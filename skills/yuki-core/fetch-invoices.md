# Fetch missing invoices (before upload-invoices.md)

Start the quarter's thread in the company's repository so its wrapper's `yuki.json` (ids, sheet, `web`)
and `vendor-recipes.md` (per vendor: Bitwarden entry + account, billing URL, clicks, PDF URL pattern,
card line text, company) apply.

## Routes per open row, in order
Loop: in the quarter tab filter the owner column (formula hint) to yourself, keep the done/status
column empty, sort by description_clean A→Z; per vendor match each row's **date** (and amount) to an
invoice and download only those.

1. **Gmail already has it**: `GWS gmail-search '<vendor> after:<quarter start>'` → `GWS
   gmail-attachments <id> -o <dir>`. Many vendors mail PDFs (Stripe receipts, webshops, colleagues' forwards).
2. **Supplier portal in the T3 browser**, signed-in profile per host policy (`preview_open {profileId,
   open:false}`, then `fetch(url,{credentials:'include'})` → `blob` → `<a download>`.click() via
   `preview_evaluate`; `preview_status` `downloads[].path` holds the bytes, nothing passes through the
   model; verified 2026-10-18). The user's real Chrome over CDP only with their OK for this run: every attach
   pops Chrome's consent modal (host browser policy). CDP variant:
   ```bash
   chrome-devtools start --autoConnect
   chrome-devtools new_page '<billing url>' --background        # own tab; pageId from list_pages
   chrome-devtools evaluate_script "() => document.body.innerText.slice(0,1500)" --pageId <id>   # signed in? which account?
   chrome-devtools close_page <id>                              # only your tab; `chrome-devtools stop` at the end
   ```
   PDF behind the session: in the page `fetch(url,{credentials:'include'})` → `btoa` → return as JSON;
   decode locally. `--output-format=json` wraps the value as `{"message":"…```json <value> ```"}`; parse
   that block. Keep one evaluate under ~1 MB (split months). "Print invoice" sites: read the `<a>` hrefs first.
3. **Paper receipt** (restaurant, fuel, shop): the user scans it with a phone → Drive/Downloads; agent only matches + uploads.
4. **Expired session / unknown vendor**: name the Bitwarden entry from the recipe; the user logs in (2FA) and says "ready".

Verify each PDF with `pdftotext -layout`: company name (`company_label` entity), amount and date match
the row. Save as `~/Downloads/vat-q<n>-<year>/<company>/<vendor>-<YYYY-MM-DD or period>[-<invoice no>].pdf`,
then [upload-invoices.md](upload-invoices.md). Yuki duplicates are harmless; a wrong company is not.

## PDF bytes out of a T3 browser tab (verified 2026-10-14)
Never return file bytes through `preview_evaluate` (a 47 KB PDF is 63 KB of base64 per call, burning
context twice). Run a tiny loopback HTTP server (`python3 -I server.py`) **as a background Bash task**
(a `nohup … &` inside a normal Bash call dies with the call) and move bytes to it:
- Page without a CSP (Yuki itself): `fetch('http://127.0.0.1:<port>/…')` works both ways.
- Page with a CSP (Sentry: `connect-src`, `frame-src`): fetch and iframes to localhost are blocked, a
  **top-level form POST** is not (`form.target='_top'`, hidden `name` + base64 `b64` fields,
  `application/x-www-form-urlencoded`). Submit, wait for `urlIncludes 127.0.0.1`, navigate back; vendor
  cookies survive. One file per round trip.
- Sentry receipts: same-origin `/organizations/<org>/payments/<id>/pdf/` (the API's `us.sentry.io` URL is cross-origin).
- HTML-only invoices (Mapbox console, Obsidian modal): `preview_resize` to the page height,
  `preview_snapshot save=true`, `sips -s format pdf`; say so in the recipe.
Stop the server and delete its directory afterwards.

## AWS: pure CLI
`scripts/aws-invoices --profile <aws profile> --out <dir> 2026-07 2026-08` downloads every invoice PDF
of those billing months (Invoicing API `ListInvoiceSummaries` + `GetInvoicePDF`), named
`aws-<account>-<YYYY-MM>-<invoice id>-<amount><cur>.pdf`; verify the company name in the PDF. Billing
month = usage month: the card line of the 2nd of month M+1 matches billing month M; a mid-month extra
invoice is a separate line. Profiles: wrapper `aws_profiles`, credentials in `~/.aws/credentials`,
never a repo. No invoices for a quarter is normal when the company buys AWS through a reseller (its
mailed invoice is forwarded to Yuki; the recipes say which).

## Learn a vendor from a screen recording
The user records a screen clip of one download (Bitwarden autofill → clicks → PDF):
```bash
transcribe-gemini --prompt prompt.md --thinking medium --out <clip>.transcript.md <clip>.mp4   # ~$0.02/min
```
Prompt: "screen recording of downloading an invoice from <vendor>; give a timestamped table of URL, exact
element label clicked, Bitwarden entry/email shown, invoice numbers/amounts; quote on-screen text, say
'unreadable' over guessing". Send the clip as-is: Gemini samples 1 fps and bills per second regardless of
the file's fps (shrinking saved nothing on a 27 s clip); `shrink-video` only over 20 MB; don't lower
`--media-resolution` (default high). Reproduce once (route 2), add the recipe to `vendor-recipes.md`, delete the
transcript: the recipe is the artifact.
