# Local route: ASR + sampled frames (no Gemini)

Two separate signals: speech transcript + scene frames read as images by a vision-capable coding
agent. Not continuous perception: frames cannot prove a click, save or anything between samples;
say so in the output.

## Why local ASR is mandatory on a subscription

Claude accepts images and PDF, no audio/video
([vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)); Codex CLI attaches
images only (0.156/0.157 answer "cannot access audio" for MP3/WAV). Audio must go through a model
first: vendor transcript, `transcribe-local`, or `transcribe-openai`. Verified 2026-09-25.

## Measured (Apple M5 / 32 GB, 2026-09-18)

Dutch two-speaker meeting, reference = vendor transcript, so figures are **disagreement, not
error, rates**.

- **Prefer the vendor transcript (Fathom/Leexi) when it exists.** Fathom–Whisper 17%,
  Fathom–Gemini 31%, Whisper–Gemini 33%; a hand-read sample split substitutions evenly (Whisper:
  nonsense words; Fathom: domain terms). The vendor adds speakers and timestamps for free. Local
  ASR is for recordings without one (screen captures, Loom, exports) or a disputed passage.
- `mlx-community/whisper-large-v3-turbo` (`transcribe-local` default): ≈25× realtime (42 min in
  ~2.5 min), 17% over the full file. `--condition-on-previous-text False` (set by the script)
  is required: with the default, the file looped after ~25 min (one filler 143×, 44%).
- `parakeet-tdt-0.6b-v3`: faster, 26–36% with many deletions. Rejected.
- The shrink preset's 32 kb/s mono audio transcribes as well as the original. No speaker labels.

Frames come from `select-frames` ([video-frames-for-vision](../video-frames-for-vision/SKILL.md)),
from the original, never the shrunk file. It replaced ffmpeg `select=gt(scene,0.1)`, which missed
same-layout page switches and scrolled forms and kept talking heads. A 1280×720 frame ≈ 1.2k
Claude visual tokens.

## OpenAI transcription API as a second opinion (2026-09-25)

`transcribe-openai` (flags and modes: `--help`). Flemish standup, 5-minute slice, aligned per
Leexi paragraph with a 20-word hint: 5 s, ≈$0.03; fixed every product name Leexi got wrong,
still missed a rare device name, ≈10% fewer words (normalises punctuation, drops repeated
fillers), so the vendor stays the literal/timing layer. Models: `gpt-transcribe` best words but
no timestamps (hence `--align`); `gpt-4o-transcribe-diarize` speakers + timestamps but no prompt
and worse names; `whisper-1` segment timestamps, decent names; `gpt-audio-1.5` chat invented
sentences and swapped speakers: never a speech layer. Long paragraphs dilute the hint: keep it
short (≤20 words) and let the previous turn carry context (the script does).

## Opaque IDs

On an original 720p frame with ≤3 crops at 3× lanczos, Claude Code (Opus, Read) read a 36-char
UUID with 35 correct and one honest `?`; Codex (gpt-6-astra, low/high effort) returned several
wrong characters, once at medium confidence. Use Claude for ID crops, require `?`, and treat any
fully "read" ID as a candidate ([exact-identifiers.md](exact-identifiers.md)). Synthetic clean
address bars were read perfectly by both, so synthetic tests overstate real fidelity.

## Codex CLI gotchas

See [codex-recipe.md](../video-frames-for-vision/codex-recipe.md#codex-cli-gotchas).

## Gemini versus the local route (same 42-minute recording, 2026-09-18)

Gemini 3.8 Flash High: 9.4k-word aligned transcript + visual timeline in ~150 s; 31% speech
disagreement (20% early, 56% late) because it paraphrases and merges short turns; speaker labels
67% agreement; quoted no UUIDs (honest UNREADABLE, but missed an editor URL Opus read exactly from
a frame). Whisper: 17%, literal, no speakers. Use Gemini for the continuous narrative when quota
allows, the local route for literal words and exact on-screen text; both need held-out checks.

## Recipe

```sh
transcribe-local --language nl recording.mp4   # only without a vendor transcript
select-frames recording.mp4                    # manifest.md + frames/ + sheets/
```

Then fill [annotate-prompt.md](../video-frames-for-vision/annotate-prompt.md): frames in manifest
order next to the transcript, targeted ID crops only afterwards, then held-out verification.
