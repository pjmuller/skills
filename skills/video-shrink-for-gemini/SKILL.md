---
name: video-shrink-for-gemini
description: Prepare recordings and obtain Markdown transcripts or visual narration with Gemini, delegating locally when available. Use for video shrinking, meeting transcription, silent UI walkthroughs, or recordings a text-only coding agent must understand.
---

# Video → Gemini

Prepare `<name>.gemini.mp4` and `<session>.gemini-prompt.md` beside the source.
When Antigravity is available locally or through T3, run the transcription yourself;
deliver `<name>.transcript.md` on disk, not just an LLM response or a copy/paste prompt.
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

Reference files are appended verbatim in separate fences. Use the execution path below.
For API use, load `GEMINI_API_KEY` from your own environment.
Check current Gemini video/file limits before choosing upload/chunking settings;
long recordings may need chunks or lower media resolution.

## Execute and verify

Prefer an authenticated T3 Antigravity provider with `t3-spawn-thread` (see the
`t3-manage-thread` skill) when its media-reading tools are available. T3 0.0.40 /
ACP 1.1.1 failed the local video probe: no video or image inspection tool was
available. For that runtime, use another media-capable route below, not a blind
transcription spawn. Recheck when the runtime changes.
Spawn from the source project with `--model gemini`
(Gemini 3.8 Flash High), a `🏓` title, and a brief naming absolute video, prompt,
context and output Markdown paths. The worker must read the brief, process the
media, write the transcript to that path, and report the path plus any gaps.
Read the file and verify it before settling the worker. Never delegate recursively.

If only `agy` is available, check its authentication and run locally with
`--model gemini-3.8-flash-high --effort high`; request the same output file.
T3 and native CLI authentication are separate; binary presence alone is insufficient.

A filename in a prompt is not a video attachment. Require evidence of actual media
ingestion: native video read/attachment, or extracted frames inspected with image
tools plus audio transcription when needed. Label sampled visual narration and
its gaps; frame inspection alone cannot produce a spoken transcript. Native CLI
supports video paste in its interactive prompt; headless stream-json accepts only
text blocks. Do not invent video attachment JSON. If a route cannot read media,
try another available automated route; report a concrete blocker before falling
back to user upload in AI Studio with the prepared video and prompt.

Check output is nonempty Markdown with timestamps, requested language/mode and
coverage of the recording. Return the transcript path and relevant gaps; preserve
source, prepared video and prompt for reuse. Never treat successful spawning or
a chat-only transcript as completion. Never use other agents' logs or test-fixture
generation commands as evidence of what the recording shows.

## PJ's local examples (optional context only)

- Project notes: `~/code/pjmuller/pjcoach/3_business/<n>_<project>.md`.
- Pilot context: `~/code/rootcause-org/rootcause-brain-<slug>/AGENTS.md`.
- Local API environment: `~/.config/mise-env/dentai-org/dentai.env`.
These are operator-specific examples, never required or assumed on another machine.
