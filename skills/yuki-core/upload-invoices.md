# Deliver invoices from a folder

Use an Astra Medium agent for browser judgment and ambiguous scans. A smaller model may extract
vendor/date/amount/invoice number, but verify the source image before accepting its match.
Use the current session when already executing this task; do not spawn the same task again.

1. Verify the wrapper's company, administration and Workspace account. Read the actual tab
   headers and all rows, including filtered-out rows. Candidates have DONE other than TRUE.
2. Download the supplied folder; inspect PDFs/images. Match vendor or verified trading name,
   currency/amount and invoice or transaction date. Bank booking dates can differ: inspect the
   raw transaction date. Date/amount alone cannot resolve a contradictory vendor identity.
3. Keep a local manifest: Drive ID, original filename/hash, sheet item_id, matched row,
   document identity and upload status. Exclude duplicates, already-done and ambiguous items.
4. Open the wrapper's Yuki tenant. Follow the host's browser policy; verify the signed-in
   identity and administration. A logged-out page is not upload access. Never substitute a
   different company's account. Route: **Postbus → Aanleveren → Aankoop binder → Uploaden**.
5. Inspect the current upload dialog and selected purchase destination before attaching files.
   Use a supported browser file-upload mechanism, or computer use for the native file picker.
   Record accepted filenames/receipts or history entries. An uncertain timeout is not a failure:
   inspect history before retrying, never blindly resubmit.
6. Only after acceptance, re-read the sheet and locate each row by stable item_id. Update only
   its DONE cell to boolean TRUE. Read back typed values and verify other cells are unchanged.

**DONE means delivered, not booked.** Yuki processes uploads asynchronously; the outstanding
invoice list need not shrink. Do not use disappearance or a changed count as upload proof.
Leave missing, ambiguous and failed documents unmarked; report the concrete remaining items.

Validation boundary: route confirmed from the supplied Yuki purchase-screen reference; upload
dialog and acceptance controls must be inspected live. Do not invent selectors or claim that a
reference screenshot proves an upload succeeded. Company URLs and tested UI details belong in
its wrapper; no private account or sheet IDs in this public core.
