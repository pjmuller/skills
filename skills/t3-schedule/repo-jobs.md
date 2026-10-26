# Recurring repo jobs

Definition lives in the project repo (survives a machine reset, gets reviewed):
`<project>/.agents/schedules/<name>.json` (portable fields, no path/profile) + `<name>.prompt.md`.
`add` writes both; **the caller commits them** (the helper never does). The runtime dir keeps a
machine-local pointer (`source`, `profile`), runner, units, state.

- Prompt edits apply at the next fire; time/model/flag edits need `refresh`. `set-at <name> HH:MM`
  moves a slot. `list` flags `untracked` / `uncommitted` / `MISSING` specs and stale runners.
- A clone arms nothing: `t3-schedule adopt <repo | spec.json> [--profile X]` opts a machine in.
- `remove` disarms this machine only; `git rm` the two files to drop it for everyone.
- `pause <name> [--until YYYY-MM-DD]` / `resume <name>` edit the repo spec (commit + push); runners
  and catch-up read it at fire time, no refresh. `--until` resumes at local midnight that date.

## One machine or many

Spec records `machines` (`one` default; `add --many-machines` → `many`) and `adopted_by`
(`machine` label, repo `git user.name`, `since`, random `id` from `meta/machine.json`; no
hostname/serial; `t3-schedule machine --label X`). `add` / `adopt` / `remove` update it; commit + push.

- **one**: adopting a job registered elsewhere asks for confirmation at a terminal; unattended it
  needs `--takeover`. `--force` never implies takeover.
- **many**: every adopter appended.
- **Displaced** (not listed / identity lost / `adopted_by: []`): runner skips (checked before the
  T3 wait and right before the fire), catch-up ignores it, `list` flags it. Recover: `adopt --takeover`.
  Specs without `adopted_by` run everywhere they're adopted.
- Registration is intent in the local checkout, not a lock: the old machine stops once it pulls.
