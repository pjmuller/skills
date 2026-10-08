---
name: video-shrink-for-gemini
description: Prepare recordings and obtain Markdown transcripts or visual narration with Gemini, delegating locally when available. Use for Fathom raw transcript retrieval without video analysis, video shrinking, meeting transcription, silent UI walkthroughs, or recordings a text-only coding agent must understand. Loom shares via download-loom; Leexi calls come from the leexi skill; without Gemini, frames come from video-frames-for-vision.
---

# Video → Gemini

Deliverable: `<name>.transcript.md` on disk (not a chat reply, not a copy/paste prompt for the
user), built from `<name>.gemini.mp4` + `<session>.gemini-prompt.md` beside the source.
Helpers (`--help` each): `shrink-video`, `build-prompt`, `download-fathom`, `download-loom`,
`detect-screenshare`, `transcribe-gemini`, `transcribe-local`, `transcribe-openai`. `scripts/install` links them; `--check` verifies deps.

Route: `transcribe-gemini` (Gemini API) → continuous audiovisual narrative; native `agy` only
without an API key ([agy-route.md](agy-route.md)). No Gemini, or small on-screen text must be
exact → [No Gemini available](#no-gemini-available).

## Fathom input

Fathom URL → [fathom.md](fathom.md). Transcript-only requests: `download-fathom URL --out
PRIVATE_DIR --transcript-only`, then stop (no media, Gemini or ASR). Never change sharing
permissions.

## Loom input

Loom share URL → [loom.md](loom.md): `download-loom URL --out PRIVATE_DIR` fetches video, metadata
and Loom's own timestamped transcript (public shares, no login). That transcript is the speech layer;
Gemini adds the screen. `--transcript-only` stops before the download.

## Leexi input

Leexi URL, UUID or "the Leexi meeting of today around 14:00" → sibling [leexi](../leexi/SKILL.md)
skill (`download-leexi`). Its timestamped transcript is the speech layer; Gemini adds what
happened on screen and checks what Leexi heard.

## ClickUp SyncUp input

`clickup-core`'s `scripts/syncup.py URL --out PRIVATE_DIR` fetches recording, AI notes and the
untimed transcript ([reference](../clickup-core/reference.md#syncup-recordings)); then continue below.

## Inspect and choose mode

Look at 3–4 frames per clip; get duration from `ffprobe`. With audio, estimate speech share from
`ffmpeg -i INPUT -af silencedetect=noise=-35dB:d=0.3 -f null -` as `(duration − silence) /
duration` (count silence running to EOF). It measures audible activity, not speech: music,
clicks and quiet voices need a listen. No audio or < ~20% → visual-first; speech-heavy →
transcript-first; speech plus UI actions → mixed. Infer project, speakers, language, purpose
and skip ranges from context (`AGENTS.md`, project docs); ask one question round only for gaps.

## Shrink

`shrink-video --preset normal FILE` (presets in the script; keep the original). API tokens depend
on duration, not bytes: shrinking only speeds the upload. Native `agy` rejects attachments over
**50 MiB (52,428,800 bytes)**; over it: add `--max-bytes 48M` (splits into overlapping parts + `<name>.chunks.md`);
preset choice and stitching part transcripts: [compression.md](compression.md).
Never use `extreme` when small screen text matters; rapid actions may need source frames.

## Prompt

**Ground the vocabulary first, every time.** Collect the exact spellings the recording will
contain: people, company/product/feature names, vendors, the project's taxonomies/enums, places,
language variety (e.g. Flemish Dutch). Sources: project `AGENTS.md`/skill docs, glossaries, the
vendor transcript's summary and speaker list, recent notes, ticket titles. 30–80 terms, only ones
seen written. Without them Gemini and OpenAI invent plausible spellings.

Fill [prompt-template.md](prompt-template.md) (`MODE`, ffprobe durations, situation, language,
speakers, skips, vocabulary, one-line intro per context file; keep applicable rule blocks), then
`build-prompt --header header.md --out session.gemini-prompt.md CONTEXT_FILE...` appends context
files verbatim. Opaque URLs/record IDs: read [exact-identifiers.md](exact-identifiers.md) first.

## Execute and verify

`transcribe-gemini <name>.gemini.mp4 --prompt session.gemini-prompt.md` writes
`<name>.transcript.md` + `.usage.json` (tokens, USD at list price), from any folder. Key: one per
machine: `VIDEO_GEMINI_API_KEY` from the env or `~/.config/transcribe-gemini/env` (chmod 600; never
in a repo); else a project's `GEMINI_API_KEY`; else `GOOGLE_CLOUD_PROJECT` + credentials (Vertex). None →
[agy-route.md](agy-route.md). `scripts/install --check` reports the key.
`--thinking medium` (default) kept every visual step at ~$0.02 per 2 minutes; `high` doubles cost
for no speech gain; `low` dropped visual steps.

Google Meet recordings (Fathom, Leexi): first `detect-screenshare <name>.gemini.mp4` (seconds per
hour, local) → `<name>.gemini.screenshare.json`, then pass it as `--ranges`: frames only while a
screen is shared, audio throughout; no share → audio only. Not Meet (Loom, Zoom, phone) → the JSON
says `full-fallback` and the whole video is sent. 10 Meet calls: 42% of video seconds skipped,
recall 1.00; a 29-minute call cost $0.14 instead of ~$0.17. Transcript cues ("share my screen")
missed most share starts: don't use them.

Read the file; check speech, visual changes, timestamps and coverage against the recording;
report gaps.

Small-text UI walkthroughs: Flash confidently invented most on-screen text, example data and
screen names on a 29-minute 720p share (2026-09-24). Compare 3–4 source frames first; if they
disagree, use [video-frames-for-vision](../video-frames-for-vision/SKILL.md) as the source and the
Gemini draft as hypotheses. `gemini-3.1-pro-high` did not read small opaque IDs better.

T3 0.0.40 / ACP 1.1.1 has no media tool, so T3 workers cannot watch video; they run
`transcribe-gemini` (or an orchestrator runs native `agy`). If a future runtime supports media: `t3-spawn-thread --model gemini` with a
`🏓` title and absolute paths; verify the file before settling; never delegate recursively. All
routes fail → report the blocker and hand over the prepared video + prompt for AI Studio.
Model comparisons: fresh conversations, identical media, held-out reference evidence.

Follow-up prompts / T3 threads from the verified transcript: [recording-followups](../recording-followups/SKILL.md).

## No Gemini available

Seen blockers: no API key and `agy` weekly quota 429, video-summary 503, no Antigravity (Windows + Codex,
Claude Code on a subscription). Frames: `select-frames` from
[video-frames-for-vision](../video-frames-for-vision/SKILL.md). Speech: vendor transcript
(Leexi/Fathom), else `transcribe-local`. Second ASR opinion when names/products/decisions matter
(optional; prints "skipped" without `OPENAI_API_KEY`):
`transcribe-openai source.webm --align leexi-call.json --hint "<≤20 riskiest terms>" --out transcript.openai.md`.
It keeps the vendor's speakers/timestamps and swaps in OpenAI's words: prefer it for names, the
vendor for fillers/timing, flag disagreements. Evidence and model choices: [local-route.md](local-route.md).
