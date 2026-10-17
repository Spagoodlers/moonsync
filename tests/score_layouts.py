'''Run with: calibre-debug tests/score_layouts.py [library_path] [moon_folder]

Read only. Scores every chapter layout in core.LAYOUTS against the positions
Moon+ itself wrote: the current .po files plus the Moon+ positions the plugin
log recorded on import. Positions the plugin wrote are left out, since they
fit the layout they were written with by construction. Use it to check the
layout rules whenever new books or Moon+ versions turn up.

For each position: how far Moon+'s percentage is from ours under each layout,
or "-" if the offset does not fit in that chapter.
'''
import glob
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moonsync import core  # noqa: E402

LIB = sys.argv[1] if len(sys.argv) > 1 else r'F:\books\calibrelibrary'
MOON = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(r'~\Documents\Dropbox\Apps\Books\.Moon+\Cache')
from calibre.utils.config import config_dir  # noqa: E402
LOG = os.path.join(config_dir, 'plugins', 'moonsync.log')

ours, seen = set(), set()
for name in (LOG + '.old', LOG):
    try:
        lines = open(name, encoding='utf-8').read().splitlines()
    except OSError:
        continue
    for line in lines:
        m = re.search(r'EXPORT wrote .*?_([0-9a-f-]{36})\.epub\.po .* -> (\S+) ', line)
        if m:
            ours.add((m.group(1), m.group(2)))
        m = re.search(r'IMPORT .*?_([0-9a-f-]{36})\.epub\.po (\S+) ', line)
        if m and '(our own)' not in line:
            seen.add((m.group(1), m.group(2)))
for po in glob.glob(os.path.join(MOON, '*.epub.po')):
    m = core.UUID_PAT.search(os.path.basename(po))
    if m:
        seen.add((m.group(1), open(po, encoding='utf-8').read().strip()))

db = sqlite3.connect(os.path.join(LIB, 'metadata.db'))
books = {}
errors = {m: [] for m in core.LAYOUTS}
print('%-32s %-30s ' % ('book', 'Moon+ position') + ' '.join('%9s' % m for m in core.LAYOUTS))
for uuid, raw in sorted(seen - ours):
    r = db.execute("select b.title,b.path,d.name from books b join data d on d.book=b.id where b.uuid=? and d.format='EPUB'", (uuid,)).fetchone()
    pos = core.MoonPosition.parse(raw)
    if not r or (pos.chapter == 0 and pos.percent < 0.1):
        continue  # not in the library, or the very start, which fits anything
    path = os.path.normpath(os.path.join(LIB, r[1], r[2] + '.epub'))
    b = books.get(path) or books.setdefault(path, core.Book(path))
    fits = {c[0]: c[3] for c in b.candidates(pos)}
    for m in core.LAYOUTS:
        errors[m].append(fits.get(m, 99))
    print('%-32s %-30s ' % (r[0][:32], raw) + ' '.join('%9s' % ('%.1f' % fits[m] if m in fits else '-') for m in core.LAYOUTS))

n = len(errors[core.LAYOUTS[0]])
print()
for limit in (1.0, 2.5, core.MAX_PERCENT_ERROR):
    print('within %.1f points: ' % limit + ', '.join('%s %d/%d' % (m, sum(e <= limit for e in errors[m]), n) for m in core.LAYOUTS))
