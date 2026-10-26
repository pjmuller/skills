---
name: yuki-core
description: "Use for \"push the Yuki list\", \"which payments still need an invoice\", \"fetch/upload the missing invoices\" or \"close the quarter\": Yuki's bank/card payments missing a purchase invoice, as CSV or the company's quarter tab in a Google Sheet. Run through the repository's yuki wrapper (yuki.json)."
---

# Yuki core: unmatched payments per quarter

**Intent.** Every quarter the accountant needs an invoice for each bank/card payment Yuki could not
match. This core lists those payments and appends them to a shared sheet tab where people fill the
manual columns (who, status, comment). One thread per quarter does list → fetch → upload → DONE → mail:

| Step | Open |
|---|---|
| Find each invoice (Gmail, supplier portals, AWS CLI, learn a vendor from a screen recording) | [fetch-invoices.md](fetch-invoices.md) |
| Upload to Yuki (explicitly authorized only) and mark DONE in the sheet | [upload-invoices.md](upload-invoices.md) |
| Status mail to the accountant | [close-quarter.md](close-quarter.md) |

**Hard rules.** The SOAP client is read-only: API keys carry write rights, so the `ALLOWED` allowlist
in `scripts/yuki_core/client.py` is the safety net; browser delivery never widens it. Company ids,
accounts, sheet and tenant live only in the private wrapper.

Code: `scripts/yuki.py` (CLI); `scripts/yuki_core/`: `client.py` (zeep), `outstanding.py` (parse,
clean, quarter selection, CSV), `sheet.py` (append-only push via the google-workspace-core CLI).
Readiness: `scripts/install --check`.

## Commands

From the wrapper's repository through `mise exec --` (it loads the API key env var):

```bash
Y() { mise exec -- uv run --quiet --project .agents/skills/yuki-core .agents/skills/yuki-core/scripts/yuki.py --config .agents/skills/yuki/yuki.json "$@"; }
Y outstanding --quarter 2026-Q3 --csv /tmp/out.csv   # stdout without --csv
Y sheet-push --quarter 2026-Q3 --dry-run             # then without --dry-run; --tab "<name>" for a scratch tab
Y discover                                           # domains + administrations for a new wrapper
```

`--quarter` defaults to the last closed quarter.

## Wrapper config (`yuki.json`)

[templates/yuki.example.json](templates/yuki.example.json) shows every key. `api_key_env` names the env
var, never the key. `sheet: null` = CSV only. `gws` = google-workspace-core `gws.py` + a Sheets-capable
`workspace.json` (absolute, `~`, or relative to yuki.json; `--gws` / `--gws-config` override).
`aws_profiles` and `web` (tenant, login, mail-in) are read by agents, not code.

## Behaviour worth knowing

- **Data = items open today**, not a quarter-end snapshot; a quarter takes the rows dated inside it.
  Booked purchase invoices (`Aankoopfactuur`) are dropped (Yuki's screen hides them); payments of both
  signs stay (refunds are positive).
- **Append-only.** The first push creates the tab (header, frozen row, basic filter by
  description_clean then newest date). Later pushes require the exact header, append only unseen
  `item_id`s (Yuki `Item/@ID`), extend the filter and never touch existing cells. A row that
  disappears from Yuki is *not* marked done and existing amounts can go stale: Yuki stays the truth.
- **Seeding.** New rows matching one-to-one a row of the newest earlier quarter tab (by `item_id`, or
  for legacy tabs date + original_amount + description_raw) get its manual cells copied once.
- **Formula columns** (optional, first): `{name, rules: [{label, pattern}]}` → a per-row
  `=IFS(REGEXMATCH(contact&" "&description_clean, pattern), label, …)` "who probably owns this" hint,
  written with the sheet locale's argument separator (`;` for comma-decimal locales); never seeded,
  overwrite by hand freely.
- **Vendor notes** (optional `lookup_columns: [{name, tab}]`): a human-kept tab (`match, How to find,
  Owner`, created if missing) with one note per vendor that survives quarters; each row shows the first
  note whose `match` regex hits contact + description_clean. Order specific before broad (Yuki books
  Google Ads under the "Linkedin Ireland" contact, so not a contact lookup). Keep notes generic
  ("account > avatar > billing"): billing UIs change every quarter.
- **Fails closed** on malformed amounts or dates, an unexpected response shape, missing or duplicate
  item ids, a header mismatch, or a read-back that does not show every new id exactly once.

Out of scope: per-person filter views, DONE from disappearance in Yuki, accounting postings.

## Yuki API gotchas

- Generic host `https://api.yukiworks.be/ws/<Service>.asmx`; tenant hosts (`l0000-<name>.yukiworks.be`)
  reject web-service calls. NL tenants use `api.yukiworks.nl`.
- SOAP names are case-sensitive: `sessionID`, `administrationID`; `sessionId` gives a misleading
  "Invalid session ID".
- Quota 1000 calls/day; one run costs 3 (Authenticate, SetCurrentDomain, OutstandingCreditorItems).
- Docs: [Yuki API (BE)](https://support.yuki.be/en/support/solutions/articles/80000787603-yuki-api-documentation),
  [Accounting web service](https://support.yuki.nl/en/support/solutions/articles/80000785926-accounting-web-service).
