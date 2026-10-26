# Daily schedule

Only when the operator asks. The job definition is versioned in the wrapper's repo; arming is
machine-local (each machine opts in). One fresh 🧭 thread per workday: yesterday's thread stays readable, the new run reads it, carries
its open cases and settles it ([continuity](continuity.md) step 5). Stagger a second mailbox by 30 minutes.

**Preferred: a repo job** ([t3-schedule repo jobs](https://github.com/pjmuller/skills/blob/main/skills/t3-schedule/repo-jobs.md)). The wrapper's repo carries
`.agents/schedules/<prefix>-mailbox-review.json` + `.prompt.md` (workdays, model `opus`, thinking
`high`, title `🧭 <mailbox> review {date}`, `adopted_by: []`); the operator's machine opts in with
`t3-schedule adopt <repo>/.agents/schedules/<name>.json`, then commits and pushes the updated spec.
launchd replays a slot the Mac slept through; T3's native timer skips runs more than 10 minutes late.

Fallback without `t3-schedule`: T3 `schedule_task` from a Claude Opus thread in the wrapper's project
(provider, model and runtime mode inherit from it), `schedule: {type: "fixed_time", timeOfDay:
"09:00", weekdays: [1,2,3,4,5]}`, `bindToCurrentThread: false`, the prompt below.

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
