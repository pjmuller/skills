# Non-Gmail inbound: a ticket adapter

Some products receive support through their own app (a ticket table the AI drafter writes into), not a
mailbox. The review is the same (research, reviewers, corrected drafts, lessons, report); only
**acquisition, writeback, ownership and continuity** change. The wrapper then binds an adapter script
instead of `cockpit.py`; nothing in this core calls it. Reference adapter: KampAdmin
`kampadmin/.agents/skills/support-ticket-review/` (`scripts/ka_tickets.py`).

| Step | Adapter must provide |
|---|---|
| collect | `index.json`: eligible rows (ready `link`, assignee, owner/route, `revision`, origin, health), exclusions **by reason** (incl. a customer reply hidden by snooze/hold), and a `coverage.line`. Eligibility mirrors the team's own "waiting on us" view; activity = the app's audit log of human changes, never `updated_at` (AI and review writes bump it) |
| detail | Fingerprinted snapshot of the guarded fields (tenant, status, assignee, AI run, draft + conversation hashes), the whole conversation, the current draft, the run, and **draft provenance**: AI run, an earlier review, a person (curated), unknown |
| apply | Dry-run by default; a compare-and-swap through the app's own write path (an action/endpoint that re-checks every expectation under a row lock), a stable `review_id` (replay = no-op), a receipt stored next to the draft (so a redelivered AI result cannot overwrite it), readback, private audit with the original draft. No send, no status/assignee change, no notification |
| state | Per-machine JSON (mode 600, atomic) keyed by ticket: reviewed `revision`, result, T3 thread ids. Same revision → skip; new revision → a new reviewer briefed with those threads |

- **Ownership:** one machine per assignee (wrapper roster, deterministic). Unmapped assignee or
  unassigned → listed as uncovered, never silently moved. The assignee expectation in the write is the
  fence: after a reassignment the old machine's write is refused. A pilot flag may review any
  assignee's ticket on one machine without claiming it.
- **Curated drafts are a person's work:** written after the latest customer message → propose in the
  report, don't overwrite (the adapter refuses unless an audited override reason is given).
- **Ref line:** reviewers and report cards use the wrapper's ref (e.g. `Ticket-ref: <app>:<id> <tenant>`)
  where this core says `Mail-ref`; `t3-mail-link` plays no part.
- Continuity per [continuity](continuity.md) with the state file standing in for `t3-mail-link index`:
  earlier 🧭 threads and reviewer threads named in state are read first; every round is a fresh
  `delegate_task`.
