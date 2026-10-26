# Go deep, whoever runs it

Developer or product owner at the keyboard, the agent debugs as far as this machine allows: product
code, every project repo and doc, the brain, read-only production data/logs/traces, a live
reproduction. A draft deferring to engineering is a research gap ([recipe](reviewer.md)): one
`delegate_task` per deep case, then a reply with the cause and a step the customer can take today.
Only facts that stay unknowable go to the developer: one ticket of one-line questions, drafted reply
attached. **Say what limited you:** a missing env var, credential, CLI, repo or access, or a
timed-out query → a "What limited this review" line naming who can grant it (wrapper); answer with
what is reachable, never settle silently for a shallower answer.

## Escalate only what research cannot settle

Rare; each names the exact question.
1. *Decisions:* money (refund, discount, void), contract or legal commitments, commercial offers, a
   policy change customers will see.
2. *Writes beyond a scoped one-customer fix:* infra, bulk data, irreversible deletion, deploys, publishing.
3. *Facts outside every reachable system:* an unlogged call or chat, an admin console without access,
   a vendor's private state, why code was deliberately disabled when git history does not say.
4. *Human hands:* login, phone, eID, payment, signature; sending or deleting mail.

## Shipping a found fix

A PR with tests on the critical path and an opposite-model review, whoever operates. A product
owner's agent fixes low-hanging fruit (clear cause, contained change, tests green) and lands it per
the repo's rules in that run; escalate to the developer only without a clear path (cause unclear,
change broad or risky, infra/migration/security), with evidence and the exact question. Deploys
follow the repo's rules; verify live. A data fix scoped to one customer (one account or backup,
reversible, low regression risk) may run on the operator's explicit go through an audited action or
the repo's documented write path, read back; anything broader is a PR.

## Local actions

One-offs run locally; only what recurs becomes a ReplyPen action. A rare or ad hoc write (billing
switch, vendor API call, one-customer fix) is a small script in the wrapper's local-actions dir:
credential read at runtime from the store the wrapper names (never printed, copied or committed),
dry-run by default (exact planned calls + before-state), `--execute` with an idempotency key, read
back, private audit record (go, before/after, request ids). The operator's explicit go gates every
write; the wrapper says which credentials and writes are in bounds.
