# Moon+ Reader Sync for calibre

Read a book on your phone in [Moon+ Reader](https://www.moondownload.com/),
pick it up in calibre's e-book viewer where you left off, and the other way
round.

Moon+ Reader Pro can sync reading positions through Dropbox: it keeps one
small `.po` file per book in a Dropbox folder. This calibre plugin reads and
writes those files, so calibre's viewer and Moon+ share one reading position.

- Open a book in calibre and it starts at your Moon+ position, if that one
  is newer.
- Read in calibre and the position is saved back for Moon+, a few seconds at
  a time and when you close the viewer.
- Sync one book, a selection, or every book Moon+ knows, in either direction.

EPUB only. It needs calibre 6 or later on Windows, macOS or Linux.

## Install

1. Download `moonsync.zip` from the releases (or build it, see
   [Development](#development)).
2. In calibre: **Preferences → Plugins → Load plugin from file**, choose the
   zip, and restart calibre.
3. If the **Moon+ Sync** button does not show up, add it under
   **Preferences → Toolbars & menus**.

## Set up

1. In Moon+ Reader Pro, turn on syncing of reading positions through Dropbox.
2. Make sure Dropbox syncs that folder to your computer. Moon+ uses
   `Dropbox/Apps/Books/.Moon+/Cache`.
3. Open **Moon+ Sync → Settings...** in calibre and check the folder. The
   plugin fills it in when it finds Dropbox in the usual places. Any folder
   holding the `.po` files works, so other sync tools are fine too.

Put the **same EPUB file** on your phone that is in your calibre library,
ideally by sending it from calibre. Moon+ positions are chapter numbers and
character counts, so they only line up when both sides have the same file.
See [Troubleshooting](#troubleshooting).

## Use

The **Moon+ Sync** toolbar button:

| Action | What it does |
| --- | --- |
| Click, or **Read at Moon+ position** | Opens the selected book in the viewer, at the Moon+ position if that is newer |
| **Sync selected books** | For each selected book, the newer position wins |
| **Moon+ → calibre** / **calibre → Moon+** | Forces one direction for the selected books |
| **Sync every book that has a Moon+ position** | Does all of them at once |

Every sync shows a short report, book by book.

### Settings

- **Folder**: where the `.po` files are.
- **Always open books at their Moon+ position**: applies to every way of
  opening a book in calibre (double click, the View button, recent books),
  not just the plugin's button. On by default.
- **Always save the calibre viewer position to Moon+**: whenever the viewer
  saves your place, which is every few seconds while reading and when it
  closes, the plugin writes it for Moon+. On by default.
- **Create Moon+ position files for books that do not have one yet**: so a
  book you start in calibre opens at the right place in Moon+ too.

## How well it works

A Moon+ position is a chapter number plus a character offset. Moon+'s
"chapters" are not always the book's files. It also splits files at
table-of-contents entries, and there is no documentation of the exact rules.
The plugin works them out per book: it checks Moon+'s own percentage against
each way the book could be divided, and remembers what fits for each of your
devices.

Things to expect:

- **You may land up to a page early.** Moon+ saves the top of the page on
  screen, not the line you were reading.
- **Font size and screen size do not matter.** Positions are counted in
  characters, not pages.
- **When in doubt, nothing is written.** If a Moon+ position does not fit
  the book, calibre opens at Moon+'s percentage instead (close, but not
  exact), and the plugin will not write to that book's `.po` file. A wrong
  chapter number would send Moon+ somewhere else in the book.

## Troubleshooting

**The report says "approximate, from percentage"**, or a book opens in
roughly the right place but not exactly. Moon+'s chapter numbers do not fit
the EPUB in your library. Almost always the copy on your phone is a different
file: an older download, a different edition, or a version from before you
converted, polished or edited the book in calibre. calibre can also rewrite
a library file when it saves metadata into it. **Fix:** send the library's
copy to your phone again and open it once in Moon+.

**"not written: Moon+ chapter layout for this book is not understood"**: the
same cause. The plugin refuses to write rather than move you to the wrong
place in Moon+.

**Moon+ does not pick up the position.** Check that Dropbox has finished
syncing on both sides, and that the folder in Settings is the one Moon+
writes to. Moon+ checks for a synced position when you open the book.

**Nothing happens when the viewer saves.** Make sure **Always save the calibre
viewer position to Moon+** is on. Positions are only picked up while calibre
is running; what you read in the viewer while calibre was closed is not.

**Something else.** Every decision the plugin makes is written to
`moonsync.log` in the `plugins` folder of calibre's configuration
(**Preferences → Miscellaneous → Open calibre configuration directory**).
Please attach the relevant lines when reporting a problem.

## Files it touches

- The `.po` files in the folder you chose: read, written, and created for
  books that have none (if that setting is on).
- calibre's viewer position for each book, the same data the viewer itself
  saves.
- In calibre's configuration folder, under `plugins`: `moonsync.json`
  (settings), `moonsync_state.json` (what the plugin wrote and learned per
  book) and `moonsync.log`.

It does not modify your books and does not connect to the internet.

## Development

```sh
python build.py                       # build dist/moonsync.zip
calibre-customize -b moonsync         # install from source
calibre-debug -g                      # run calibre with console output
```

The scripts in `tests/` run against your own library and Moon+ folder (by
default the library calibre last opened and the folder in the plugin's
settings, or pass `<library> <moon folder>`). They do not change either one.

```sh
calibre-debug tests/test_core.py      # position conversions round trip
calibre-debug tests/test_e2e.py       # import, export and change detection, on copies of the .po files
calibre-debug tests/score_layouts.py  # how well each chapter layout fits the positions Moon+ wrote
calibre-debug tests/diagnose.py       # what the plugin would do for recently viewed books
```

How positions are converted, and what is known about Moon+'s format, is in
[docs/how-it-works.md](docs/how-it-works.md).

## License

GPL v3, like calibre. See [LICENSE](LICENSE).
