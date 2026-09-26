---
name: leexi
description: Leexi API access for meeting calls. Use for a Leexi call URL or UUID, "the Leexi meeting of today around 14:00" (find a call by date/time), Leexi transcript export to Markdown with speakers and timestamps, Leexi recording download, or listing recent Leexi calls.
---

# Leexi

Speech layer only: find a call, export `transcript.md` (speaker/timestamp paragraphs plus Leexi's
summary and tasks), download the recording. What happened **on screen**: feed `source.webm` to
[video-shrink-for-gemini](../video-shrink-for-gemini/SKILL.md) (Gemini) or
[video-frames-for-vision](../video-frames-for-vision/SKILL.md) (frames for vision-only models).

- `leexi-calls` lists recent calls; `download-leexi URL|UUID` or `download-leexi --at "today 14:00"`
  fetches one. Flags, `--at` forms and defaults: `--help`. Several `--at` matches → candidates on
  stderr, exit 2, rerun with `--pick N`.
- Output defaults to `./.local/leexi/<uuid>/` and must be git-ignored (the helper refuses otherwise).
  An existing `source.webm` is not re-downloaded.
- Transcript is raw Leexi ASR; summary/tasks are Leexi-generated notes, not evidence. No
  `recording_url` → archived or retention off; only the transcript exists.
- Env: `LEEXI_KEY_ID` / `LEEXI_KEY_SECRET` (mise projects: `mise exec -- download-leexi …`).
  Without the installer (any OS, incl. WSL): `uv run --script path/to/download-leexi …`.
  `scripts/install` links both helpers; `--check` verifies.
- Python callers: `scripts/leexi_api.py` (stdlib-only client, `--at` resolution, Markdown render).

API facts, auth and key-scope gotchas (404 = out of scope): [api.md](api.md).
