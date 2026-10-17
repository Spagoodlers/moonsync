#!/usr/bin/env python
# License: GPL v3
'''
Conversion between Moon+ Reader position files (*.po) and calibre e-book
viewer positions (EPUB CFIs). No GUI code lives here so it can be tested with
calibre-debug.

Moon+ .po format (reverse engineered, there is no public spec):

    <stamp>*<chapter>@<sub>#<offset>:<percent>%

stamp    13 digit millisecond epoch. It is shared by many books so it seems to
         identify the device/installation rather than the save time. We
         preserve whatever value is already in use.
chapter  Moon+ "chapter" index. Usually the spine index, but Moon+ splits
         large HTML files at their table of contents anchors, so for those
         books every TOC section in a big file counts as its own chapter.
sub      Always 0 in observed files.
offset   Character offset into the chapter's body text.
percent  Progress shown to the user, used here only to validate a mapping.
'''

import os
import re
import time
from hashlib import sha256

from lxml import etree

XHTML_NS = 'http://www.w3.org/1999/xhtml'
BODY = '{%s}body' % XHTML_NS
PO_PAT = re.compile(r'^\s*(\d+)\*(\d+)@(\d+)#(\d+):([\d.]+)%\s*$')
UUID_PAT = re.compile(r'_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.epub\.po$', re.I)
# Files with more body text than this are split at their TOC anchors by Moon+.
# Fitted against real .po files; see README.
SPLIT_THRESHOLD = 100000
# A mapping whose percentage disagrees with Moon+ by more than this is
# rejected and the percentage is used instead.
MAX_PERCENT_ERROR = 2.0


class UnknownLayout(ValueError):
    '''Moon+ splits this book into chapters in a way we cannot reproduce, so
    writing a position would send Moon+ to the wrong place.'''


class MoonPosition:

    def __init__(self, stamp, chapter, sub, offset, percent):
        self.stamp, self.chapter, self.sub, self.offset, self.percent = stamp, chapter, sub, offset, percent

    @classmethod
    def parse(cls, raw):
        m = PO_PAT.match(raw)
        if m is None:
            raise ValueError('Not a Moon+ EPUB position: %r' % raw)
        return cls(m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), float(m.group(5)))

    def serialize(self):
        return '%s*%d@%d#%d:%.1f%%' % (self.stamp, self.chapter, self.sub, self.offset, self.percent)

    def __repr__(self):
        return 'MoonPosition(%s)' % self.serialize()


# Moon+ files {{{

def po_files(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names if n.lower().endswith('.epub.po')]


def find_po_files(folder, uuid, title=None):
    '''All Moon+ files for a book, newest first. Moon+ names its files after
    the book file, which calibre names "<title> - <author>_<uuid>.epub", so
    the UUID is the reliable key. There can be more than one if the book was
    copied to the phone under different names.'''
    uuid = uuid.lower()
    candidates = po_files(folder)
    ans = []
    for path in candidates:
        m = UUID_PAT.search(os.path.basename(path))
        if m is not None and m.group(1).lower() == uuid:
            ans.append(path)
    if not ans and title:
        # Only for files without a UUID (books copied to the phone by hand)
        key = sanitize(title).lower()
        for path in candidates:
            name = os.path.basename(path).lower()
            if UUID_PAT.search(name) is None and (name == key + '.epub.po' or name.startswith(key + ' - ')):
                ans.append(path)
    return sorted(ans, key=os.path.getmtime, reverse=True)


def sanitize(text):
    return re.sub(r'[\\/:*?"<>|]', '_', text).strip()


def default_po_name(title, author, uuid):
    # Mirrors the names Moon+ produces for calibre books: title and author
    # are each cut to 31 characters, filesystem unsafe characters become _
    return '%s - %s_%s.epub.po' % (sanitize(title)[:31], sanitize(author)[:31], uuid)


def common_stamp(folder):
    counts = {}
    for path in po_files(folder):
        try:
            with open(path, encoding='utf-8') as f:
                pos = MoonPosition.parse(f.read())
        except Exception:
            continue
        counts[pos.stamp] = counts.get(pos.stamp, 0) + 1
    if counts:
        return max(counts, key=counts.get)
    return str(int(time.time() * 1000))


def read_po(path):
    with open(path, encoding='utf-8') as f:
        return MoonPosition.parse(f.read())


def write_po(path, pos):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(pos.serialize())
    os.replace(tmp, path)
# }}}


# Book text model {{{

class SpineFile:

    def __init__(self, name, body):
        self.name = name
        self.body = body
        self.length = 0
        self.anchors = {}
        if body is not None:
            self.anchors, self.length = anchor_offsets(body)


def anchor_offsets(body):
    offsets = {}
    n = 0
    for ev, el in etree.iterwalk(body, events=('start', 'end')):
        if ev == 'start':
            if isinstance(el.tag, str):
                for attr in ('id', 'name'):
                    v = el.get(attr)
                    if v and v not in offsets:
                        offsets[v] = n
                if el.text:
                    n += len(el.text)
        elif el is not body and el.tail:
            n += len(el.tail)
    return offsets, n


class Book:

    def __init__(self, path_to_epub):
        from calibre.ebooks.oeb.polish.container import get_container
        from calibre.ebooks.oeb.polish.toc import get_toc
        c = get_container(path_to_epub, tweak_mode=True)
        self.files = []
        for name, linear in c.spine_names:
            root = c.parsed(name)
            self.files.append(SpineFile(name, root.find('.//' + BODY)))
        self.total = sum(f.length for f in self.files) or 1
        self.toc_frags = {}
        for node in get_toc(c).iterdescendants():
            if node.dest and node.frag:
                self.toc_frags.setdefault(node.dest, set()).add(node.frag)
        self._chapters = {}

    def chapters(self, model):
        '''List of (spine_index, start_offset) for each Moon+ chapter.'''
        if model not in self._chapters:
            ans = []
            for i, f in enumerate(self.files):
                starts = {0}
                if model == 'toc-split' and f.length > SPLIT_THRESHOLD:
                    starts |= {f.anchors[x] for x in self.toc_frags.get(f.name, ()) if x in f.anchors}
                ans.extend((i, s) for s in sorted(starts))
            self._chapters[model] = ans
        return self._chapters[model]

    def global_offset(self, spine_index, offset):
        return sum(f.length for f in self.files[:spine_index]) + offset

    def from_global(self, goffset):
        for i, f in enumerate(self.files):
            if goffset < f.length or i == len(self.files) - 1:
                return i, max(0, min(goffset, f.length))
            goffset -= f.length

    def percent(self, spine_index, offset):
        return 100.0 * self.global_offset(spine_index, offset) / self.total

    def moon_to_spine(self, pos):
        '''Return (spine_index, offset, how) for a Moon+ position. how is the
        chapter layout used, or "percent" if the position had to be placed
        from Moon+'s percentage alone.'''
        found = {}
        for model in ('spine', 'toc-split'):
            chapters = self.chapters(model)
            if pos.chapter >= len(chapters):
                continue
            idx, start = chapters[pos.chapter]
            nxt = chapters[pos.chapter + 1] if pos.chapter + 1 < len(chapters) else None
            end = nxt[1] if nxt and nxt[0] == idx else self.files[idx].length
            if start + pos.offset > end:
                continue  # offset does not fit, so this is not Moon+'s chapter layout
            off = start + pos.offset
            found[model] = (abs(self.percent(idx, off) - pos.percent), idx, off)
        if found:
            # Moon+'s percentage is only loosely related to text position, so
            # it just picks between layouts that both fit.
            model = min(found, key=lambda m: found[m][0])
            err, idx, off = found[model]
            if len(found) == 2 and found['spine'][1:] == found['toc-split'][1:]:
                model = 'toc-split'
            if err <= MAX_PERCENT_ERROR or not self.size_split_suspected(idx):
                return idx, off, model
        idx, off = self.from_global(int(self.total * pos.percent / 100.0))
        return idx, off, 'percent'

    def size_split_suspected(self, spine_index):
        '''Moon+ also seems to split huge files that have no TOC anchors, by
        size, in a way not yet worked out. Chapter numbers after such a file
        cannot be trusted.'''
        for f in self.files[:spine_index + 1]:
            if f.length > SPLIT_THRESHOLD and not any(x in f.anchors for x in self.toc_frags.get(f.name, ())):
                return True
        return False

    def detect_model(self, pos):
        '''Which chapter layout Moon+ uses for this book, judged from an
        existing Moon+ position. None if that position fits no known layout.'''
        if pos is None:
            return 'toc-split'  # nothing to check against, best guess
        idx, off, how = self.moon_to_spine(pos)
        return None if how == 'percent' else how

    def spine_to_moon(self, spine_index, offset, model, stamp):
        chapters = self.chapters(model)
        chapter, start = 0, 0
        for i, (idx, s) in enumerate(chapters):
            if (idx, s) <= (spine_index, offset):
                chapter, start = i, s
            else:
                break
        if chapters[chapter][0] != spine_index:
            start = offset = 0
        pct = round(self.percent(spine_index, offset), 1)
        return MoonPosition(stamp, chapter, 0, offset - start, pct)
# }}}


# CFI <-> text offset {{{
# Mirrors src/pyj/read_book/cfi.pyj in calibre:
# * child indices: elements are even, text and comments odd; text on both
#   sides of a comment shares one odd index.
# * a text position is NOT encoded relative to its own text node. calibre
#   walks back over every previous sibling (elements included) to the
#   parent's first child and adds up the lengths of the *direct* text
#   children it passed, skipping the text inside sibling elements. So
#   "<p>ab<i>cd</i>ef</p>" position at "f" is /p/1:3, not /p/3:1.
# * decoding goes forward from the named node through direct text children
#   only, in the same way.

def _children(el, start):
    '''Yield (index, kind, payload, start_offset) for el's child nodes, where
    kind is "text" (payload: the string), "el" (payload: the element) or
    "other" (comment/PI). start_offset is the global text offset.'''
    index, pos = 0, start
    if el.text:
        index |= 1
        yield index, 'text', el.text, pos
        pos += len(el.text)
    for child in el:
        if isinstance(child.tag, str):
            index = (index | 1) + 1
            yield index, 'el', child, pos
            pos += text_length(child)
        else:
            index |= 1
            yield index, 'other', child, pos
        if child.tail:
            index |= 1
            yield index, 'text', child.tail, pos
            pos += len(child.tail)


def text_length(el):
    return sum(len(t) for t in el.itertext()) if isinstance(el.tag, str) else 0


def _escape(raw):
    return re.sub(r'[\[\],^();~@!]', lambda m: '^' + m.group(), raw)


def _step(index, el=None):
    i = el.get('id') if el is not None and isinstance(el.tag, str) else None
    return '/%d[%s]' % (index, _escape(i)) if i else '/%d' % index


def offset_to_cfi(book, spine_index, offset):
    f = book.files[spine_index]
    prefix = 'epubcfi(/%d' % ((spine_index + 1) * 2)
    if f.body is None:
        return prefix + ')'
    path, el = '/2/4', f.body
    offset = max(0, min(offset, f.length))
    while True:
        kids = list(_children(el, 0))
        direct = 0  # direct text of el seen so far
        target = None
        for index, kind, payload, start in kids:
            if kind == 'text':
                if offset <= start + len(payload):
                    target = ('text', direct + offset - start)
                    break
                direct += len(payload)
            elif kind == 'el' and offset < start + text_length(payload):
                target = ('el', index, payload, start)
                break
        if target is None:
            if direct and kids:
                target = ('text', direct)
            else:
                return prefix + path + ')'
        if target[0] == 'text':
            index, kind, payload, start = kids[0]
            return prefix + path + _step(index, payload if kind == 'el' else None) + ':%d)' % target[1]
        index, child, start = target[1], target[2], target[3]
        path += _step(index, child)
        el, offset = child, offset - start


CFI_STEP = re.compile(r'/(\d+)(?:\[((?:\^.|[^\]])*)\])?')


def cfi_to_offset(book, cfi):
    '''Return (spine_index, text_offset) for a calibre CFI.'''
    m = re.match(r'epubcfi\((.+)\)$', cfi.strip())
    if m is None:
        raise ValueError('Not a CFI: %r' % cfi)
    rest = m.group(1)
    steps = []
    while True:
        sm = CFI_STEP.match(rest)
        if sm is None:
            break
        steps.append(int(sm.group(1)))
        rest = rest[sm.end():]
    om = re.match(r':(\d+)', rest)
    char_offset = int(om.group(1)) if om else None
    if not steps:
        raise ValueError('Empty CFI: %r' % cfi)
    spine_index = steps[0] // 2 - 1
    if not 0 <= spine_index < len(book.files):
        raise ValueError('CFI spine step out of range: %r' % cfi)
    f = book.files[spine_index]
    if f.body is None or len(steps) < 3:
        return spine_index, 0
    # steps[1] is <html>, steps[2] is <body>
    node, pos = f.body, 0
    siblings = first = None
    for target in steps[3:]:
        kids = list(_children(node, pos))
        i = next((i for i, k in enumerate(kids) if k[0] == target), None)
        if i is None:
            break
        siblings, first = kids, i
        index, kind, payload, pos = kids[i]
        if kind != 'el':
            break
        node = payload
    if char_offset is None or siblings is None:
        return spine_index, pos
    # Walk forward from the named node through the parent's direct text
    remaining, last_end = char_offset, pos
    for index, kind, payload, start in siblings[first:]:
        if kind == 'text':
            if remaining <= len(payload):
                return spine_index, start + remaining
            remaining -= len(payload)
            last_end = start + len(payload)
    return spine_index, last_end
# }}}


# calibre viewer storage {{{

def viewer_annots_path(path_to_book):
    from calibre.gui2.viewer.annotations import annotations_dir
    key = sha256(path_to_book.encode('utf-8')).hexdigest()
    return os.path.join(annotations_dir(), key + '.json')


def read_viewer_last_read(path_to_book):
    '''Return (cfi, timestamp_seconds) or (None, 0).'''
    from calibre.utils.iso8601 import parse_iso8601
    from calibre.utils.serialize import json_loads
    p = viewer_annots_path(path_to_book)
    try:
        with open(p, 'rb') as f:
            annots = json_loads(f.read())
    except (OSError, ValueError):
        return None, 0
    best = None
    for a in annots:
        if a.get('type') == 'last-read' and a.get('pos_type') == 'epubcfi':
            ts = parse_iso8601(a['timestamp'], assume_utc=True).timestamp()
            if best is None or ts > best[1]:
                best = (a['pos'], ts)
    return best or (None, 0)


def write_viewer_last_read(path_to_book, cfi, timestamp=None):
    from datetime import datetime, timezone

    from calibre.utils.serialize import json_dumps, json_loads
    p = viewer_annots_path(path_to_book)
    try:
        with open(p, 'rb') as f:
            annots = json_loads(f.read())
    except (OSError, ValueError):
        annots = []
    annots = [a for a in annots if a.get('type') != 'last-read']
    ts = datetime.fromtimestamp(timestamp or time.time(), timezone.utc).isoformat()
    annots.append({'type': 'last-read', 'pos': cfi, 'pos_type': 'epubcfi', 'timestamp': ts})
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(json_dumps(annots))
    os.replace(tmp, p)
# }}}


# High level operations {{{

LOG_PATH = None  # set by the GUI; every sync decision is appended here


def log(*args):
    if LOG_PATH is None:
        return
    line = time.strftime('%H:%M:%S ') + ' '.join(str(a) for a in args)
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 1024 * 1024:
            os.replace(LOG_PATH, LOG_PATH + '.old')
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def _stamp(t):
    return time.strftime('%H:%M:%S', time.localtime(t)) if t else 'never'


def import_position(book_path, po_path, book=None):
    '''Moon+ -> viewer. Returns (cfi, how).'''
    book = book or Book(book_path)
    pos = read_po(po_path)
    idx, off, how = book.moon_to_spine(pos)
    cfi = offset_to_cfi(book, idx, off)
    write_viewer_last_read(book_path, cfi, os.path.getmtime(po_path))
    log('IMPORT', os.path.basename(po_path), pos.serialize(), '-> spine', idx, 'offset', off, 'via', how, '->', cfi)
    return cfi, how


def export_position(book_path, po_path, folder, book=None):
    '''viewer -> Moon+. Returns the written MoonPosition or None.'''
    cfi, ts = read_viewer_last_read(book_path)
    if cfi is None:
        return None
    book = book or Book(book_path)
    existing = None
    if po_path and os.path.exists(po_path):
        try:
            existing = read_po(po_path)
        except Exception:
            existing = None
    idx, off = cfi_to_offset(book, cfi)
    stamp = existing.stamp if existing else common_stamp(folder)
    model = book.detect_model(existing)
    if model is None:
        raise UnknownLayout('Cannot work out how Moon+ divides this book into chapters')
    pos = book.spine_to_moon(idx, off, model, stamp)
    if existing is not None and (existing.chapter, existing.offset) == (pos.chapter, pos.offset):
        log('EXPORT unchanged', os.path.basename(po_path), pos.serialize(), 'viewer', cfi)
        return None  # unchanged; don't make Dropbox upload it again
    write_po(po_path, pos)
    log('EXPORT wrote', os.path.basename(po_path), (existing.serialize() if existing else 'new file'), '->', pos.serialize(), 'from viewer', cfi, 'saved', _stamp(ts))
    # Give the file the viewer's timestamp so newer_side() sees them as equal
    os.utime(po_path, (ts, ts))
    return pos


def newer_side(book_path, po_path):
    '''"moon", "viewer" or None depending on which position is newer.'''
    cfi, vts = read_viewer_last_read(book_path)
    mts = os.path.getmtime(po_path) if po_path and os.path.exists(po_path) else 0
    if not cfi and not mts:
        return None
    log('COMPARE', os.path.basename(po_path or ''), 'moon file', _stamp(mts), '| viewer', _stamp(vts), cfi)
    # Two seconds of slack so a just-synced pair is not bounced back
    if mts > vts + 2:
        return 'moon'
    if vts > mts + 2:
        return 'viewer'
    return None
# }}}
