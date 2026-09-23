---
name: monologue
description: Read Monologue notes, original summaries and speaker-labelled transcripts through its public API; retrieve temporary audio URLs when audio inspection is requested.
---

Use `scripts/monologue_api.py` as a small shared Python module or CLI. Configure
`MONOLOGUE_API_KEY` through the caller's ignored environment file. No account/key
or archive policy lives in this replaceable installation.

- `uv run scripts/monologue_api.py scan --date YYYY-MM-DD --timezone Europe/Amsterdam`: notes **created** that day (a delayed upload can have an earlier recording date).
- `uv run scripts/monologue_api.py get UUID`: original summary + timestamped, speaker-labelled Markdown.
- Python: `list_notes(day, query=None, tz=...)`, `get_note(uuid)`, `note_markdown(note)`, `transcript_markdown(note)`, `recording_url(note)`.

Prefer a project's wrapper if present: it owns archive paths, attendee links, local
corrections and human insights. Generated text must not overwrite human additions.
Use literal documented corrections, never guess a speaker's identity from turn order.
`transcript_segments` contains seconds and neutral `speaker_id` values; only fall
back to flat `transcript` when segments are absent/empty. Invalid populated segments
raise before archive writes, rather than silently losing part of a conversation.

`summary` is Monologue's own summary, distinct from agent/user takeaways. Keep both
labelled. Calls are GET-only, cursor-paginated, bounded by creation day. No automatic
recording assignment from time or voice resemblance.

`recording_url` is a temporary signed URL. Download only into private/ignored storage;
never print or commit it, raw API payloads or credentials. Transcript coherence is not
proof of audio quality. Listen before claiming acoustic quality was checked.

[API reference](https://www.monologue.to/docs/public-api/reference/notes/getnote).

`transcript_markdown(note, speaker_names={"speaker_0": "Alex Smith"})` renders
`01:48 Alex: Text.`; duplicate first names use full names. Persist mappings/evidence in
project-owned storage keyed by note UUID, never as cross-recording voice identity.
Use explicit introductions or unambiguous identifying context, not turn order or timing.
Unknown speakers remain their source ID. The same optional mapping works with `note_markdown`.
