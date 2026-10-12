# Deliver invoices from a folder

Use an Astra Medium agent for browser judgment and ambiguous scans. A smaller model may extract
vendor/date/amount/invoice number, but verify the source image before accepting its match.
Use the current session when already executing this task; do not spawn the same task again.

1. Verify the wrapper's company, administration and Workspace account. Use its Workspace API
   CLI for Drive downloads and all Sheet reads/writes. Read actual headers and all rows; filter
   DONE in memory (blank/FALSE are open; boolean TRUE or formatted "TRUE" are done).
2. Download the supplied Drive folder or use the supplied local downloads; inspect PDFs/images. Match vendor or verified trading name,
   currency/amount and invoice or transaction date. Bank booking dates can differ: inspect the
   raw transaction date. Date/amount alone cannot resolve a contradictory vendor identity.
3. Keep a local manifest: Drive ID, original filename/hash, sheet item_id, matched row,
   document identity and upload status. Exclude duplicates, already-done and ambiguous items.
   For invoices absent from the sheet, check the matching quarter with `Y outstanding`; an
   outdated sheet is not evidence that the invoice was delivered. Keep accepted document links
   for those invoices; do not fabricate a row or mark a different payment DONE.
4. Open the wrapper's Yuki tenant. Follow the host's browser policy; verify the signed-in
   identity and administration. A logged-out page is not upload access. Never substitute a
   different company's account. Route: **Postbus → Aanleveren → Aankoop binder → Uploaden**.
5. Inspect the current upload dialog and selected purchase destination before attaching files.
   Use a supported browser file-upload mechanism, or computer use for the native file picker.
   Record accepted filenames/receipts or history entries. An uncertain timeout is not a failure:
   inspect history before retrying, never blindly resubmit.
6. Only after acceptance, re-read through the API and locate each row by stable item_id. Update
   only its DONE cell to boolean TRUE; verify typed readback and unchanged unrelated cells.

**DONE means delivered, not booked.** Yuki processes uploads asynchronously; the outstanding
invoice list need not shrink. Do not use disappearance or a changed count as upload proof.
Leave missing, ambiguous and failed documents unmarked; report the concrete remaining items.

## Sheets API mechanics

Use `gws.py --config <wrapper-config>`: `sheet-meta` resolves the tab; `sheet-read` reads the
full used range. UI filters do not restrict these values: keep each row's original grid index
while filtering in memory. No browser cell editing or filter-view manipulation is needed.

Re-resolve unique `item_id`s immediately before writing because sorting/inserting rows changes
A1 coordinates. `sheet-batch-write` accepts a JSON range-to-values map; send `[[true]]` for each
accepted row's single DONE cell. Never rewrite a compacted list of visible rows over the sheet.
Verify via `api GET` on the Sheets values endpoint with `valueRenderOption=UNFORMATTED_VALUE`
that the results are booleans; compare the full readback to ensure only intended cells changed.

## Browser mechanics verified 2026-10-12

- Clicking **Aankoop** refreshes controls inside a legacy iframe: take a fresh snapshot before
  clicking **Uploaden**. It redirects to `/domain/archive/upload-files/1`; confirm **Map = Aankoop**.
- **Bladeren** selects files; selection is not delivery. Verify filenames and count, then click
  **Uploaden** once. Wait for **Uploaden voltooid!** and the accepted count.
- Success redirects to `/domain/aspx/UploadedFiles.aspx?Batch=<id>`. The batch lists uploader,
  timestamp, individual document links and **Aankoop**. Save those links in the manifest before
  editing DONE. The transient success notification may disappear by itself.
- Where host policy permits logged-in Chrome: `chrome-devtools start --autoConnect`, find the
  tenant with `list_pages`, select it without bringing it forward, then open your own tab with
  `new_page <url> --background`. Verify profile identity in the top-right user menu.
  `upload_file <pageId> <Bladeren-uid> <paths...>` attaches multiple files; obtain UIDs from
  each current `take_snapshot`. Close only your created tab, then stop the CLI daemon.

## Reusable tooling

The maintained Python tools are `scripts/yuki.py` (read-only outstanding payments and append-only
sheet reporting) and the wrapper's Google Workspace core `gws.py` (Drive and targeted Sheets
operations). Run `scripts/install --check` for Yuki readiness. Browser uploads follow this recipe;
there is no unattended upload/OCR pipeline. Invoice matching remains a verified agent decision.
Company/account IDs stay in each `yuki` wrapper; consumer repos carry committed core copies.
