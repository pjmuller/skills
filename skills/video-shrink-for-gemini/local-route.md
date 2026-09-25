# Local route: ASR + sampled frames (no Gemini)

Two separate signals: local speech transcription, plus scene-change frames read as images by an
image-capable coding agent. It is **not** continuous audiovisual perception. Sampled frames cannot
prove a click, a save, or anything that happened between frames — state that limit in the output.

## Why local ASR is mandatory on a subscription

Claude's API accepts images (JPEG/PNG/GIF/WebP) and PDF only; no audio or video input
([vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)). Codex CLI attaches
images only, via `--image/-i`
([developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)). So neither
Claude Code nor Codex can listen to a recording — audio has to go through a local model first.
Verified 2026-09-18.

## Measured (Apple M5 / 32 GB, 2026-09-18)

Dutch two-speaker meeting audio, 3-minute spans, reference = a vendor transcript, so the figures are
**disagreement rates, not pure error rates**.

- `mlx-community/whisper-large-v3-turbo`: ≈25× realtime (3 min of audio in ~7 s after the one-time
  model download; a full 42-minute recording in ~2.5 min), 16–26% word disagreement on spans,
  17% over the full recording (10–12% in the first ten minutes, 21–25% later). Preferred.
- Long recordings need `--condition-on-previous-text False` (the script sets it): with the default,
  the same 42-minute file drifted into repetition loops after ~25 minutes (one filler word emitted
  143 times) and disagreement rose to 44%.
- `parakeet-tdt-0.6b-v3`: faster (~4 s) but 26–36%, with many deletions.
- The shrink preset's 32 kb/s mono audio transcribed as well as the original (16.7% vs 16.2%).
- No speaker labels from local ASR.
- **If the call has a Fathom transcript, use it as the speech layer and skip local ASR.** Three-way
  check on the same recording: Fathom–Whisper 17%, Fathom–Gemini 31%, Whisper–Gemini 33% word
  disagreement, and a hand-read sample of Fathom/Whisper substitutions split roughly evenly (Whisper
  makes more nonsense-word errors, Fathom more domain-term errors). Fathom is as literal as local
  Whisper, adds speakers and timestamps, costs nothing, and `download-fathom --timings` already
  fetches it. Local ASR is for recordings without a vendor transcript (raw screen captures, Loom,
  exports) or as a tie-breaker on a disputed passage.

Frames: the sibling `video-frames-for-vision` skill (`select-frames`) replaced the earlier
scene-change sampler (ffmpeg `select=gt(scene,0.1)`: 41 frames for a 42-minute meeting, but it
skipped a same-layout page switch and a scrolled form, and it kept talking-head frames). Extract
frames from the original, never from the shrunk file; at 1280×720 a frame costs ≈1.2k Claude
visual tokens, and a blind Opus narration of 41 frames cost ≈91k tokens and 4 minutes.

## Opaque IDs

Claude Code (Opus, Read tool, ≤3 crops per frame at 3× lanczos upscale) read a 36-character UUID
from an original 720p share frame with 35 correct characters and one honest `?`. Codex
(gpt-6-astra, low and high effort, same crops) returned several wrong characters, once at medium
confidence. Use Claude for ID crops, require `?` for uncertain characters, and treat any fully
"read" ID as a candidate until independently checked — see
[exact-identifiers.md](exact-identifiers.md). Synthetic clean address bars at 11–15 px were read
perfectly by both models, so synthetic tests overstate real fidelity.

## Codex CLI gotchas

Put the prompt **before** `-i`: the variadic `-i` swallows a trailing prompt. Close stdin
(`</dev/null`) in non-interactive shells, or `codex exec` blocks reading it. `codex exec` prints
`tokens used` at the end; one 1280×720 frame round trip cost ~12–34k tokens including system
overhead.

## Gemini versus the local route (same 42-minute recording, 2026-09-18)

Native Gemini 3.8 Flash High wrote a 9.4k-word aligned transcript plus visual timeline in ~150 s
(thinking 2m17s / 16.9k tokens; input tokens are not exposed by the CLI). Speech disagreement with
the vendor transcript was 31% (20% early, 56% late): Gemini paraphrases and merges short exchanges,
so it reads fluently but is not literal. Local Whisper was 17% and literal. Gemini labelled speakers
(67% agreement with the vendor's labels); Whisper cannot. Gemini quoted no UUIDs at all (honest
UNREADABLE, but it also missed an editor URL that Opus read exactly from a frame). Gemini's real
advantage is continuous coverage and one aligned narrative. Use Gemini for the narrative draft when
quota allows, the local route for the literal transcript and exact on-screen text, and both need
held-out verification.

## Recipe

```sh
transcribe-local --language nl recording.mp4   # skip when a vendor transcript (Leexi/Fathom) exists
select-frames recording.mp4                    # video-frames-for-vision: manifest.md + frames/ + sheets/
```

Then follow `video-frames-for-vision`'s annotation prompt: the agent reads the manifest frames in
order next to the timestamped transcript and writes the analysis; only then take targeted crops
for IDs, and finish with held-out verification.
