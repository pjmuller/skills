---
name: video-shrink-for-gemini
description: Prepare recordings and obtain Markdown transcripts or visual narration with Gemini, delegating locally when available. Use for video shrinking, meeting transcription, silent UI walkthroughs, or recordings a text-only coding agent must understand.
---

# Video → Gemini

Prepare `<name>.gemini.mp4` and `<session>.gemini-prompt.md` beside the source.
When Antigravity is available locally or through T3, run the transcription yourself;
deliver `<name>.transcript.md` on disk, not just an LLM response or a copy/paste prompt.
Install commands with `scripts/install`; verify dependencies with `scripts/install --check`.

## Fathom input

For a Fathom URL, use [the API download flow](fathom.md) before media inspection.
It resolves private call URLs without browser/cookie automation and optionally saves
transcript timings for verification. Never change sharing permissions.

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

Bare filenames resolve in `~/screenshots`, then `~/Downloads`. Keep the original.
Output uses H.264 slow encoding and mono 16 kHz AAC at 32 kb/s for meeting speech.
Normal = 0.5 fps / CRF 24 / 1280px cap; compact = same cadence / CRF 28;
heavy = 0.25 fps / CRF 26 / 1280px; extreme = 0.2 fps / CRF 30 / 854px.
For 720p screen shares, preserve 720p: try normal, compact, then heavy before chunking.
Never use extreme when small screen text matters. Rapid actions may require source
frames or higher fps; inspect output speech and small text before accepting a recipe.

Native `agy` 1.2.5 rejects files over **50 MiB (52,428,800 bytes)**, separately from
Gemini API limits. A tested 46-minute 720p meeting fit in one file: normal 38.6 MiB,
compact 29.3 MiB, heavy 24.4 MiB. These are examples, not size guarantees.
Read [size fitting and chunk fallback](compression.md) when output exceeds the limit.
Prefer the fewest measured-to-fit clips; do not default to arbitrary ten-minute chunks.

## Prompt

Fill [prompt-template.md](prompt-template.md): `MODE` = visual-first, transcript-first,
or mixed; durations/count from ffprobe; situation, language, speakers, skips and a
short introduction to each context file. Keep the applicable rule blocks.

```sh
scripts/build-prompt --header /tmp/header.md --out session.gemini-prompt.md \
  /path/to/project-context.md /path/to/project/AGENTS.md
```

Reference files are appended verbatim in separate fences. Use the execution path below.
For opaque URLs/record IDs, read [exact-identifiers.md](exact-identifiers.md):
candidate-assisted identification is not visual verification.
For API use, load `GEMINI_API_KEY` from your own environment.
Check current Gemini video/file limits before choosing upload/chunking settings;
long recordings may need chunks or lower media resolution.

## Execute and verify

**Verified: native `agy` 1.2.5, Gemini 3.8 Flash High, paid plan (2026-09-18); 1.2.0 Starter (2026-09-10).**
A clipboard MP4 produced an aligned speech + visual Markdown file; a 42-minute 720p meeting
took ~150 s. Driving it headlessly works: `osascript -e 'set the clipboard to (POSIX file "…")'`,
`agy` inside `tmux`, `tmux send-keys C-v`, confirm `Clipboard file URL read … video/mp4` in the
latest `~/.gemini/antigravity-cli/log/cli-*.log`, then `tmux load-buffer` + `paste-buffer -p` the
prompt. The ancillary `media_summary_generation` 503 is harmless; only a main-run 429 is a blocker.

1. Check native authentication with `agy models`; T3 login is separate.
2. Start interactive `agy --model gemini-3.8-flash-high --effort high` in the task folder.
3. Copy the **video file** in Finder, then send Ctrl+V to the CLI. Verify the attachment
   indicator shows `video/mp4` (or its actual type) and nonzero bytes before submission.
   Pasting a pathname as text does not attach media. The submitted message may label
   video as “image(s)” and later show 0 B; the pre-submit MIME/size is the useful check.
4. Send the prepared brief with an absolute `<name>.transcript.md` output path.
   Require direct media perception; prohibit deriving contents from logs or source code.
   Approve the requested file write within the authorized task, then read it yourself.
5. Verify spoken words, visual changes, timestamps and coverage against the recording;
   report gaps. Return the Markdown path, preserve inputs, then exit the CLI.

Run directly in native `agy` when it works; a T3 worker is optional, not a media
prerequisite. For model comparisons, use fresh conversations, identical media and
held-out reference evidence. Discover model IDs with `agy models`; never silently
substitute models or change billing. `gemini-3.1-pro-high` was authenticated in
1.2.5, but did not improve small opaque-ID recognition in a two-ticket comparison.

Automate the interactive terminal and file clipboard when computer tools allow;
do not hand the user a copy/paste prompt when this local route works. Headless
stream-json accepts text blocks only; do not invent video attachment JSON.
[Official media-paste docs](https://antigravity.google/docs/cli/prompting/).

T3 0.0.40 / ACP 1.1.1 failed the media probe: no video/image inspection tool.
A T3 orchestrator can run the native CLI workflow above. If a future T3 runtime
supports media, use `t3-spawn-thread --model gemini` with a `🏓` title and absolute
input/output paths; verify the file before settling the worker. Never recursively
delegate. If all automated media-capable routes fail, report the concrete blocker
and provide the prepared video/prompt for AI Studio. Chat-only output is incomplete.

## No Gemini available

Seen blockers: native `agy` weekly quota 429, and video-summary 503. When Gemini is exhausted or
existing Claude/OpenAI subscriptions are preferred, take the measured
[local route](local-route.md): `scripts/transcribe-local` for local ASR and `scripts/scene-frames`
for scene-sampled original-resolution frames, read by Claude Code or Codex. It is sampled, not
continuous, perception — weaker than Gemini on anything between frames; say so in the output.

## PJ's local examples (optional context only)

- Project notes: `~/code/pjmuller/pjcoach/3_business/<n>_<project>.md`.
- Pilot context: `~/code/rootcause-org/rootcause-brain-<slug>/AGENTS.md`.
- Local API environment: `~/.config/mise-env/dentai-org/dentai.env`.
These are operator-specific examples, never required or assumed on another machine.
