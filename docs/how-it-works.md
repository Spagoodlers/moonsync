# How it works

Notes for anyone working on the plugin or curious why a position lands where
it does. Moon+ Reader's `.po` format has no public specification. Everything
below comes from comparing real `.po` files with the EPUBs they belong to.

## Moon+ `.po` files

One file per book, named after the book file on the phone plus `.po`. For
books sent from calibre that is `<title> - <author>_<calibre uuid>.epub.po`,
with title and author cut to 31 characters. The plugin finds a book's file
by the UUID, and by title for files without one.

Contents: `<stamp>*<chapter>@<sub>#<offset>:<percent>%`, for example
`1700000000000*11@0#76306:55.3%`.

| Field | Meaning |
| --- | --- |
| `stamp` | 13 digits. The same for every book written from one device, so it is a device or install id, not a save time. The plugin keeps whatever stamp the file has, and uses the folder's most common one for new files. |
| `chapter` | Moon+'s chapter number. See [Chapter layouts](#chapter-layouts). |
| `sub` | Always `0` so far. |
| `offset` | Character offset into that chapter's text. It does not depend on font or screen size. Moon+ saves the first character of the page on screen. |
| `percent` | The progress Moon+ shows, from its own rendered layout. It is typically 0.3 to 3.5 points away from a text-based percentage (images and page breaks take space), so it can only rule layouts out, never place a position. |

Moon+ may also write `.an` files next to them (zlib-compressed highlights and
notes). The plugin does not use them.

## Chapter layouts

The chapter number is the hard part. The plugin knows three ways Moon+ may
divide a book (`core.LAYOUTS`, in order of preference):

1. **`toc-all`**: every table-of-contents anchor that has some text before
   it in its file starts a new chapter, whatever the file size. An anchor
   with only whitespace before it, usually the heading at the top of a file,
   does not start one.
2. **`toc-split`**: only files with more than 100,000 characters of text are
   split at their TOC anchors.
3. **`spine`**: one chapter per spine file.

For most novels, whose TOC points only at file starts, all three give the
same result. They differ for books whose TOC lists sections inside the
chapter files, which is typical of technical books. For those, recent Moon+
positions fit `toc-all` only. The `toc-split` rule came from older files, and
those turned out to match this plugin's own percentages exactly, so earlier
plugin versions had most likely written them. Versions before 0.4 used
`toc-split` only.

### Choosing a layout

For a Moon+ position, a layout is a candidate if the offset fits inside that
chapter and the text-based percentage there is within 5 points of Moon+'s
(`MAX_PERCENT_ERROR`). Wrong layouts are usually 10 or more points out.
Among the candidates the plugin takes:

1. a layout already learned for this book and device;
2. otherwise the first one in the list above that is within 1 point
   (`PERCENT_SLACK`) of the closest match.

If there is no candidate, the position is placed from Moon+'s percentage
alone, and the plugin refuses to write to that book's `.po` file. A wrong
chapter number would move the reader in Moon+.

### Learning

A position near the start of a chapter often fits several layouts. Each
position Moon+ writes narrows down which layouts the book uses on that
device, keyed by stamp. If a new position fits none of them, the list starts
over. Positions that match the plugin's own percentage exactly are skipped,
since they are almost certainly old plugin writes, not Moon+'s.

## What the plugin remembers

`moonsync_state.json` in calibre's `plugins` configuration folder, one entry
per `.po` file:

| Key | Use |
| --- | --- |
| `wrote`, `model` | The position the plugin last wrote and the layout it used. If the file still holds exactly that, it is not news from Moon+, even with a newer modification time (Dropbox can change those). Later writes keep the same layout. |
| `layouts` | Per device stamp, the layouts all positions Moon+ wrote are consistent with. |
| `book` | The book's shape (number of spine files, text length) when the above was recorded. If the library EPUB changes shape, `model` and `layouts` are no longer used. |

**Echo.** When Moon+ opens a position the plugin wrote, it saves the top of
that page: the same chapter, up to 3000 characters earlier (`ECHO_CHARS`).
Importing that would pull calibre back a page on every round trip, so it
counts as in sync. Reading on in Moon+ is still picked up, and forcing
Moon+ → calibre always imports.

## calibre's viewer

The viewer keeps its last position in
`<calibre config>/viewer/annots/<sha256 of the book's path>.json` as an EPUB
CFI, and opens at the newest `last-read` entry. `core.py` converts between
CFIs and text offsets the same way calibre's `src/pyj/read_book/cfi.pyj`
does. A text position is counted over the parent element's *direct* text,
starting from its first child, not from the text node itself.

The plugin finds out when the viewer saves by watching that folder for
changes every 5 seconds.

Which side is newer is decided by time: the `.po` file's modification time
against the viewer entry's timestamp. After a sync both get the same time.

## Known gaps

Things that can still put a position in the wrong place:

- **Different book files.** Chapter numbers only mean something for the exact
  EPUB Moon+ opened. A phone copy from before the book was converted,
  polished, replaced or had metadata embedded can have a different spine.
  This is the most common cause of positions that fit no layout. The fix is
  to send the library copy to the phone again.
- **Splitting by size.** Moon+ may split very large files that have no TOC
  anchors by size. Not confirmed, not modelled.
- **Skipped files.** Moon+ may leave the cover page or the EPUB 3 navigation
  document out of its chapter count. Not confirmed, not modelled.
- **What counts as a character.** Offsets count the raw text of the HTML,
  including source whitespace. If Moon+ collapses whitespace, positions deep
  inside chapters with a lot of indented code drift by up to the whitespace
  share, which can be 20% or more in programming books but under 1% in
  prose. Not confirmed either way.

`tests/score_layouts.py` scores every layout against the positions Moon+ has
written in your folder, leaving out the ones the plugin wrote. It is the
tool for testing new layout ideas.

## Log

`moonsync.log` in calibre's `plugins` configuration folder records every
decision:

- `COMPARE`: which side is newer, and why.
- `IMPORT`: the Moon+ position, the device stamp, and the layout used. If no
  layout fits, it also lists how far each one was from Moon+'s percentage.
- `LEARN`: layouts being narrowed down for a book.
- `EXPORT`: what was written and with which layout.

The log rolls over to `moonsync.log.old` at 1 MB.
