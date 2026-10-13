# Close the quarter: status mail to the accountant

After the uploads, PJ sends Jona Vandebosch (PKF Bofidi, Jona.Vandebosch@pkfbofidi.com) one short status mail
for all companies. Draft it with the google-workspace-personal CLI (`gmail-draft`, never send); PJ reviews in Gmail.

- Subject: `BTW Q<n> - <year>: KampAdmin - Momentum Tools - ProBackup`. Dutch, informal ("Dag Jona," … "Toy toy toy :)"), PJ's signature once.
- One section per company (Pro Backup, Momentum Tools, KampAdmin), `-` bullets, anomalies only: what is still
  missing and why (lost receipt, private mailbox, subscription cancelled), what Jona may book as private cost
  ("up to you, mag als privé kost / RC zaakvoerder"), payments made from the wrong company account, invoices that
  arrive by Peppol later, Stripe/revenue caveats (refunds, voids, open customer balances), scans paid privately
  that must flow back via RC zaakvoerder. Nothing uploaded fine needs a line; "alles geüpload" is enough.
- Before drafting: `Y outstanding --quarter <q>` per company for the real open list (PB/KA also have the sheet;
  Momentum has no sheet, its list is short). Rows DONE in the sheet but still listed by Yuki are fine: Yuki
  processes asynchronously.
- Examples in Gmail: "BTW Q2 - 2026: KampAdmin - Momentum Tools - ProBackup" (2026-07-13), Q1 thread "Accounting Q1" (2026-04).
