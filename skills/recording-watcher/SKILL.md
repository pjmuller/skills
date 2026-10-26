---
name: recording-watcher
description: "Use to install, check or tune the poller that gives every new Fathom/Leexi/Monologue call one T3 follow-up thread on exactly one teammate's machine, set up a teammate, find out why a call got no (or the wrong) thread, or acknowledge/reprocess calls."
---

# Recording watcher

Intent: every call gets follow-up prompts without anyone asking, on exactly one teammate's machine.
No LLM in the poller: Python lists, [elects the owner](owner-election.md), routes, writes the
transcript and spawns; the thread does the judgement via
[recording-followups](../recording-followups/SKILL.md) (or the machine's wrapper). Personal data
lives in one config file ([config.md](config.md)); new machine (macOS or WSL): [setup.md](setup.md).

## Run (`recording-watcher --help` per subcommand)

- `poll [--dry-run] [--since D] [--force-hours]`: silent outside work hours unless `--force-hours`.
  `--dry-run` shows would-be spawns and election evidence, no state change. `--since` relists
  without moving the watermark; final calls (`spawned`, any `skipped:*`) are never revisited.
- `check` (config, credentials, workspaces) · `status` · `list` (read-only) · `seed` (new machine
  starts from now, no backfill).
- `ack [KEY…] [--match TITLE]`: handled elsewhere → `skipped:acknowledged`; no keys = all over-cap
  leftovers. `forget KEY…` drops final `skipped:*` entries (never spawned ones) so
  `poll --since <day>` re-elects them, e.g. after a roster fix. Both snapshot `state.json` first:
  **never edit `state.json` by hand**.
- `scripts/install [--schedule|--unschedule|--check]`: links the command; `--schedule` arms launchd
  (macOS) or a systemd user timer (Linux/WSL). Log and state: `~/.local/state/recording-watcher/`.

## How it decides (`scripts/recording-watcher`)

- No transcript → pending, `skipped:no-transcript` after 6 h; < 150 words → `skipped:too-short`.
- Election on vendor-verified speaker emails; a `personal` source (own Monologue account) is always
  this machine's. Not owner → `skipped:<reason>` + owner + evidence.
- Route: the source's pinned `workspace`, else known non-self speakers vote by words, then
  invitees, else default. Screen-share phrases → the brief asks for a Gemini narration first.
- Spawn = `t3-relay launch --wait 120` ([relay.md](../t3-manage-thread/relay.md)): confirmed →
  `spawned`; accepted but unconfirmed → `relay-pending`, re-checked via `t3-relay status` next poll
  (landed → `spawned`, failed → respawned; never resent while pending). Max 6 per poll, newest
  first; the watermark never passes an unfinished call; each spawn is saved at once (the relay
  never retries, so this is the only dedupe).
