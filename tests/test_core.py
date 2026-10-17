'''Run with: calibre-debug tests/test_core.py [library_path] [moon_folder]

Checks against real data:
1. Every last-read CFI the calibre viewer saved for a library EPUB decodes
   to a text offset and re-encodes to the same CFI.
2. Every Moon+ position maps to a spine offset and back to the same Moon+
   chapter/offset.
'''
import glob
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moonsync import core  # noqa: E402

LIB = sys.argv[1] if len(sys.argv) > 1 else r'F:\books\calibrelibrary'
MOON = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(r'~\Documents\Dropbox\Apps\Books\.Moon+\Cache')

db = sqlite3.connect(os.path.join(LIB, 'metadata.db'))
rows = db.execute("select b.uuid, b.title, b.path, d.name from books b join data d on d.book=b.id where d.format='EPUB'").fetchall()
# calibre stores paths with / but the viewer keys its files on the native path
books = {u: (t, os.path.normpath(os.path.join(LIB, p, n + '.epub'))) for u, t, p, n in rows}

print('== viewer CFI round trip')
ok = bad = 0
for uuid, (title, path) in books.items():
    cfi, ts = core.read_viewer_last_read(path)
    if not cfi or '@' in cfi:  # skip spatial (image) CFIs
        continue
    try:
        b = core.Book(path)
        idx, off = core.cfi_to_offset(b, cfi)
        again = core.offset_to_cfi(b, idx, off)
    except Exception as e:
        print('ERROR', title, cfi, e)
        bad += 1
        continue
    if again == cfi:
        ok += 1
    else:
        # Same text offset is acceptable (e.g. calibre pointed at an element boundary)
        same = core.cfi_to_offset(b, again) == (idx, off)
        print('DIFF' if not same else 'EQUIV', title[:40], cfi, '->', again)
        ok += same
        bad += not same
print('round trip ok=%d bad=%d' % (ok, bad))

print('== Moon+ round trip')
for po in sorted(glob.glob(os.path.join(MOON, '*.epub.po'))):
    m = core.UUID_PAT.search(os.path.basename(po))
    if not m or m.group(1) not in books:
        continue
    title, path = books[m.group(1)]
    b = core.Book(path)
    pos = core.read_po(po)
    idx, off, how = b.moon_to_spine(pos)
    cfi = core.offset_to_cfi(b, idx, off)
    idx2, off2 = core.cfi_to_offset(b, cfi)
    back = b.spine_to_moon(idx2, off2, how if how != 'percent' else 'toc-split', pos.stamp)
    flag = 'OK ' if (how == 'percent' or (back.chapter, back.offset) == (pos.chapter, pos.offset)) else 'BAD'
    text = ''.join(b.files[idx].body.itertext())[off:off + 50].replace('\n', ' ') if b.files[idx].body is not None else ''
    print(flag, '%-32s %-30s %-9s %s | %r' % (title[:32], pos.serialize(), how, back.serialize(), text))
