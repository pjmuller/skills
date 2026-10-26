---
name: video-shrink-for-gemini
description: "Use for \"transcribe this video/call\", \"what happens in this recording\", a product-feedback or silent UI walkthrough, a Fathom/Loom/Leexi/SyncUp link, or shrinking a video for Gemini: ends in a verified Markdown transcript or visual narration. No Gemini → video-frames-for-vision."
---

# Video → Gemini

Deliverable: `<name>.transcript.md` on disk (not a chat reply, not a paste-prompt for the user),
built from `<name>.gemini.mp4` + `<session>.gemini-prompt.md` beside the source. Helpers (`--help`
each, which also holds their measurements): `shrink-video`, `build-prompt`, `download-fathom`,
`download-loom`, `detect-screenshare`, `transcribe-gemini`, `transcribe-local`, `transcribe-openai`.
`scripts/install` links them; `--check` verifies deps and the key.

Route: `transcribe-gemini` (Gemini API) → continuous audiovisual narrative; native `agy` only
without an API key ([agy-route.md](agy-route.md)). No Gemini, or small on-screen text must be
exact → [No Gemini available](#no-gemini-available).

## Inputs

All `--out` dirs must be git-ignored and private (the helpers refuse otherwise). **Never create or
change sharing permissions**: missing access is a blocker to report.

- Fathom → [fathom.md](fathom.md). Transcript-only ask: `download-fathom URL --out DIR
  --transcript-only`, then stop (no media, Gemini or ASR).
- Loom share → [loom.md](loom.md): `download-loom URL --out DIR` (video + Loom's timestamped
  transcript, no login).
- Leexi URL/UUID/"today's call around 14:00" → [leexi](../leexi/SKILL.md) (`download-leexi`).
- ClickUp SyncUp → `clickup-core`'s `scripts/syncup.py URL --out DIR`
  ([reference](../clickup-core/reference.md#syncup-recordings)).

A vendor transcript is the speech layer; Gemini adds the screen and checks what the vendor heard.

## Inspect and choose mode

Look at 3–4 frames per clip; duration from `ffprobe`. Speech share ≈ `(duration − silence) /
duration` from `ffmpeg -i INPUT -af silencedetect=noise=-35dB:d=0.3 -f null -` (count silence
running to EOF; it measures audible activity, so music/clicks/quiet voices need a listen). No audio
or < ~20% → visual-first; speech-heavy → transcript-first; speech plus UI actions → mixed. Infer
project, speakers, language, purpose and skip ranges from context (`AGENTS.md`, project docs); ask
one question round only for gaps.

## Shrink

`shrink-video --preset normal FILE` (keep the original). API tokens follow duration, not bytes:
shrinking only speeds the upload. Native `agy` rejects attachments over **50 MiB**: add
`--max-bytes 48M` (overlapping parts + `<name>.chunks.md`); presets and stitching parts:
[compression.md](compression.md). Never `extreme` when small screen text matters.

## Prompt

**Ground the vocabulary first, every time**: 30–80 exact spellings seen written (people,
company/product/feature names, vendors, project enums, places, language variety such as Flemish
Dutch) from `AGENTS.md`/skill docs, glossaries, the vendor transcript's summary and speakers,
recent notes, ticket titles. Without them Gemini and OpenAI invent plausible spellings.

Fill [prompt-template.md](prompt-template.md), then `build-prompt --header header.md --out
session.gemini-prompt.md CONTEXT_FILE...` (appends context files verbatim). **Shared screen is an
artefact we hold** (repo deck, design export, ticket, mockup) → pass it as context: Gemini still
watches for timing but names slides/frames/labels by their real titles. Opaque URLs/record IDs →
[exact-identifiers.md](exact-identifiers.md) first.

**Product feedback walkthrough** (someone clicks through an app narrating changes): `--preset ui`
(1 fps: at 0.5 fps a Backspace-removed chip or 200 ms spinner falls between frames; same cost), keep
the template's feedback block, fill `{{WALLCLOCK}}` from the recording start (CleanShot filenames
carry it) so items line up with server logs, and pass the owning screen's skill doc plus the app's
UI copy (i18n/strings or templates) so Gemini quotes real labels. Then
[feedback-round](../recording-followups/feedback-round.md).

## Execute and verify

`transcribe-gemini <name>.gemini.mp4 --prompt session.gemini-prompt.md` → `<name>.transcript.md` +
`.usage.json` (tokens, USD at list), from any folder. Audio files go in as audio, no shrink;
WhatsApp voice notes: [whatsapp-bridge](../whatsapp-bridge/SKILL.md#voice-notes).

**Key routing**: `VIDEO_GEMINI_API_KEY` (env or `~/.config/transcribe-gemini/env`, chmod 600, never
in a repo), else a project's `GEMINI_API_KEY`, else `GOOGLE_CLOUD_PROJECT` + credentials (Vertex).
None → [agy-route.md](agy-route.md).

Defaults are tuned (`--help` has the numbers): `--thinking medium` (`low` drops visual steps, `high`
doubles cost for nothing); `--media-resolution high` decides whether screen text is read or
invented. `low` only for long videos whose screen doesn't matter.

**Google Meet recordings (Fathom, Leexi)**: `detect-screenshare <name>.gemini.mp4` →
`<name>.gemini.screenshare.json`; `shrink-video --crop <that json> SOURCE` → `<name>.gemini.crop.mp4`
(share tile fills the frame, no webcam faces); transcribe the crop with `--ranges <that json>`
(frames only while sharing, audio throughout). Not Meet → the JSON says `full-fallback`, whole video
is sent. Don't locate shares from transcript cues ("share my screen"): they miss most starts.

Verify: read the file; check speech, visual changes, timestamps and coverage against the recording;
report gaps. Its provenance header says "work from this text": downstream briefs point at **this**
file, never at raw vendor ASR, so no later thread re-watches the video.

Hard-won checks:
- Feedback walkthroughs: check every count and every "X is sorted/broken by Y" against a source
  frame or the data. A Flash pass once restated the speaker's misreading as visible fact while its
  own numbers showed the opposite, and misread 31 as 51.
- Small-text UI: uncropped low resolution invented most screen text and names; crop + high read
  0.88 of small facts ([evidence](compression.md#crop-the-meet-share-tile)). Opaque IDs still need
  source frames: if 3–4 disagree, [video-frames-for-vision](../video-frames-for-vision/SKILL.md) is
  the source and the Gemini draft only hypotheses. A Pro model did not read them better.
- Model comparisons: fresh conversations, identical media, held-out reference evidence.

T3 workers cannot watch video; they run `transcribe-gemini` (or an orchestrator runs native `agy`).
All routes fail → report the blocker and hand over the prepared video + prompt for AI Studio.
Follow-up prompts / threads from the verified transcript:
[recording-followups](../recording-followups/SKILL.md).

## No Gemini available

Seen: no API key plus `agy` weekly-quota 429, no Antigravity (Windows + Codex, Claude Code on a
subscription). Frames: `select-frames` ([video-frames-for-vision](../video-frames-for-vision/SKILL.md)).
Speech: vendor transcript, else `transcribe-local`. Names/products/decisions matter → optional second
ASR: `transcribe-openai source.webm --align leexi-call.json --hint "<≤20 riskiest terms>" --out
transcript.openai.md` (vendor speakers/timestamps, OpenAI's words; prefer it for names, the vendor
for timing; flag disagreements; "skipped" without `OPENAI_API_KEY`). Evidence and model choices:
[local-route.md](local-route.md).
