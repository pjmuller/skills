---
name: t3-resume-limited
description: Find and unblock T3 Code threads that are stuck on a provider rate/usage limit. Use for "my dentai profile is healthy again", "unblock rate-limited threads", "resume limited threads", "which threads hit the limit", "resume rate-limited t3 threads for dentai" (no time → derived from the blocked threads' reset), "… at 10:11", "/t3-resume-limited". Times are Europe/Brussels. Do not use for ordinary stalled workers — that is t3-maintenance's t3-fleet --stalled.
---

# Resume rate-limited T3 threads

`t3-limited` (in `t3-maintenance/scripts/`, on PATH via that skill's `install`).

## The signal
A limit hit leaves no status flag: the turn is `completed`, the session is `ready`. The *only*
evidence is the thread's **last** message — a short assistant line like `You've hit your session
limit · resets 10:10am (Europe/Brussels)`, `You've hit your monthly spend limit …`, `You've reached
your Fable 5 limit …`, `API Error: Rate limit reached`. If a user message came after it, the thread
is not blocked. No cache, no state file — recomputed from the read-only projection store each run.

## Flow
1. `t3-limited list --profile dentai --since 7d` — show PJ the table (kind: session/monthly/model/api,
   parsed reset time, whether it passed). Filters are case-insensitive substrings of the profile's
   `instanceId`, so `claude` matches all three Claude profiles.
1b. `t3-drafts list --limited` — blocked threads that also hold an unsent draft; PJ may have meant that
   text, not a plain `continue`, so ask before resuming those.
2. `t3-limited resume --profile dentai --dry-run` — confirm the exact `t3-ping-thread` calls.
3. `t3-limited resume --profile dentai` — pings `continue` into each thread, 5s apart.
4. Re-run both list commands immediately before reporting. Limit banners can arrive while this
   workflow is running; the first preview is never the final inventory.

PJ saying "profile X is healthy again" *is* the reset signal: `model`/`api` limits carry no reset
time and resume by default. Skipped unless `--force`: `monthly` spend limits (never self-reset) and
`session` limits whose parsed reset time is still in the future.

`t3-limits --profile dentai` (skill `t3-manage-thread`) confirms the window actually reset before resuming.

## Scheduled ("resume rate-limited t3 threads for dentai [at 10:11]")
Preview the set now, then `t3-limited schedule` arms a retrying one-shot LaunchAgent (time given, or
derived from the blocked threads' latest pending reset). It recomputes immediately before every
attempt and re-verifies afterward; never report the preview count as the armed count:
[scheduled-resume.md](scheduled-resume.md).

Related: `t3-maintenance` (fleet audit, `install`), `t3-manage-thread` (`t3-ping-thread` itself).
