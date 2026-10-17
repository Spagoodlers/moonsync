# Moon+ Reader Sync for calibre

A calibre GUI plugin that shares reading positions between Moon+ Reader Pro
(through the `.po` files its Dropbox sync writes) and calibre's e-book viewer.
Point it at any folder holding the `.po` files.

## Use

Toolbar button **Moon+ Sync**:

- **Click / Read at Moon+ position**: opens the selected book in the calibre
  viewer. If Moon+ has the newer position, the book opens there. While you
  read, the position is written back to the `.po` file, so Moon+ picks it up
  on the phone.
- **Sync selected books**: whichever side is newer wins.
- **Moon+ → calibre / calibre → Moon+**: force one direction.
- **Sync every book that has a Moon+ position**.
- **Settings**:
  - the folder;
  - **Always open books at their Moon+ position**: hooks calibre's own View
    action, so double click, the View button and the history menu all open at
    the Moon+ position when it is newer;
  - **Always save the calibre viewer position to Moon+**: watches every viewer
    position save (it happens every few seconds and when the viewer closes)
    for any library EPUB, and writes it to the `.po` file;
  - creating `.po` files for books Moon+ has never opened.

Only EPUB is supported.

## How it works

### Moon+ `.po` files

`<stamp>*<chapter>@<sub>#<offset>:<percent>%`, for example
`1732319143006*11@0#76306:55.3%`. There is no public spec. This is what the
real files show:

- File name: `<title, 31 chars> - <author>_<calibre uuid>.epub.po`. The
  plugin matches books by the UUID.
- `stamp` is shared by many books but differs between devices, so it is a
  device/install id. It is kept as is, never set to the current time.
- `chapter` counts spine files, with a file split into several chapters at
  its TOC anchors (see below).
- `offset` is the character offset into that chapter's body text. It does not
  depend on font size or screen. Moon+ saves the top of the page on screen,
  so a position it saves is up to a page before where you were reading.
- `percent` is what Moon+ shows. It comes from Moon+'s own layout (images,
  page breaks, ...), and is typically 0.3 to 3.5 points away from a
  text-based percentage. So it is used only to rule chapter layouts out,
  never to place a position exactly.

Moon+ can also write `.an` files (zlib-compressed highlights and notes). They
are not used.

### Chapter layouts

Moon+'s chapter numbers are the hard part. The plugin knows three ways a book
can be divided, and tries them in this order (`core.LAYOUTS`):

1. `toc-all`: every TOC anchor with some text before it in its file starts a
   new chapter, whatever the file size. An anchor with only whitespace before
   it (usually the heading at the top of the file) does not.
2. `toc-split`: only files with more than 100k characters are split at their
   TOC anchors.
3. `spine`: one chapter per spine file.

For books whose TOC points only at file starts, all three are the same. They
differ for technical books, whose TOCs list sections inside small chapter
files. There, positions Moon+ wrote in October 2026 only fit `toc-all`
(Dependency Injection: `toc-split` was 46 points off, `toc-all` 2; Software
Architect Elevator 26 against 1). Some older `.po` files fit only
`toc-split`, but they match the plugin's own percentage exactly, so they were
probably written by an earlier version of this plugin, which used
`toc-split`.

When importing, every layout the position fits (its offset lies inside that
chapter) and that is within 5 points of Moon+'s percentage is a candidate. The
plugin picks, in this order:

- a layout already learned for this book and device;
- one within 1 point of the best match;
- the earliest in the list above.

If no layout is within 5 points, the position is placed from the percentage
alone and nothing is written back for that book.

`tests/score_layouts.py` scores the layouts against every position Moon+ has
written. Run it when new books or Moon+ versions show up.

### What the plugin remembers

`<calibre config>/plugins/moonsync_state.json`, per `.po` file:

- `wrote`: the last position the plugin wrote, and `model`, the layout used.
  If the `.po` file still holds exactly that, it is our own write, so it is
  not treated as news from Moon+, even if Dropbox gave it a newer time.
  Further exports keep the same layout, instead of re-guessing it from our
  own write.
- `layouts`: per device stamp, the layouts that all positions Moon+ has
  written are consistent with. Each new Moon+ position can only narrow this
  list. If a new position fits none of them, the list starts over, since the
  book or device has changed. Positions that match the plugin's own
  percentage exactly are not learned from, because they are most likely
  legacy plugin writes.
- `book`: the book's shape (spine files and text length) the above was
  learned on. If the library EPUB changes shape, both are forgotten.

**Echo**: when Moon+ opens a position we wrote, it saves the top of that page,
which is the same chapter up to 3000 characters earlier. Importing that would
pull calibre back a page every time, so it counts as "in sync". Reading
further in Moon+ is still picked up. Forcing Moon+ → calibre always imports.

### calibre viewer

The viewer stores its last position in
`%APPDATA%/calibre/viewer/annots/<sha256(book path)>.json` as an EPUB CFI,
and opens at the newest `last-read` entry. `core.py` converts between CFIs
and text offsets the same way calibre's `read_book/cfi.pyj` does. A text
position is counted over the parent element's *direct* text, starting from
its first child.

### Safety

When a Moon+ position fits no chapter layout (within 5 points of Moon+'s
own percentage), importing falls back to the percentage. In that case the
plugin **refuses to write** to that book's `.po`, because a wrong chapter
number would move you in Moon+. Before 0.4 a layout further out was still
accepted unless the book had a huge file without TOC anchors. That is how
Dependency Injection opened at 52.7% when Moon+ was at 6.8%.

### When positions are still wrong

Things that can still break a position, and what to do about each:

- **The phone has a different copy of the book.** Chapter numbers only make
  sense for the exact EPUB Moon+ opened. calibre rewrites the library file
  when it embeds metadata (it did so for six books on 2026-10-17, as they
  were opened), and a book that was converted, polished or replaced after it
  went to the phone can have a different spine. Signs: the sync report says
  "approximate, from percentage", and the log shows `no chapter layout fits`.
  Today this is Power Broker, Lovecraft, Delphi Fleming, Press Reset, The
  Elusive Shift and War Is a Racket. Fix: send the library copy to the phone
  again.
- **Different devices.** Each device has its own stamp, and layouts are
  learned per stamp. Positions from stamp `1761228724937` fit the library
  copies worst of all, which again suggests different book files on that
  device.
- **A layout we don't know yet.** Moon+ may split huge files without TOC
  anchors by size (Power Broker hints at this), and may skip the cover or the
  EPUB 3 nav document (War Is a Racket, Press Reset). Neither is confirmed, so
  neither is modelled. `tests/score_layouts.py` is the tool to test such
  ideas.
- **What counts as a character.** Offsets count the raw text of the HTML,
  including source whitespace. If Moon+ collapses whitespace, positions deep
  into chapters with lots of code drift by up to the whitespace share: 22%
  in some Five Lines of Code chapters, under 1% in novels. Not confirmed
  either way.
- **Moon+'s page snapping.** Moon+ saves the top of the page, so you can land
  up to a page earlier than you left off. This can't be avoided.
- **Legacy writes.** `.po` files written by plugin versions before 0.4 used
  `toc-split`. For technical books Moon+ reads them differently, so Moon+ may
  open those books in the wrong place until you move once in Moon+, which
  gives a fresh position. At the time of writing: Clean Code, Unity in
  Action, the Oxford Bible and Dependency Injection.

### Quick experiment to settle the open questions

Open *Unity in Action* in Moon+ without changing its position. Its `.po` says
chapter 12 at 21.9%, in the `toc-split` layout. If Moon+ shows about 22%,
Moon+ still uses `toc-split` for that book. If it shows much less,
`toc-all` is confirmed and the file was a legacy plugin write.

## Develop

```sh
calibre-debug tests/test_core.py      # CFI and Moon+ round trips on your real library (read only)
calibre-debug tests/test_e2e.py       # import -> export -> change detection on copies of the .po files
calibre-debug tests/score_layouts.py  # how well each chapter layout fits Moon+'s own positions (read only)
calibre-debug tests/diagnose.py       # what the plugin would do for recently viewed books (read only)
python build.py                       # dist/moonsync.zip
calibre-customize -b moonsync         # install from source
```

The plugin log is `<calibre config>/plugins/moonsync.log`. `IMPORT` lines
show the device stamp and the layout used, `LEARN` lines show layouts being
narrowed down, and a failed fit lists every layout's distance from Moon+'s
percentage.
