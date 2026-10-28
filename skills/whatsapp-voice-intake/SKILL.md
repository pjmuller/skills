---
name: whatsapp-voice-intake
description: "Use to install, check or tune the poller that turns voice notes sent to your own WhatsApp chat (\"message yourself\") into transcribed messages in one T3 thread (usually a pinned router), find out why a note did not arrive, or reseed it. Read the machine's wrapper first (account, target thread, hours)."
---

# WhatsApp voice intake

Intent: dictate an idea on the road as a voice note to yourself; minutes later it sits, transcribed,
in your router thread, which decides what to do. **No model in the poller**: it reads, groups,
transcribes once and delivers quoted source data; the receiving thread interprets. Only the paired
account's own chat is read. Mechanics reused: [whatsapp-bridge](../whatsapp-bridge/SKILL.md) (read,
download, `transcribe-gemini` ≈ $0.004/min), [t3-relay](../t3-manage-thread/relay.md) (`find`,
`send --request-id`, `launch`). Config: [config.md](config.md). Code: `scripts/voice_intake.py`.

## Run (`whatsapp-voice-intake --help`)

- `poll [--dry-run] [--force-hours]`: one pass; launchd/systemd runs it every 5 min, silent outside the
  configured hours. Missed or offline notes are picked up by the next in-hours poll.
- `seed [--include MSG_ID…] [--force]`: start from now, **no backlog**; `--include` adds exact older voice
  notes (verified in the self chat, printed with local time). A poll without state seeds itself from now.
- `status` (exit 1 on problems) · `check` (config, paired account, target thread, health).
- `scripts/install [--schedule|--unschedule|--check]`. State/log: `~/.local/state/whatsapp-voice-intake/`
  (0700; transcripts and frozen messages live there, never in logs). Never edit `state.json` by hand.

## How it decides

- **Capture** = a chain of self-chat messages at most 120 s apart (cut at 15 min) holding ≥1 voice note:
  text before/after is its annotation, adjacent voice notes travel together. Dispatched once the newest
  message is 5 min old, so a "below" annotation can still join. Text-only chains are never sent.
- **Late text** that syncs into an already delivered chain (≤24 h) → one *supplement* message that names
  the capture; never a second task. A new voice note always starts its own capture.
- **Floor**: notes before the seed (or before `now - 6 h` once caught up) are never imported; the 6 h trail
  catches history that syncs late.
- **Transcription** once per note, verbatim, with the purpose (`CONTEXT`: a note-to-self a dispatcher will
  route) and the wrapper's `hint` + `vocabulary` file. On a synthetic Flemish clip with 10 product/model/people
  terms: no hint 6 wrong, a one-line names hint 1, purpose + vocabulary with known mishearings 0. Failures retry after 5/15/60 min, then the note is delivered marked
  "transcription failed" (never silently dropped). A transcript a crash left beside the audio is reused, not
  re-bought. Daily cap `daily_audio_minutes` holds further paid calls.
- **Target** looked up per delivery (`t3-relay find`: open root threads with the exact title + pin state):
  newest pin wins (a router reset pins the successor first); else the only open one; several unpinned →
  hold + alert; none → one `fallback` launch (its brief must make the thread pin itself), never a second
  while the first is unconfirmed or was launched < 24 h ago. Pin state unreadable = unavailable, not "none".
- **Delivery** `t3-relay send --mode queue --request-id <capture>`, payload frozen on disk first. The id
  makes a crash between send and save harmless: the next poll asks `t3-relay status` and never re-sends an
  accepted or still-unconfirmed message, and never to another thread. Guarantee: at-least-once attempts,
  no duplicate from retries or restarts; not exactly-once execution by the receiving agent.
- **Reading** pages forward from the floor (bridge `read_chat(since=)`, 200 per page, ≤25 pages). A chat too
  busy to page through (or 200 messages in one second) holds the floor and raises `backlog`: stuck, never skipped.
- **Health**: macOS notification once per condition per 6 h (bridge/T3 outages after 30 min), no message
  content. `status`/`check` list the conditions and captures undelivered > 1 h.
