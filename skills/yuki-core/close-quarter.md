# Close the quarter: status mail to the accountant

After the uploads, PJ sends Jona Vandebosch (PKF Bofidi, Jona.Vandebosch@pkfbofidi.com) one short status mail
for all companies. Draft with the google-workspace-personal CLI (`gmail-draft` / `gmail-draft-update`, never
send); PJ reviews in Gmail. PJ may edit the draft himself: read it back (`gmail-draft-get`) before every update.

## Format (PJ's rules, 2026-10-13)
- Subject `BTW Q<n> - <year>: KampAdmin - Momentum Tools - ProBackup`. Dutch, informal: "Dag Jona," … "Toy toy toy :)", signature once.
- One section per company: header **bold + underlined** (`<b><u>Pro Backup</u></b>`), so pass `--html-file` with the
  HTML alternative next to the plain `--body-file` (plain text cannot underline). Order: Pro Backup, Momentum Tools, KampAdmin.
- Anomalies only, as `-` bullets, one row per bullet: `DD-MM € -bedrag Leverancier: waarom + what Jona should do`
  ("up to you, mag als privé kost / RC zaakvoerder", "komt via Peppol", "verkeerde rekening, transfer gedaan").
  Group identical cases in one bullet ("16-07 € -71,56 Gabriels en 28-08 € -22,50 Excelsior: bonnetjes kwijt").
- Not in the mail: what was uploaded (also last-minute scans), how an invoice looks (private account, missing
  company name): Jona reacts if something is insufficient. "Alles geüpload, op deze na:" is the whole status.
- Other recurring topics when relevant: Stripe revenue caveats (refunds, voids, open customer balances), scans
  paid privately that must flow back via RC zaakvoerder, a company's list still being finished by a colleague
  ("Tobias laadt de laatste facturen vandaag op").
- Before drafting: `Y outstanding --quarter <q>` per company for the real open list (PB/KA also have the sheet;
  Momentum has no sheet, its list is short). Rows DONE in the sheet but still listed by Yuki are fine (async).
- Examples in Gmail: "BTW Q2 - 2026: …" (2026-07-13), "BTW Q3 - 2026: …" (2026-10-13), thread "Accounting Q1" (2026-04).
