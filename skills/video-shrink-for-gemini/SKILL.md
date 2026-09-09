---
name: video-shrink-for-gemini
description: Prepare screen recordings for Gemini with a smaller video and a context-rich prompt. Use for video shrinking, meeting transcription, silent UI walkthroughs, or recordings a text-only coding agent must understand.
---

# Video → Gemini

Deliver `<name>.gemini.mp4` and `<session>.gemini-prompt.md` beside the source.
The operator uploads both to AI Studio; later coding agents consume the text.
Install commands with `scripts/install`; verify dependencies with `scripts/install --check`.

## Inspect and choose mode

Inspect 3–4 frames across each clip and measure duration with `ffprobe`.
If audio exists, run `ffmpeg -i INPUT -af silencedetect=noise=-35dB:d=0.3 -f null -`.
Estimate speech share as `(duration − total silence duration) / duration`, accounting for
silence continuing to EOF. This measures audible activity, not speech: music, clicks,
noise and quiet voices need listening checks. No audio stream → visual-first.
Below roughly 20% speech → propose visual-first; speech-heavy → transcript-first;
substantial speech plus UI actions → mixed. If unsure, include mode in the single
question round along with missing project, speakers/language, purpose and skip ranges.
Infer available context first; use your project's context files and `AGENTS.md`.

## Shrink

```sh
scripts/shrink-video --preset normal "recording.mp4"
```

Bare filenames resolve in `~/screenshots`, then `~/Downloads`. Output audio is mono
16 kHz AAC. Presets: normal = 0.5 fps / 1280px cap; heavy = 0.25 fps / 1280px;
extreme = 0.2 fps / 854px. Never choose a preset that makes screen text unreadable.
For visual-first or mixed, rapid actions may disappear at 0.5 fps: retain the original
or produce a higher-frame-rate, source-resolution copy with ffmpeg when needed.
Check sampled output frames before delivery. Keep the original.

## Prompt

Fill [prompt-template.md](prompt-template.md): `MODE` = visual-first, transcript-first,
or mixed; durations/count from ffprobe; situation, language, speakers, skips and a
short introduction to each context file. Keep the applicable rule blocks.

```sh
scripts/build-prompt --header /tmp/header.md --out session.gemini-prompt.md \
  /path/to/project-context.md /path/to/project/AGENTS.md
```

Reference files are appended verbatim in separate fences. Return both output paths
and the chosen mode/preset. For API use, load `GEMINI_API_KEY` from your own environment.
Check current Gemini video/file limits before choosing upload/chunking settings;
long recordings may need chunks or lower media resolution.

## PJ's local examples (optional context only)

- Project notes: `~/code/pjmuller/pjcoach/3_business/<n>_<project>.md`.
- Pilot context: `~/code/rootcause-org/rootcause-brain-<slug>/AGENTS.md`.
- Local API environment: `~/.config/mise-env/dentai-org/dentai.env`.
These are operator-specific examples, never required or assumed on another machine.
