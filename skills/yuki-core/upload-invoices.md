# Deliver invoices and mark DONE

Only on an explicit request. **Only route: the Yuki web upload** (T3 browser `preview_*` first, the user's
Chrome over CDP second). Tenant, login and mail-in come from the wrapper's `yuki.json` `web`
(missing → blocks delivery, not CSV reporting). A tenant showing the Visma Connect login is blocked:
ask the user to sign in to that tenant in the T3 browser and say "ready"; one login can serve several
tenants but the session is per subdomain. The mail-in address is reference only (suppliers and the user's
phone forward there; intake takes hours, never re-send), never an agent route.

Browser judgment and ambiguous scans: an Astra Medium agent. A smaller model may extract
vendor/date/amount/invoice number; verify the source image before accepting its match. Already
executing this task → don't spawn it again.

1. Verify the wrapper's company, administration and Workspace account. Read the sheet's actual
   headers and all rows via `gws.py`; filter DONE in memory (blank/FALSE open; boolean or formatted
   TRUE done).
2. Use the supplied Drive folder or local downloads. Match vendor (or verified trading name),
   currency/amount and invoice or transaction date; bank booking dates differ, so inspect the raw
   transaction date. Date/amount alone cannot resolve a contradictory vendor identity.
3. Keep a local manifest: Drive ID, filename/hash, `item_id`, matched row, document identity, upload
   status. Exclude duplicates, already-done and ambiguous items. An invoice absent from the sheet →
   check its quarter with `Y outstanding` (an outdated sheet is no proof of delivery); keep its
   document link, never fabricate a row or mark a different payment DONE.
4. Open `web.tenant_url` per the host's browser policy; verify the signed-in identity
   (`web.login_email`, top-right user menu) and administration. A logged-out page is not upload
   access; never substitute another company's account. Route: **Postbus → Aanleveren → Aankoop
   binder → Uploaden**.
5. Inspect the upload dialog and **Map = Aankoop** before attaching. Record accepted filenames and
   document links. An uncertain timeout is not a failure: inspect history before retrying, never
   blindly resubmit.
6. Only after acceptance, re-read the sheet, locate each row by `item_id` and set only its DONE cell
   to boolean TRUE (below).

**DONE means delivered, not booked.** Yuki processes uploads asynchronously; the outstanding list need
not shrink, so disappearance or a changed count is no upload proof. Leave missing, ambiguous and
failed documents unmarked; report the concrete remaining items. There is no unattended upload/OCR
pipeline: matching stays a verified agent decision.

## Sheet writes

`gws.py --config <wrapper-config>`: `sheet-meta` resolves the tab, `sheet-read` reads the full used
range (UI filters don't restrict it; keep each row's original grid index). Re-resolve `item_id`s right
before writing (sorting/inserting moves A1 coordinates). `sheet-batch-write` takes a range-to-values
JSON map: `[[true]]` per accepted row's DONE cell; never rewrite a compacted visible-rows list. Verify
with `api GET` on the values endpoint, `valueRenderOption=UNFORMATTED_VALUE`: booleans, and only the
intended cells changed. No browser cell editing.

## Yuki upload page (verified 2026-10-12/14)

- Direct URL: `<tenant>/domain/inbox/aspx/uploadarchive.aspx`. The binder picker lives in the
  same-origin iframe `name="Main"` (`iframe[src*="uploadarchive"]`): click the leaf whose text is
  `Aankoop` (`Ordner_OnClick(1)`), take a **fresh snapshot** (controls refresh), click **Uploaden** →
  `/domain/archive/upload-files/1` with `Map = Aankoop` and a **Bladeren** button.
- Selecting files is not delivery: check "N bestand(en) klaar om te uploaden" (names, count), click
  **Uploaden** once, wait for **Uploaden voltooid!**. Success lands on
  `/domain/aspx/UploadedFiles.aspx?Batch=<id>`, whose iframe lists filename, Map, Status "Open" and
  document links: save them in the manifest before editing DONE. The success toast may vanish.
- A navigation can make an evaluate call report failure although the click worked: check the URL
  before retrying.

**T3 preview** (preferred when its Yuki session is signed in): close the profile drawer after checking
identity (it covers Uploaden). Without a file-upload tool, serve only the PDFs from a throwaway folder
(never `~/Downloads` itself) through a loopback CORS server (`Access-Control-Allow-Origin: *`, free
port: `lsof -iTCP:<port>`, other agents run servers too; run it as a background Bash task, see
[fetch-invoices.md](fetch-invoices.md)). One `preview_evaluate`: `fetch` each file, `new File([blob],
name)`, add to a `DataTransfer`, assign it to `input[type=file].files`, dispatch a bubbling `change`;
a second evaluate checks `Map` and clicks Uploaden; `preview_wait_for urlIncludes UploadedFiles.aspx`.
Kill the server afterwards. Base64 through evaluate only as fallback (each expression < 64,000
characters, never print payloads).

**Chrome over CDP** (where host policy permits logged-in Chrome): `chrome-devtools start
--autoConnect`, find the tenant with `list_pages`, open your own tab with `new_page <url>
--background`, verify the profile identity. `upload_file <pageId> <Bladeren-uid> <pdf...>` attaches
several files (UIDs from the current `take_snapshot`). Close only your tab, then `chrome-devtools stop`.
