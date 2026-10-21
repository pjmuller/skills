# Close the quarter: status mail to the accountant

After the uploads, the owner sends the accountant one short status mail (one for all companies they run).
Recipient, subject, company order and examples are owner-specific: the wrapper's `SKILL.md` links them
(keep names and amounts out of this public core). Draft only, never send; the owner may edit the draft,
so read it back before every update.

## Format
- Anomalies only. "Alles geüpload, op deze na:" is the whole status; one section per company.
- One `-` bullet per payment: `DD-MM € -amount Vendor: why + what the accountant should do`
  ("up to you, private cost", "comes via Peppol", "wrong account, transfer done"). Group identical cases.
- Leave out what was uploaded and how an invoice looks: the accountant reacts if something is insufficient.
- No fixed greeting/closing formula beyond the owner's signature; copy tone, not phrases, from earlier mails.

## Before drafting (same day)
- `Y sheet-push --quarter <q> --dry-run`, then push: Yuki books bank/card lines late (a payment dated in the
  quarter can appear a week after the first push; card statements uploaded by hand add a batch). The first
  push is a snapshot, not the final list.
- `Y outstanding --quarter <q>` per company is the real open list. Rows DONE in the sheet but still listed by
  Yuki are fine (async). Rows a `Likely resp` rule labels as "no invoice needed" still need one when Yuki
  lists them: check those before the mail.
