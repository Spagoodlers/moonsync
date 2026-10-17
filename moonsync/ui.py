#!/usr/bin/env python
# License: GPL v3

import os
import time
import traceback
from hashlib import sha256
from queue import Queue
from threading import Thread

from qt.core import QIcon, QObject, QTimer, QToolButton, pyqtSignal

from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.widgets import BusyCursor
from calibre_plugins.moonsync import core
from calibre_plugins.moonsync.config import default_folder, prefs


class BookCache:
    '''Parsing an EPUB takes a moment, keep the last few around.'''

    def __init__(self, size=4):
        self.size, self.items = size, []

    def get(self, path):
        mtime = os.path.getmtime(path)
        for i, (p, m, b) in enumerate(self.items):
            if p == path and m == mtime:
                self.items.insert(0, self.items.pop(i))
                return b
        b = core.Book(path)
        self.items = [(path, mtime, b)] + [x for x in self.items if x[0] != path][:self.size - 1]
        return b


class ExportWorker(QObject):
    '''Writes viewer positions to Moon+ files off the GUI thread.'''

    exported = pyqtSignal(object, object)
    failed = pyqtSignal(object, object)

    def __init__(self, parent):
        QObject.__init__(self, parent)
        self.queue = Queue()
        self.books = BookCache()
        Thread(target=self.run, name='MoonSyncExport', daemon=True).start()

    def run(self):
        while True:
            self.export(*self.queue.get())

    def export(self, book_path, po_paths, folder):
        for po in po_paths:
            try:
                # Skip the change our own import just made
                if os.path.exists(po) and core.newer_side(book_path, po) != 'viewer':
                    continue
                pos = core.export_position(book_path, po, folder, book=self.books.get(book_path))
            except core.UnknownLayout:
                core.log('EXPORT refused, chapter layout unknown', os.path.basename(po))
                continue
            except Exception:
                core.log('EXPORT failed', os.path.basename(po), traceback.format_exc())
                self.failed.emit(po, traceback.format_exc())
            else:
                if pos is not None:
                    self.exported.emit(po, pos)


class MoonSyncAction(InterfaceAction):

    name = 'Moon+ Reader Sync'
    action_spec = ('Moon+ Sync', None, 'Read the selected book, starting from its Moon+ Reader position', None)
    popup_type = QToolButton.ToolButtonPopupMode.MenuButtonPopup
    action_add_menu = True
    action_type = 'current'
    dont_add_to = frozenset(['context-menu-device', 'toolbar-device', 'menubar-device'])

    def genesis(self):
        self.qaction.setIcon(QIcon.ic('bookmarks.png'))
        self.qaction.triggered.connect(self.read_selected)
        m = self.qaction.menu()
        self.create_menu_action(m, 'moonsync-read', 'Read at Moon+ position', icon='view.png', triggered=self.read_selected)
        m.addSeparator()
        self.create_menu_action(m, 'moonsync-sync', 'Sync selected books (newest position wins)', triggered=self.sync_selected)
        self.create_menu_action(m, 'moonsync-import', 'Moon+ → calibre for selected books', triggered=lambda: self.sync_selected('moon'))
        self.create_menu_action(m, 'moonsync-export', 'calibre → Moon+ for selected books', triggered=lambda: self.sync_selected('viewer'))
        self.create_menu_action(m, 'moonsync-sync-all', 'Sync every book that has a Moon+ position', triggered=self.sync_all)
        m.addSeparator()
        self.create_menu_action(m, 'moonsync-config', 'Settings...', icon='config.png', triggered=self.show_settings)
        self.books = BookCache()
        self.worker = ExportWorker(self.gui)
        self.worker.failed.connect(self.export_failed)
        self.worker.exported.connect(self.exported)
        self.original_view = None
        self.annots_mtimes = {}  # viewer annotations file name -> mtime
        self.hash_map = None  # viewer annotations file name -> book id
        self.timer = QTimer(self.gui)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.poll_viewer)

    def initialization_complete(self):
        # Every way of opening a library book (double click, View button,
        # history menu, ...) ends up in View.view_format_by_id, so wrapping
        # it is enough for "always open at the Moon+ position".
        view = self.gui.iactions.get('View')
        if view is not None:
            self.original_view = view.view_format_by_id

            def view_format_by_id(book_id, fmt, open_at=None):
                if open_at is None and prefs['open_all'] and fmt.upper() == 'EPUB':
                    open_at = self.moon_open_at(book_id)
                return self.original_view(book_id, fmt, open_at=open_at)
            view.view_format_by_id = view_format_by_id
        from calibre.utils.config import config_dir
        core.LOG_PATH = os.path.join(config_dir, 'plugins', 'moonsync.log')
        core.STATE_PATH = os.path.join(config_dir, 'plugins', 'moonsync_state.json')
        core.log('---- calibre started, plugin', '.'.join(map(str, self.interface_action_base_plugin.version)),
                 '| folder', self.folder, '| open_all', prefs['open_all'], '| save_all', prefs['save_all'])
        self.annots_mtimes = self.scan_annots()
        self.settings_changed()

    def library_changed(self, db):
        self.hash_map = None

    def shutting_down(self):
        self.timer.stop()
        # Pick up a viewer that was closed just before calibre. Done inline
        # since the worker thread dies with calibre.
        self.poll_viewer(inline=True)

    # Helpers {{{
    @property
    def folder(self):
        return prefs['folder'] or default_folder()

    def settings_changed(self):
        if prefs['save_all']:
            self.timer.start()
        else:
            self.timer.stop()

    def show_settings(self):
        self.interface_action_base_plugin.do_user_config(self.gui)

    def check_folder(self, interactive=True):
        f = self.folder
        if f and os.path.isdir(f):
            return f
        if interactive:
            error_dialog(self.gui, 'Moon+ folder not set', 'Choose the folder holding the Moon+ Reader position files first.', show=True)
            self.show_settings()
            f = self.folder
            return f if f and os.path.isdir(f) else None

    def selected_ids(self):
        return list(self.gui.library_view.get_selected_ids())

    def book_info(self, book_id, folder):
        '''Returns (title, book_path, po_paths) or None if the book has no EPUB.
        po_paths is newest first and empty if no Moon+ file exists and none
        should be created.'''
        db = self.gui.current_db.new_api
        if not db.has_format(book_id, 'EPUB'):
            return None
        title = db.field_for('title', book_id)
        uuid = db.field_for('uuid', book_id)
        path = db.format_abspath(book_id, 'EPUB')
        authors = db.field_for('authors', book_id) or ('Unknown',)
        expected = core.default_po_name(title, authors[0], uuid)
        pos = core.find_po_files(folder, uuid, title)
        if len(pos) > 1:
            # Never touch more than one file per book: prefer the one with
            # the name Moon+ itself uses, else the newest
            named = [p for p in pos if os.path.basename(p) == expected]
            print('Moon+ sync: several position files for %s, using only %s' % (title, (named or pos)[0]))
            pos = (named or pos)[:1]
        if not pos and prefs['create_missing']:
            pos = [os.path.join(folder, expected)]
        return title, path, pos

    def sync_one(self, path, pos, direction=None):
        '''Returns a short description of what happened.'''
        newest = pos[0]
        direction = direction or core.newer_side(path, newest)
        if direction == 'moon':
            if not os.path.exists(newest):
                return 'no Moon+ position'
            cfi, how = core.import_position(path, newest, book=self.books.get(path))
            return 'Moon+ → calibre' + (
                ' (approximate, from percentage: Moon+\'s chapter numbers do not fit this EPUB, '
                'the copy on the phone may be a different version)' if how == 'percent' else '')
        if direction == 'viewer':
            results = []
            for po in pos:
                try:
                    p = core.export_position(path, po, self.folder, book=self.books.get(path))
                except core.UnknownLayout:
                    return 'not written: Moon+ chapter layout for this book is not understood'
                results.append(('calibre → Moon+ (%.1f%%)' % p.percent) if p else self.in_sync_note(po))
            return ', '.join(results)
        return self.in_sync_note(newest)

    def in_sync_note(self, po):
        if not os.path.exists(po):
            return 'nothing to sync yet'
        when = time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(po)))
        return 'already in sync: Moon+ file saved at %s, position %s' % (when, core.read_po(po).serialize())
    # }}}

    # Opening {{{
    def moon_open_at(self, book_id):
        '''CFI to open the book at if Moon+ has the newer position, else None.
        Never raises: a failure here must not stop the book from opening.'''
        folder = self.check_folder(interactive=False)
        if not folder:
            return None
        try:
            info = self.book_info(book_id, folder)
            if info is None or not info[2] or not os.path.exists(info[2][0]):
                core.log('OPEN book', book_id, 'no Moon+ file, opening normally')
                return None
            title, path, pos = info
            side = core.newer_side(path, pos[0])
            if side != 'moon':
                core.log('OPEN', title, '- newer side is', side, ', opening at calibre position')
                return None
            with BusyCursor():
                cfi, how = core.import_position(path, pos[0], book=self.books.get(path))
            self.gui.status_bar.show_message('Opening at Moon+ position (%.1f%%)' % core.read_po(pos[0]).percent, 5000)
            return cfi
        except Exception:
            core.log('OPEN failed for book', book_id, traceback.format_exc())
            return None

    def read_selected(self):
        folder = self.check_folder()
        ids = self.selected_ids()
        if not folder or not ids:
            return
        db = self.gui.current_db.new_api
        if not db.has_format(ids[0], 'EPUB'):
            return error_dialog(self.gui, 'No EPUB', 'Moon+ sync only works with the EPUB format.', show=True)
        view = self.original_view or self.gui.iactions['View'].view_format_by_id
        view(ids[0], 'EPUB', open_at=self.moon_open_at(ids[0]))
    # }}}

    # Saving {{{
    def scan_annots(self):
        try:
            from calibre.gui2.viewer.annotations import annotations_dir
            with os.scandir(annotations_dir()) as it:
                return {e.name: e.stat().st_mtime for e in it if e.name.endswith('.json')}
        except OSError:
            return {}

    def build_hash_map(self):
        # The viewer names its files after sha256 of the book's path
        db = self.gui.current_db.new_api
        ans = {}
        for book_id in db.all_book_ids():
            if 'EPUB' in (db.field_for('formats', book_id) or ()):
                path = db.format_abspath(book_id, 'EPUB')
                if path:
                    ans[sha256(path.encode('utf-8')).hexdigest() + '.json'] = book_id
        return ans

    def poll_viewer(self, inline=False):
        if not prefs['save_all']:
            return
        folder = self.check_folder(interactive=False)
        current = self.scan_annots()
        changed = [n for n, m in current.items() if self.annots_mtimes.get(n) != m]
        self.annots_mtimes = current
        if not changed or not folder:
            return
        if self.hash_map is None or any(n not in self.hash_map for n in changed):
            self.hash_map = self.build_hash_map()
        for name in changed:
            book_id = self.hash_map.get(name)
            if book_id is None:
                core.log('VIEWER saved', name, 'but it is not a library EPUB')
                continue
            core.log('VIEWER saved position for book', book_id)
            info = self.book_info(book_id, folder)
            if info and info[2]:
                item = (info[1], info[2], folder)
                if inline:
                    self.worker.export(*item)
                else:
                    self.worker.queue.put(item)

    def exported(self, po, pos):
        self.gui.status_bar.show_message('Moon+ position saved: %.1f%%' % pos.percent, 3000)

    def export_failed(self, po, tb):
        print('Moon+ sync: failed to write', po)
        print(tb)
    # }}}

    # Bulk sync {{{
    def sync_selected(self, direction=None):
        folder = self.check_folder()
        if not folder:
            return
        self.run_sync([(bid, self.book_info(bid, folder)) for bid in self.selected_ids()], direction)

    def sync_all(self):
        folder = self.check_folder()
        if not folder:
            return
        db = self.gui.current_db.new_api
        seen, items = set(), []
        for po in core.po_files(folder):
            m = core.UUID_PAT.search(os.path.basename(po))
            bid = db.lookup_by_uuid(m.group(1)) if m else None
            if bid is not None and bid not in seen:
                seen.add(bid)
                items.append((bid, self.book_info(bid, folder)))
        self.run_sync(items)

    def run_sync(self, items, direction=None):
        lines = []
        with BusyCursor():
            for bid, info in items:
                if info is None:
                    lines.append('Book %d: no EPUB format, skipped' % bid)
                    continue
                title, path, pos = info
                if not pos:
                    lines.append('%s: no Moon+ position file' % title)
                    continue
                try:
                    lines.append('%s: %s' % (title, self.sync_one(path, pos, direction)))
                except Exception as e:
                    lines.append('%s: FAILED (%s)' % (title, e))
                    traceback.print_exc()
        if lines:
            info_dialog(self.gui, 'Moon+ sync', 'Synced %d book(s)' % len(lines), det_msg='\n'.join(lines), show=True)
    # }}}
