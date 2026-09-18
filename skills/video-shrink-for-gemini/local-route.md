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
- No speaker labels from local ASR. [Fathom timings](fathom.md) supply speakers when available.

Frames: scene threshold 0.1 gave 41 frames for a 42-minute meeting with screen share (0.05 → 94,
0.2 → 32). At 1280×720 that is ≈1.2k Claude visual tokens per frame; a blind Opus narration of all
41 frames cost ≈91k tokens and 4 minutes, and its three legible run UUIDs matched held-out
references exactly. Threshold 0.1 still skipped two page states a human check had listed (a page
switch with similar layout, and a scrolled form), so treat sampled frames as incomplete and lower
the threshold for dense UI sessions. Extract frames from the original, never from the shrunk file.

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

## Recipe

```sh
transcribe-local --language nl recording.mp4
scene-frames --threshold 0.1 recording.mp4
```

Then have the agent read the `manifest.tsv` frames in order and write `<name>.transcript.md` with a
speech section built from the whisper SRT and a visual section per frame. Only then take targeted
crops for IDs, and finish with held-out verification.
