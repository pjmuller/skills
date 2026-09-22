# REST workflow details

Run `gws.py --config <wrapper>/workspace.json --help` for the full command set. Read structure first:
`slides-outline` → `slides-slide`; `doc-outline` → `doc-read`; `sheet-meta` → bounded `sheet-read`.
`--json` is raw except documented compact summaries; text exports remain text.

Only requested writes. Re-read edited ranges/slides. For Docs batches, apply index-changing
edits from highest index downward. `slides-delete` requires `--yes`; Drive removal uses trash.

**Slides**
- `slides-add` = createSlide + placeholder text + bullets + notes in one go. It copies the
  title/body **text colours** from the `--after` slide (`--like N` / `--like none`): a fresh
  placeholder only inherits the layout defaults (black title, grey body), not the deck's green/navy
  run styling. Bullets: newline = bullet, leading tab = nesting level.
- Images: `createImage` fetches the URL **without our credentials**, so a freshly uploaded (private)
  Drive file is always rejected with "should be publicly accessible" — verified. `slides-image`
  therefore grants a temporary `anyone/reader` permission, retries, and revokes it in a `finally`
  (the pixels are copied into the deck; the Drive file stays the editable source). With that
  permission `drive.google.com/uc?id=<id>` works fine.
- `createImage`'s `size` needs **both** width and height (a half-filled one fails as "Unknown
  dimension unit UNIT_UNSPECIFIED"). With only `--w` or only `--h`, `slides-image` creates the image
  at natural size and then rescales uniformly via `updatePageElementTransform` (ABSOLUTE), which is
  how it keeps the aspect ratio. Sizes/offsets are in **pt** (slide = 720×405 pt; 1 pt = 12700 EMU).
- `updateSlidesPosition.insertionIndex` is a 0-based position in the deck **before** the move, with
  the moved slides still counted; `slides-move --to N` translates "become slide N" by inserting
  after the (N-1)th non-moved slide. Don't hand-compute it.
- When several people edit a deck at once, so **slide numbers shift between calls**: resolve
  the anchor by objectId right before `slides-add --after` / `slides-move`, and re-check with
  `slides-outline` after a bulk insert (a block inserted "after 38" once landed before its cue
  slides because two slides had been added above it minutes earlier). Two `slides-add --after X`
  calls in a row land in reverse order (each goes directly after X); pass a `--spec` list to insert
  several slides in order.
- Text lives in `shape.text.textElements[]`, each with `textRun` (content + style),
  `paragraphMarker` (bullets/paragraph style) or `autoText` (slide number). Concatenating only
  `textRun.content` is what `slides-*` does; `\n` ends a paragraph, `\v` is a soft line break.
- `insertText` on Slides takes `objectId` + **`insertionIndex`**; Docs takes `location.index`.
  `deleteText` takes `textRange: {type: "ALL"}` or `FIXED_RANGE` + start/endIndex.
- Table cells need `cellLocation: {rowIndex, columnIndex}` on insert/delete text; `slides-slide`
  prints the cell grid so you can count.
- `slides-set-text` = `deleteText(ALL)` + `insertText(0)`. The new run inherits the
  shape/placeholder defaults, so **run-level styling may be lost** (placeholder-level colours
  survive). Prefer `slides-replace` for a wording change; restyle with `updateTextStyle` if needed.
- Slide references resolve in `gws_core/slides_ref.py`: an all-digit token is a 1-based slide
  number, anything else an objectId; `parse_slides_url` pulls deck + slide out of `?slide=id.X` or
  `#slide=id.X`. `slides-resolve` prints the pair plus a link back.
- Placeholders matter: `SLIDE_NUMBER` shapes contain the page number and are filtered from titles
  and `slides-text`; `TITLE`/`CENTERED_TITLE` is what the outline shows.
- Elements can be `elementGroup`s — text is nested in `children` (the CLI recurses).
- Speaker notes are on `slideProperties.notesPage`; write to
  `notesProperties.speakerNotesObjectId` (printed by `slides-slide`), not to the page.

- `slides-thumbnail` downloads from `lh*.googleusercontent.com`, outside the `*.googleapis.com`
  hosts everything else uses; a sandbox egress allowlist must include `*.googleusercontent.com`
  or thumbnails fail with a network error naming that host. `slides-export-pdf` stays on
  googleapis.com.

**Docs**
- Markdown export escapes markdown-ish characters (`>>` → `\>\>`) and starts with a UTF-8 BOM
  (the CLI strips it). Use `doc-outline` + indexes as the source of truth for editing, not the
  exported Markdown.
- The body always starts with a `sectionBreak` at 0-1; real content starts at index 1.

**Sheets**
- Tab name is locale-dependent: a spreadsheet **created via the API** gets `Sheet1`, one created in
  a Dutch UI gets `Blad1`. A wrong tab name fails as `400 Unable to parse range` — run
  `sheet-meta` first.
- `USER_ENTERED` (what we use) evaluates `=SUM(...)` and coerces dates/numbers; use `sheet-write --raw`
  when you need literal text.
- `sheet-read` returns strings and **ragged rows** (trailing empty cells are omitted).

**Drive**
- Every Drive call sends `supportsAllDrives=true`; list/search also send
  `includeItemsFromAllDrives=true` + `corpora=allDrives`. Without those, shared-drive files are
  invisible — shared-drive files need both flags.
- `drive-copy --parent` into a shared drive folder works (no need to detour via My Drive).
- Field masks: some methods reject dotted sub-selection (`fields=storageQuota.limit` on
  `/drive/v3/about`) with the misleading `The 'fields' parameter is required for this method`.
  Drop the sub-field.
