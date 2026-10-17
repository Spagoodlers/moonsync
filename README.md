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
- `stamp` is shared by many books, so it looks like a device/install id. It
  is kept as is, never set to the current time.
- `chapter` is the spine index. Moon+ splits big HTML files (more than about
  100k characters of text) at their TOC anchors, and each piece then counts
  as a chapter.
- `offset` is the character offset into that chapter's body text.
- `percent` is used only to check that a chapter layout is right.

The `.an` files next to them are zlib-compressed highlights and notes. They
are not used yet.

### calibre viewer

The viewer stores its last position in
`%APPDATA%/calibre/viewer/annots/<sha256(book path)>.json` as an EPUB CFI,
and opens at the newest `last-read` entry. `core.py` converts between CFIs
and text offsets the same way calibre's `read_book/cfi.pyj` does. A text
position is counted over the parent element's *direct* text, starting from
its first child.

### Safety

When a Moon+ position fits no known chapter layout (within 2% of Moon+'s own
percentage), importing falls back to the percentage. In that case the plugin
**refuses to write** to that book's `.po`, because a wrong chapter number
would move you in Moon+.

## Develop

```
calibre-debug tests/test_core.py   # CFI and Moon+ round trips on your real library (read only)
calibre-debug tests/test_e2e.py    # import -> export on copies of the .po files
python build.py                    # dist/moonsync.zip
calibre-customize -b moonsync      # install from source
```
