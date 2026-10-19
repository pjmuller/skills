# Prompt shape: two examples

Neutral fixtures (names, ids and paths invented). Keep this order for every type; adapt the
case, actions, authorization, verification and lifecycle to the outcome. Write in the call's
language. Not a template to fill: drop what an item doesn't need.

## A bug seen in the call

```md
# Booked slot still confirmed

In the call (06:22): Sam showed a reply flagged in feedback. Patient: "OK for Monday 14 Dec 10:15".
The front desk had already answered by hand that the slot was just taken online; our draft four
minutes later still said "Your appointment is confirmed". Feedback 1/5: "the bot should have seen it was taken".

Broader: the run knew (`slot_explain` → occupied, nothing booked) and confirmed anyway; why the
answer ignored it remains open. A taken slot never gets a confirmation, for every customer.

Next steps
1. After selection: replay the run; compare the rules then and now.
2. Smallest general fix: taken → offer alternatives.
3. Test a taken and a free slot; update the existing ticket, no duplicate.

---
For the agent: owner Alex · class coding · lifecycle settle when done after selection. Repo
`~/code/acme/assistant-brain`; read `AGENTS.md`, `.agents/skills/debug-run/SKILL.md`. No customer-specific
branch, no writes to the booking system while diagnosing. Run `r-1234`, ticket `T-42`. Tests,
opposite-model review, commit/push, verify live. Source: call link · 06:22–07:14 · transcript path (raw ASR).
```

## A request, not a bug

```md
# Ask the vendor for the insurance document

In the call (43:00): Sam showed the proof-of-insurance a patient needs; it is generated inside
the vendor's software and we cannot produce it. Alex: "add it to the vendor feature-request list".
Meanwhile drafts tell the desk to fetch it by hand.

Broader: one clear question to the vendor (can we fetch that existing document as an attachment?),
not an endpoint design. The closest open request is about email templates, a different outcome.

Next steps
1. After selection: check the list for duplicates; get the document's official name from Sam.
2. Create or extend one request: backlog, owner Alex. No message to the vendor.

---
For the agent: owner Alex · class ops · lifecycle settle when done after selection. Repo
`~/code/acme/ops`; read `.agents/skills/tickets/SKILL.md`. List `vendor-requests`. Don't invent
an API contract or mark it requested. Source: call link · 43:00–43:50.
```
