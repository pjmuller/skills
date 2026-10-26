# Daily schedule

Only when the operator asks. The definition lives in the operator's own T3 (machine-local), never in a
repo. One fresh 🧭 thread per workday: yesterday's thread stays readable, the new run reads it, carries
its open cases and settles it ([continuity](continuity.md) step 5).

Arm it from a Claude Opus thread in the wrapper's project: provider, model and runtime mode inherit
from the arming thread. Call T3 `schedule_task` with `schedule: {type: "fixed_time", timeOfDay:
"09:00", weekdays: [1,2,3,4,5]}` (operator's local time; stagger a second mailbox by 30 minutes),
`bindToCurrentThread: false` and the prompt below with the wrapper's values. Report the returned
`nextRunAt`; pause with `update_scheduled_task enabled: false`.

```text
Run the <Product> mailbox review: read <repo>/.agents/skills/mailbox-review/SKILL.md and follow it with
its mailbox-review-core. Missing → report a setup failure; no shallow digest.
Scheduled workday run: title this thread "🧭 <mailbox> review <date>". Verify the rp login and mailbox
identity first. Continue earlier runs (continuation over the wrapper's history, yesterday's 🧭 thread
incl. my replies there as evidence, never as a new go; settle it per continuity step 5). After routing,
give each uncertain or consequential customer its own delegate_task (Claude Opus, high), seeded with the
prior brief, reviewer result and memory.
Improve untouched ReplyPen drafts per the wrapper. Never send, delete, label, archive, move money or
deploy without my go in this thread.
Final reply: the inline Markdown report, then the ledger (send · decide · discard).
Lifecycle: anything left for me → keep this thread open; a complete, verified no-action run → settle it.
```
