---
name: monologue
description: Read Monologue notes, original summaries and speaker-labelled transcripts through its public API; retrieve temporary audio URLs when audio inspection is requested. Use for a Monologue note UUID, the Monologue notes created on a given day, or rendering a Monologue transcript to Markdown.
---

`scripts/monologue_api.py`: read-only client, CLI (`scan --date`, `get UUID`; `--help`) and
Python helpers (`list_notes`, `get_note`, `note_markdown`, `transcript_markdown`,
`recording_url`). `MONOLOGUE_API_KEY` comes from the caller's ignored environment file; no
account, key or archive policy lives in this replaceable install.
[API reference](https://www.monologue.to/docs/public-api/reference/notes/getnote).

Prefer a project's wrapper when present: it owns archive paths, attendee links, corrections and
human insights. Generated text must never overwrite human additions.

- `scan` filters on note **creation** day in `--timezone`: a delayed upload can have an earlier
  recording date.
- `summary` is Monologue's own; keep it labelled apart from agent/user takeaways.
- Transcript renders `transcript_segments` (seconds + neutral `speaker_id`), falling back to flat
  `transcript` only when segments are absent/empty. Malformed populated segments raise before any
  archive write rather than silently dropping part of a conversation.
- Speaker names: optional `speaker_names={"speaker_0": "Alex Smith"}` for either renderer. Map only
  from explicit introductions or unambiguous context, never turn order, timing or voice
  resemblance; persist mappings with evidence per note UUID in project storage, never as
  cross-recording voice identity. Unknown speakers keep their source ID.
- `recording_url` is a temporary signed URL: download only into private/ignored storage; never
  print or commit it, raw payloads or credentials. Transcript coherence is not proof of audio
  quality: listen before claiming it was checked.
