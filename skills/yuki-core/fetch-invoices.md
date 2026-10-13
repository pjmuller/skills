# Fetch missing invoices (before upload-invoices.md)

One thread does the whole quarter: learn a vendor from PJ's clip, fetch, upload, mark DONE. Start it in the
company repo (PB `pro-backup-backend`, KA `kampadmin`) so the wrapper's `yuki.json`, sheet and tenant apply.

## Order of routes per open row
1. **Gmail already has it**: `GWS gmail-search '<vendor> after:<quarter start>'` → `GWS gmail-attachments <id> -o <dir>`.
   Many vendors mail PDFs (Stripe receipts, webshops, forwards from colleagues/Klara).
2. **Supplier portal via PJ's logged-in Chrome** (CDP, background tab, no focus steal; precondition and tool notes in
   `macbook_setup/ai/t3-preview.md`). Recipe per vendor in the wrapper's `vendor-recipes.md`.
   ```bash
   chrome-devtools start --autoConnect
   chrome-devtools new_page '<billing url>' --background        # own tab; pageId from list_pages
   chrome-devtools evaluate_script "() => document.body.innerText.slice(0,1500)" --pageId <id>   # signed in? which account?
   chrome-devtools close_page <id>                              # only your tab; `chrome-devtools stop` at the end
   ```
   PDF behind the session: in the page, `fetch(url,{credentials:'include'})` → bytes → `btoa` → return as JSON; decode locally.
   `--output-format=json` wraps the value as `{"message":"…```json <value> ```"}`; parse that block. Keep one
   evaluate under ~1 MB; split months otherwise. Sites with a "print invoice" link: read the `<a>` hrefs first.
3. **Paper receipt** (restaurant, fuel, shop): PJ scans with his phone → Drive/Downloads; agent only matches + uploads.
4. **Expired session / unknown vendor**: name the Bitwarden entry from the recipe; PJ logs in (2FA) and says "ready".

Verify each PDF with `pdftotext -layout`: company name (Pro Backup BV / KampAdmin BV), amount, date match the row.
Save as `~/Downloads/vat-q<n>-<year>/<company>/<vendor>-<YYYY-MM-DD or period>[-<invoice no>].pdf`.
Then follow [upload-invoices.md](upload-invoices.md). Yuki duplicates are harmless; a wrong company is not.

Alternative delivery when the browser is unavailable: forward the PDF to the tenant's mail-in address
(wrapper SKILL.md), subject = vendor + period. Yuki confirms with "Je hebt een nieuwe … factuur ontvangen".

## Learn a vendor from a screen recording
PJ records a CleanShot clip of one download (Bitwarden autofill → clicks → PDF). Turn it into recipe bullets:
```bash
transcribe-gemini --prompt prompt.md --thinking medium --out <clip>.transcript.md <clip>.mp4   # ~$0.02/min
```
Prompt: "screen recording of downloading an invoice from <vendor>; give a timestamped table of URL, exact element
label clicked, Bitwarden entry/email shown, invoice numbers/amounts; quote on-screen text, say 'unreadable' over guessing".
Clips over 20 MB: `shrink-video` first. Reproduce once via CDP (route 2), then add to the wrapper's `vendor-recipes.md`:
`## vendor` · Bitwarden entry + account · billing URL · clicks · PDF URL pattern · card line text · which company.
Delete the transcript afterwards; the recipe is the artifact.
