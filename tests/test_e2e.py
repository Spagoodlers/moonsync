'''Run with: calibre-debug tests/test_e2e.py [library_path] [moon_folder]

Import every Moon+ position into a scratch viewer annotations folder, then
export it back to a copy of the .po file and check Moon+ would land in the
same place. Neither the real Moon+ folder nor the real viewer data is touched.
'''
import glob
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moonsync import core  # noqa: E402

LIB = sys.argv[1] if len(sys.argv) > 1 else r'F:\books\calibrelibrary'
MOON = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(r'~\Documents\Dropbox\Apps\Books\.Moon+\Cache')

tmp = tempfile.mkdtemp()
annots_dir = os.path.join(tmp, 'annots')
moon_dir = os.path.join(tmp, 'moon')
os.makedirs(annots_dir)
shutil.copytree(MOON, moon_dir, dirs_exist_ok=True)
core.viewer_annots_path = lambda p: os.path.join(annots_dir, core.sha256(p.encode()).hexdigest() + '.json')
core.STATE_PATH = os.path.join(tmp, 'state.json')

db = sqlite3.connect(os.path.join(LIB, 'metadata.db'))
failures = 0
checked = 0
for po in sorted(glob.glob(os.path.join(moon_dir, '*.epub.po'))):
    m = core.UUID_PAT.search(os.path.basename(po))
    r = m and db.execute("select b.title,b.path,d.name from books b join data d on d.book=b.id where b.uuid=? and d.format='EPUB'", (m.group(1),)).fetchone()
    if not r:
        continue
    path = os.path.normpath(os.path.join(LIB, r[1], r[2] + '.epub'))
    before = core.read_po(po)
    book = core.Book(path)
    cfi, how = core.import_position(path, po, book=book)
    assert core.newer_side(path, po) is None, 'timestamps should match after import'
    # Pretend the viewer saved the same spot a minute later
    core.write_viewer_last_read(path, cfi, os.path.getmtime(po) + 60)
    assert core.newer_side(path, po) == 'viewer'
    try:
        written = core.export_position(path, po, moon_dir, book=book)
    except core.UnknownLayout:
        print('SKIP %-35s %s (layout unknown, export refused)' % (r[0][:35], before.serialize()))
        continue
    after = core.read_po(po)
    same = (after.chapter, after.offset) == (before.chapter, before.offset)
    failures += not same
    print('%s %-35s %s -> %s %s' % ('OK  ' if same else 'FAIL', r[0][:35], before.serialize(), after.serialize(),
                                   '(unchanged, not rewritten)' if written is None else ''))
    assert core.newer_side(path, po) in (None, 'viewer')
    # Read on a little in calibre, so the export has to write
    idx, off = core.cfi_to_offset(book, cfi)
    if book.files[idx].length < off + 300:
        continue
    core.write_viewer_last_read(path, core.offset_to_cfi(book, idx, off + 300), os.path.getmtime(po) + 120)
    written = core.export_position(path, po, moon_dir, book=book)
    if written is None:
        continue
    # Dropbox touching our own file must not count as a Moon+ change
    t = os.path.getmtime(po) + 120
    os.utime(po, (t, t))
    assert core.newer_side(path, po) is None, 'our own write came back as newer'
    # Moon+ re-saving our position at the top of the page is not a change
    if written.offset > 0:
        echo = core.MoonPosition(written.stamp, written.chapter, 0, max(0, written.offset - 500), written.percent)
        core.write_po(po, echo)
        os.utime(po, (t, t))
        assert core.newer_side(path, po) is None, 'page start echo came back as newer'
    # A real move in Moon+ is
    moved = core.MoonPosition(written.stamp, written.chapter, 0, written.offset + 1, written.percent)
    core.write_po(po, moved)
    os.utime(po, (t, t))
    assert core.newer_side(path, po) == 'moon'
    checked += 1

# A book with no Moon+ file yet gets one with the folder's usual stamp
name = core.default_po_name('Some Title: With Colon', 'An Author', '00000000-0000-0000-0000-000000000000')
print('new file name:', name, '| stamp:', core.common_stamp(moon_dir))
shutil.rmtree(tmp)
print('failures:', failures, '| change detection checked on', checked, 'books')
sys.exit(1 if failures else 0)
