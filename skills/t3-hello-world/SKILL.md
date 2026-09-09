---
name: t3-hello-world
description: Start fresh five-hour usage windows in T3 Code with low-cost turns on OpenAI and every enabled Claude profile, then settle the child threads and orchestrator, and keep those windows chained back-to-back through the workday. Use when asked to warm up, initialize, or start all provider limits without leaving needs-you reminders, or to install/inspect the daytime top-up poller.
---

# T3 Hello World

```bash
.agents/skills/t3-hello-world/scripts/t3-hello-world [--dry-run]   # from the project root
```

Intent: one cheapest-possible turn per provider profile so all usage windows start together, and
no thread is left asking for attention. The helper discovers OpenAI plus every enabled
`claudeAgent` instance from T3's registry (no profile list to maintain; other provider families
ignored), verifies each spawn, and settles every child it created — including partial successes.
Models/effort are pinned in the script; change them there.

Spawning and settling stay owned by [t3-manage-thread](../../../ai/skills/t3-manage-thread/SKILL.md)
(`t3-spawn-thread`, `t3-settle-thread` and `jq` on PATH — its `scripts/install` once). Do not
duplicate its API, auth, polling or lifecycle logic here.

## Ending the orchestrator

After the helper finishes, prepare the concise provider result. With no tool calls, background
tasks or subagents left, make this the **last** tool action, in a normal foreground shell call:

```bash
t3-settle-thread --self
```

Then end the turn immediately with the prepared result. Any later activity (even reading the
detached log) wakes and unsettles the orchestrator — settle semantics in
[settle-thread.md](../../../ai/skills/t3-manage-thread/settle-thread.md).

## Daytime top-ups

Windows should never sit expired during a workday. `scripts/t3-hello-world-topup` is a macOS
LaunchAgent (`com.pjmuller.t3-hello-world-topup`, `ProcessType=Interactive` — with `Standard` a hello child
sat visible ~90 s before settling, 2026-09-09) that ticks every 10 min and fires
`t3-hello-world --only <ids>` for exactly the profiles whose 5h session window has expired.

```bash
.agents/skills/t3-hello-world/scripts/t3-hello-world-topup install [--interval 600]  # arm · idempotent
… t3-hello-world-topup run --dry-run --ignore-hours     # decide + print, fire nothing
… t3-hello-world-topup status | uninstall
```

Gate: Mon–Fri, 05:00 ≤ now < 21:00 Europe/Brussels; T3 Code must be up (else the next tick
retries). Never wakes the Mac. Stale = session reset missing or more than 60 s in the past;
accounts `t3-limits --json` reports with an `error` are *unknown*, logged and skipped. An account
with no session row at all is logged, never topped up (Codex Pro's OAuth usage endpoint returned
`primary: null` even right after a turn, 2026-09-08 — a missing row is not an expired one, and
treating it as stale re-fires a hello every tick). Codex is therefore only chained when it reports
an expired window; Claude profiles always report theirs.
When nothing is stale but a reset lands inside the tick, it sleeps to that reset + 60 s and
re-checks once — ~1-minute precision without polling faster.

Log: `~/.t3/userdata/logs/t3-hello-world-topup.log`, one summary line per tick.

Deterministic by design — no LLM thread in the loop. In-thread timers (`CronCreate`, `/loop`,
`ScheduleWakeup`) die with T3's 30-min ProviderSessionReaper or a Mac sleep, see
[t3_monkey_patches.md](../../../decissions/t3_monkey_patches.md). Overlapping with the 05:00
`t3-schedule` hello-world job is harmless: a hello on a live window costs nothing extra.
