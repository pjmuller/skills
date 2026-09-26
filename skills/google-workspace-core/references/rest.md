# REST workflow details

Read structure before content: `slides-outline` → `slides-slide`; `doc-outline` → `doc-read`;
`sheet-meta` → bounded `sheet-read`. Re-read what you edited. Docs batches: apply index-changing
edits from the highest index down. Below: API behaviour the commands absorb, relevant when you drop
to `slides-batch` / `doc-batch` / `sheet-batch` / `api`. Implementations in `scripts/gws_core/`.

**Slides** (`slides.py`, `slides_ref.py`)
- Fresh placeholders inherit layout defaults, not the deck's run colours; `slides-add` copies
  title/body text colours from `--like` (default the `--after` slide).
- Concurrent editors shift slide numbers between calls: resolve anchors by objectId just before
  `slides-add --after` / `slides-move`, and re-check with `slides-outline` after bulk inserts. Two
  `slides-add --after X` calls land in reverse order; use one `--spec` list.
- `slides-set-text` (delete ALL + insert) loses run-level styling; prefer `slides-replace`.
- `createImage` fetches without our credentials, so private Drive files fail ("should be publicly
  accessible"). `slides-image` grants a temporary anyone-reader permission and revokes it in a
  `finally`. `size` needs both width and height; units are pt (slide 720×405; 1 pt = 12700 EMU).
- `updateSlidesPosition.insertionIndex` counts the deck before the move, moved slides included;
  `slides-move --to N` computes it. Don't hand-compute.
- Raw text: `shape.text.textElements[]` (`textRun` / `paragraphMarker` / `autoText`); `\n` ends a
  paragraph, `\v` is a soft break. Text can nest in `elementGroup.children`. Slides `insertText`
  takes `objectId` + `insertionIndex` (Docs: `location.index`); table cells need `cellLocation`
  (`slides-slide` prints the grid). `SLIDE_NUMBER` placeholders are filtered from titles.
- Speaker notes: write to `notesProperties.speakerNotesObjectId` (printed by `slides-slide`), not
  the notes page.
- `slides-thumbnail` downloads from `lh*.googleusercontent.com`: a sandbox egress allowlist needs
  `*.googleusercontent.com` besides `*.googleapis.com`. `slides-export-pdf` stays on googleapis.

**Docs**
- Markdown export escapes Markdown-ish characters (`>>` → `\>\>`); edit from `doc-outline`
  indexes, not the export. Content starts at index 1 (a `sectionBreak` occupies 0–1).

**Sheets**
- Default tab name is locale-dependent (`Sheet1` vs `Blad1`); a wrong one fails as
  `400 Unable to parse range`: run `sheet-meta` first.
- Writes use `USER_ENTERED` (formulas evaluate, dates/numbers coerce); `sheet-write --raw` for
  literal text. `sheet-read` returns strings in ragged rows (trailing empties omitted).

**Drive**
- Shared-drive files are invisible without `supportsAllDrives` (+ `includeItemsFromAllDrives`,
  `corpora=allDrives` on list/search); the core sends them on every call, raw `api` included.
- Some field masks reject dotted sub-selection (`fields=storageQuota.limit` on `/drive/v3/about`)
  with the misleading "The 'fields' parameter is required": drop the sub-field.
