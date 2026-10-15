---
name: recording-watcher
description: Deterministic poller (every 5 min, Mon-Fri 09-18 Brussels) that finds new Fathom, Leexi or Monologue calls this machine owns and spawns one T3 follow-up thread per call. Shared owner election keeps teammates' machines from processing the same call twice. Use to install/check/tune it, set up a teammate's machine, inspect its state, or acknowledge/reprocess calls.
---

# Recording watcher

Intent: every call gets follow-up prompts without anyone asking, on exactly one teammate's machine.
No LLM in the poller: Python lists, [elects the owner](owner-election.md), routes, writes the transcript
and spawns; the thread does the judgement via [recording-followups](../recording-followups/SKILL.md)
(or the machine's wrapper). Personal data lives in one config file: [config.md](config.md).
New machine (macOS or WSL): [setup.md](setup.md).

## Run

- `recording-watcher poll [--dry-run] [--since 2026-10-01] [--force-hours]`: outside Mon-Fri 09:00-18:00
  Brussels it exits silently unless `--force-hours`. `--dry-run` prints would-be spawns and skips with
  election evidence, no state change. `--since` relists a window without moving the watermark;
  final calls (`spawned`, any `skipped:*`) are never revisited.
- `recording-watcher check`: config, credentials, workspaces. `status`: watermarks, counts, last spawns.
  `seed`: new machine starts from now (no backfill).
- `recording-watcher list [--since D] [--source fathom|leexi|monologue]`: read-only, with state status.
- `recording-watcher ack [KEY ...] [--match "<title>"]`: handled elsewhere → `skipped:acknowledged`;
  no keys = all over-cap leftovers. Snapshots `state.json.bak-<ts>` first; fetches a missing transcript.
- `recording-watcher forget KEY…`: drop final `skipped:*` entries (snapshot first; spawned ones refused), then
  `poll --since <day>` re-elects them, e.g. after a roster fix. Never edit `state.json` by hand.
- `scripts/install` links the command; `--schedule` arms launchd (macOS) or a systemd user timer
  (Linux/WSL); `--unschedule`; `--check`. Log `~/.local/state/recording-watcher/poll.log`.

## How it decides (`scripts/recording-watcher`)

- No transcript → pending (retried; `skipped:no-transcript` after 6 h); < 150 words → `skipped:too-short`.
- Election ([owner-election.md](owner-election.md)) on vendor-verified speaker emails; a `personal`
  source (own Monologue account) is always this machine's. Not owner → `skipped:<reason>` + owner + evidence.
- Route: a source's pinned `workspace`, else known non-self speakers vote by words, then invitees, else default.
- Screen share: phrase hits; likely → the brief asks for a Gemini narration first.
- Max 6 spawns per poll, newest first; the watermark never passes an unfinished call. Each spawn is saved
  immediately: never spawned twice. State + transcripts: `~/.local/state/recording-watcher/`.
- Tests: `uv run --with pytest pytest skills/recording-watcher -q`.
