'''Run with: calibre-debug tests/diagnose.py [library_path] [moon_folder]

Read only. For the books most recently opened in the calibre viewer, shows
what the plugin would decide: which side is newer, and how the Moon+
position maps into the book.
'''
import datetime
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moonsync import core  # noqa: E402

LIB = sys.argv[1] if len(sys.argv) > 1 else r'F:\books\calibrelibrary'
MOON = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(r'~\Documents\Dropbox\Apps\Books\.Moon+\Cache')


def t(x):
    return datetime.datetime.fromtimestamp(x).strftime('%H:%M:%S') if x else '-'


from calibre.gui2.viewer.annotations import annotations_dir  # noqa: E402
from calibre.library import db  # noqa: E402

d = db(LIB).new_api
adir = annotations_dir()
recent = sorted(os.listdir(adir), key=lambda n: -os.path.getmtime(os.path.join(adir, n)))[:6]
hm = {}
for b in d.all_book_ids():
    if 'EPUB' in (d.field_for('formats', b) or ()):
        p = d.format_abspath(b, 'EPUB')
        hm[hashlib.sha256(p.encode()).hexdigest() + '.json'] = (b, p)
for n in recent:
    if n not in hm:
        print('not a library EPUB:', n)
        continue
    b, p = hm[n]
    title = d.field_for('title', b)
    cfi, vts = core.read_viewer_last_read(p)
    print('==', title, '| viewer', cfi, t(vts))
    pos = core.find_po_files(MOON, d.field_for('uuid', b), title)
    if not pos:
        print('   no Moon+ file')
    book = core.Book(p)
    for po in pos:
        mp = core.read_po(po)
        print('   po', mp.serialize(), t(os.path.getmtime(po)), 'newer:', core.newer_side(p, po), '|', os.path.basename(po)[-50:])
        print('   moon ->', book.moon_to_spine(mp), 'export model:', book.detect_model(mp))
