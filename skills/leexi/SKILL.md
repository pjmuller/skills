---
name: leexi
description: Leexi API access for meeting calls. Use for a Leexi call URL or UUID, "the Leexi meeting of today around 14:00" (find a call by date/time), Leexi transcript export to Markdown with speakers and timestamps, Leexi recording download, or listing recent Leexi calls.
---

# Leexi

Speech layer only: find a call, export `transcript.md` (speaker + timestamp paragraphs,
plus Leexi's summary and tasks), download the recording. What happened **on screen** is
the job of sibling skills `video-shrink-for-gemini` (Gemini) or `video-frames-for-vision`
(frames for vision-only models); feed them `source.webm`.

```bash
leexi-calls [--days 14 | --from ISO --to ISO] [--json] [--min-seconds 60]
download-leexi URL_OR_UUID [--out DIR] [--transcript-only | --resolve-only]
download-leexi --at "today 14:00" [--window 90] [--pick N] [--transcript-only]
```

- `--at`: `today 14:00`, `yesterday 14:00`, `2026-09-25 14:00`, `14:00` (today) pick the
  call nearest that local time within `--window` minutes; several matches → candidates on
  stderr, exit 2, rerun with `--pick N`. A bare date (`2026-09-25`) takes that day's latest
  call. Calls shorter than `--min-seconds` (60) are ignored.
- Out dir default `./.local/leexi/<uuid>/`; inside git it must be ignored (add `.local/`).
  Writes `source.json`, `leexi-call.json`, `transcript.md`, `source.webm` (skipped if present).
- Transcript is raw Leexi ASR; summary/tasks are Leexi-generated notes, not evidence.
  No `recording_url` → archived or retention off; only the transcript exists.
- Env: `LEEXI_KEY_ID` / `LEEXI_KEY_SECRET`. Mise-managed projects: `mise exec -- download-leexi ...`.
- Without the installer (any OS, incl. WSL): `uv run --script path/to/download-leexi --at "today 14:00"`.
- Install: `scripts/install` (links both helpers into `~/.local/bin`), `--check` verifies.

API facts, auth and key-scope gotchas (404 = out of scope): [api.md](api.md).
