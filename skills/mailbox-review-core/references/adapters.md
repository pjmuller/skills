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

## Intercom via ReplyPen: `scripts/intercom.py` (report-only)

Intercom has no draft object: ReplyPen posts its suggestion as an admin **note** ("📝 Suggested reply —
copy into the reply box…") plus an internal note, often from the same admin seat the team replies with.
So "unused" is only observable as **no reply from a person after the suggestion**; text pasted into an
unsent composer is invisible. Say so (the coverage line does); never claim paste detection.

```sh
intercom.py collect --project <p> [--tenant <slug>] --mailbox-id <intercom-uuid> --out <new dir> [--days 7]
intercom.py detail  --bundle <dir> --thread-id <conversation id>   # refresh + re-evaluate + fingerprint
intercom.py recheck --bundle <dir>                                  # right before the report
```

- **Reads:** `rp run list` → `rp run thread` (provider must be intercom; the mailbox must be the
  project's only Intercom one, since lineage has no mailbox id) → `rp run show` → the raw conversation
  through `rp dev console bash run` with the runtime's own Intercom connector (one GET; no local token).
  `rp project mailbox thread` is not enough: it drops notes and conversation state.
- **Ours vs a person's** by content, never by author: after stripping only the host's own fixed strings
  (`HOST_CHROME`), a note must carry a run's draft or notes and **not one word more**; a suggestion must
  match exactly one run's draft. A new host string shows up as false `curated`/`person_note_after`:
  add it to `HOST_CHROME` with its host source, never loosen the match.
- **Eligible** (`scope: draft`): latest suggestion, open, no newer customer message or run, no person's
  reply since the customer message it answers (even one sent before placement; any part with text
  counts, since reply-and-assign/close/snooze are not `comment` parts), no send link, no
  person's note after it, not edited. **Follow-up** (`scope: followup`): open, customer spoke last,
  ReplyPen placed nothing. Everything else is excluded with one reason (`answered`, `closed`,
  `snoozed`, `newer_inbound`, `superseded_by_run`, `sent_linked`, `person_note_after`, `curated`,
  `ambiguous_*`, `outside_window`, `no_suggestion`); flag `unanswered` marks the ones a snooze or close
  hides. Failed reads are `unread`, not excluded. Rules: `evaluate()`, tests `test_intercom.py`.
- No `apply`, no state file: a better reply is a proposal in the report. Reviewers get the core recipe
  with `Ticket-ref: intercom:<id> <mailbox>` and the detail file.
