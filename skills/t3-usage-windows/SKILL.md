---
name: t3-usage-windows
description: Start provider usage windows with cheap turns, chain them during the workday, and resume or schedule recovery of rate-limited T3 Code threads. Use for warming accounts, daytime top-ups, window status, or unblocking threads after a usage reset. Ordinary stalled workers belong to t3-maintenance.
---

# T3 usage windows

A usage window is a provider's rolling quota period, commonly five hours, opened
by a model turn. Starting a window early makes its next reset arrive earlier;
a turn inside an active window does not restart its clock.

Three verbs cover the lifecycle: **start** windows, **topup** expired windows,
**limited** recovery. **status** combines quota windows and blocked-thread count.

```bash
t3-usage-windows start [--profile NAME_OR_ID] [--dry-run] [--json]
t3-usage-windows topup install [--interval 600]
t3-usage-windows topup status [--json]
t3-usage-windows topup remove
t3-usage-windows limited list --since 7d [--profile NAME_OR_ID] [--json]
t3-usage-windows limited resume [--profile NAME_OR_ID] --dry-run
t3-usage-windows limited schedule --profile NAME_OR_ID [--at HH:MM] [--dry-run]
t3-usage-windows status [--profile NAME_OR_ID] [--json]
```

`start` discovers enabled Codex and Claude profiles from T3 settings. It uses
Luna/low or Haiku/low, verifies selection, and settles every created child.
It leaves the calling thread running. `--profile` matches an exact instance ID
first, otherwise a case-insensitive ID/display-name substring.

`topup` runs every ten minutes, Monday–Friday 05:00–21:00 in the **system timezone**.
It starts only expired session windows, with a 60-second grace period. Unknown
quotas and accounts without session rows are skipped. T3 must be running;
launchd retries on the next tick. It never wakes the Mac.
For a manual decision preview: `topup run --dry-run --ignore-hours`.

`limited` detects a short limit banner as the thread's **last assistant message**;
a later user message means it is no longer blocked. `resume` sends `continue`,
skipping monthly caps and future resets unless `--force`. Model/API banners with
no reset time resume when requested. Check `t3-drafts list --limited`; use
`resume --protect-drafts` to exclude unsent drafts. Re-list immediately after
resuming to report the current inventory.

Read [scheduled-resume.md](scheduled-resume.md) for one-shot scheduling, reset
time derivation, bounded retries, draft protection, cancellation and notifications.
Mutation commands accept `--dry-run`; `limited resume|schedule --json` returns an
outcome plus audit output. `limited list --json` returns structured thread rows.

## Install and migration

Install [thread helpers](../t3-manage-thread/SKILL.md) and
[maintenance](../t3-maintenance/SKILL.md) first, then run `scripts/install` and
`scripts/install --check`. Dependencies resolve through PATH; `t3-limits` stays
owned by thread helpers. Maintenance supplies store access and draft discovery.
`t3-limited` is a thin legacy alias for `t3-usage-windows limited`.

Run `topup install` to unload `com.t3-skills.t3-hello-world-topup` and load
`com.t3-skills.t3-usage-windows.topup`. New one-shot jobs share the label family
`com.t3-skills.t3-usage-windows.limited.*`. Let existing one-shot resumes finish
before updating. Check `topup status --json` for loaded/legacy state.

Upstream limitations, workday constants and logs: [notes.md](notes.md).
