---
name: video-shrink-for-gemini
description: Prepare a CleanShot / screen recording (from ~/screenshots or ~/Downloads) for Gemini transcription — shrink it with ffmpeg (low fps, source-resolution frames, mono speech audio) AND build the companion markdown prompt (brief + appended project context files). Use for "shrink this video for Gemini", "make this recording uploadable", "prep the recording + prompt for Gemini", "transcribe this meeting recording".
---

# Video → Gemini (shrink + prompt)

Deliverable = two files next to the source: `<name>.gemini.mp4` and one `<session>.gemini-prompt.md`
(one prompt for all clips of the same session). PJ uploads both in aistudio.google.com; the transcript
feeds later AI agents. Bytes are cheap (2 GB/file); Gemini *tokens* are the limit, and on-screen text
must stay readable — drop frames, not pixels.

## 1. Shrink
```sh
scripts/shrink-video [--preset normal|heavy|extreme] [--out DIR] "CleanShot 2026-09-08 at 11.55.46.mp4"
```
Bare names resolve in `~/screenshots` then `~/Downloads`. Width is a cap (never upscales); audio always mono 16 kHz AAC 48k.

| preset | fps | width cap | when | ~size / hour |
|--------|-----|-----------|------|-------------|
| normal (default) | 0.5 | 1280 | code/UI/slides on screen matter | 60–80 MB |
| heavy | 0.25 | 1280 | talking + occasional screen | 50–60 MB |
| extreme | 0.2 | 854 | picture only for orientation | 30 MB |

Lesson 2026-09-08: 640 px made UI text unreadable for zero gain — never downscale below source to save bytes.

## 2. Close the gaps (one question round, max)
Reverse-engineer first, ask second. Pull 3–4 frames spread over the clip
(`ffmpeg -ss <t> -i in.mp4 -frames:v 1 /tmp/f.png`) and look at them: which app, which company,
which people are on camera. Then ask PJ **only** what's still missing, in one `AskUserQuestion`:
- **Project** → pick the pjcoach file `~/code/pjmuller/pjcoach/3_business/<n>_<project>.md`
  (0_overall, 2_pro-backup, 3_kampadmin, 6_rootcause, 7_dentai, 8_leesheld, 9_momentum-tools).
- **Counterpart** (customer/company) → its brain `~/code/rootcause-org/rootcause-brain-<slug>/AGENTS.md`
  when it's a Rootcause pilot; otherwise the repo's top-level `AGENTS.md`.
- **Who speaks** (names + roles) and **language** (usually Flemish Dutch + English jargon).
- **Dead stretches**: podcast/music leaking in, silent setup work, breaks — approximate timestamps if PJ knows them.
- **Purpose of the transcript** (customer discovery, onboarding notes, bug hunt…) — it steers what "relevant" means.

## 3. Build the prompt
1. Copy `prompt-template.md` to `/tmp/header.md`, fill every `{{…}}` (COUNT, DURATIONS from ffprobe,
   SITUATION, LANGUAGE, SPEAKERS with roles, SKIPS as bullet lines, CONTEXT_INTRO = 2–4 lines saying what
   each appended file is). Keep the rules block as-is unless PJ asks otherwise.
2. Append the reference files verbatim — never retype them:
   ```sh
   scripts/build-prompt --header /tmp/header.md --out ~/screenshots/<session>.gemini-prompt.md \
     ~/code/pjmuller/pjcoach/3_business/6_rootcause.md ~/code/rootcause-org/rootcause-brain-<slug>/AGENTS.md
   ```
   Each file lands as `### <path>` + a 5-backtick fence, so PJ can strip one block by hand.
3. Reply with both paths and the preset used. Nothing else to recap.

Worked example (2026-09-08, iBeauty onsite): `examples/ibeauty-onsite-2026-09-08.header.md`.

## Gemini limits (verified 2026-09-08, ai.google.dev/gemini-api/docs/video-understanding)
- File: 2 GB (free) / 20 GB (paid) via Files API — AI Studio uses the same path. Kept 48 h.
- Context 1 M tokens (3.8 Flash). Gemini samples at **1 fps regardless of source fps**:
  ~300 tokens/s at default media resolution, ~100 tokens/s at `low`. ≈55 min fits at default, ≈3 h at low.
  Tell PJ to set **media resolution = low** in AI Studio for anything > 50 min; 3.8 Flash also has an
  "agentic" video mode (~88 % fewer tokens).
- API only: `video_metadata.fps` (e.g. 0.25) cuts tokens further; `start_offset`/`end_offset` to chunk.
  Key: `GEMINI_API_KEY` in `~/.config/mise-env/dentai-org/dentai.env`.
