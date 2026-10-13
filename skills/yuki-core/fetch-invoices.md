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

## AWS: pure CLI, no browser
`scripts/aws-invoices --profile <aws profile> --out <dir> 2026-07 2026-08` lists the billing months via the AWS
Invoicing API and downloads every invoice PDF (`invoicing:ListInvoiceSummaries` + `GetInvoicePDF`, presigned URL,
15 min). File name = `aws-<account>-<YYYY-MM>-<invoice id>-<amount><cur>.pdf`; the PDF shows the company name,
verify it. Billing month = usage month: the card line of the 2nd of month M+1 matches billing month M; a mid-month
extra invoice (e.g. 26 Aug) is a separate line. The AWS profile per company lives in the wrapper's `yuki.json`
(`aws_profiles`, informational) and SKILL.md; profiles are in `~/.aws/credentials`, never in a repo.

## Learn a vendor from a screen recording
PJ records a CleanShot clip of one download (Bitwarden autofill → clicks → PDF). Turn it into recipe bullets:
```bash
transcribe-gemini --prompt prompt.md --thinking medium --out <clip>.transcript.md <clip>.mp4   # ~$0.02/min
```
Prompt: "screen recording of downloading an invoice from <vendor>; give a timestamped table of URL, exact element
label clicked, Bitwarden entry/email shown, invoice numbers/amounts; quote on-screen text, say 'unreadable' over guessing".
Send the CleanShot clip as-is (3 to 6 MB): Gemini samples 1 fps and bills per second whatever the file's fps
(27 s clip: original vs `shrink-video --preset normal` = same 8158 tokens, same steps, $0.013). `shrink-video` only over
20 MB; keep `--media-resolution high`. Reproduce once via CDP (route 2), then add to the wrapper's `vendor-recipes.md`:
`## vendor` · Bitwarden entry + account · billing URL · clicks · PDF URL pattern · card line text · which company.
Invoice rendered as HTML/modal without a PDF URL (e.g. Obsidian): route = print to PDF; say so in the recipe.
Delete the transcript afterwards; the recipe is the artifact.
