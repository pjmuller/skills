# Optional finding fields

Read by the reviewer only when emitting one of these; see [reviewer.md](reviewer.md) for the base schema.

When a draft was wrong, or right only after research ReplyPen could not do itself, and a brain change (policy line, case runbook, script output, routing hint, KB article, action) would have steered the run to the right answer, add `brain_proposal`: `{"target": "brain file or article", "change": "one-line change", "why": "which run it fixes and why", "detail": "optional private path to the exact diff"}`. Read the current brain file first; if it already says the right thing, it is a model/host issue, not a proposal. Write the exact diff to a private file next to your finding and point `detail` at it. Proposals render in their own section, also for non-actionable threads. The reviewer applies nothing; the coordinator lands them through one brain thread (SKILL.md "Teach the brain").

Whenever you can write a **better version** of an **unmodified unsent AI draft** (wrong, obsolete, incomplete, or just clearer), include `replacement_body` with the complete plain-text body; no operator go is needed. Match the latest run's `draft_markdown` byte-for-byte to exactly one Gmail draft. Preserve existing quotes, signature, persona and language verbatim. A claim that only becomes true after a human step (payment, refund, credit note, setting) gets a leading `[[✏️ Before sending: …]]` line naming that step. If the draft was human-edited, another reply exists, authorship is uncertain, or the thread/run changed, recommend the owner's next action instead. The coordinator validates and applies it separately.

For a **confirmed** product bug (evidence: code path, rows/logs or a reproduction), add `bug`: `{"title", "evidence": ["1-6 short lines: file:line, ids, counts"], "affected": "how many customers, how counted", "fix_direction", "owner": "role from the wrapper", "thread": "optional fix thread or PR link"}`. Suspicions stay in `why`/`sources`. Renders under "Confirmed product bugs".

When something kept you from going deeper, add `dx_gaps`: 1-5 `{"gap": "what was missing (env var, credential, CLI, repo, access, timed-out query)", "unblock": "who grants it or what fixes it"}`. Renders under "What limited this review" so the operator can ask for it.

`case_thread`: the T3 thread that owns this case (a standalone fix/action thread, or the owner `t3-mail-link find` returned), as `t3-thread://v1/<threadId>` or the bare id, ≤300 characters. Renders beside the row's `Mail-ref` line ([continuity](continuity.md)).

`due_by`: `YYYY-MM-DD` of a promise **we** made (a refund date, a document by a date, a contractual
deadline). A stale case whose `due_by` is within 7 days (or overdue) stays among the top cards. Never a
renewal or invoice date: those recur.
