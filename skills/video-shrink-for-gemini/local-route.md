# Local route: ASR + sampled frames (no Gemini)

Two separate signals: speech transcript + scene frames read as images by a vision-capable coding
agent. Not continuous perception: frames cannot prove a click, save or anything between samples;
say so in the output.

```sh
transcribe-local --language nl recording.mp4   # only without a vendor transcript
select-frames recording.mp4                    # from the original, never the shrunk file
```

Then fill [annotate-prompt.md](../video-frames-for-vision/annotate-prompt.md): frames in manifest
order next to the transcript, targeted ID crops only afterwards, then held-out verification.
Codex specifics: [codex-recipe.md](../video-frames-for-vision/codex-recipe.md#codex-cli-gotchas).

## Why local ASR is mandatory on a subscription

Claude accepts images and PDF, no audio/video
([vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)); Codex CLI attaches
images only ("cannot access audio" for MP3/WAV, verified 2026-09-25). Audio must go through a model
first: vendor transcript, `transcribe-local`, or `transcribe-openai`.

Install elsewhere: Apple Silicon `uv tool install mlx-whisper` (plus `parakeet-mlx` for
word-timestamp clip cutting; models land in the Hugging Face cache on first run); other OS: closest
runner for whisper-large-v3-turbo. Verify with `scripts/install --check` and a 30 s file.

## Speech evidence (Apple M5 / 32 GB)

- **Prefer the vendor transcript (Fathom/Leexi) when it exists** (2026-09-18, Dutch two-speaker
  meeting, disagreement not error rates): Fathom–Whisper 17%, Fathom–Gemini 31%, Whisper–Gemini 33%;
  Whisper errs with nonsense words, Fathom with domain terms; the vendor adds speakers and timestamps.
  Local ASR is for recordings without one or a disputed passage.
- `whisper-large-v3-turbo` (`transcribe-local` default): ≈25× realtime, no speaker labels.
  `--condition-on-previous-text False` (set by the script) is required: otherwise the file looped
  after ~25 min (one filler 143×). The script also sets `--hallucination-silence-threshold 2
  --no-speech-threshold 0.5 --compression-ratio-threshold 1.8` (without them cross-talk in Dutch
  standups degenerated into "Ehm…/Ja." loops); `--prompt "<names>"` passes a vocabulary as
  whisper's `--initial-prompt`. The shrink preset's 32 kb/s mono audio transcribes as well as
  the original.
- English (2026-10-08, vs AssemblyAI, three podcasts): turbo on par with Parakeet, fewest missed
  names. `parakeet-mlx` + `parakeet-tdt-0.6b-v2` ≈2× faster for word-timestamp clip cutting.
  `parakeet-tdt-0.6b-v3` on Dutch: 26–36%, many deletions, rejected. `parakeet-unified-en-0.6b`
  (Handy's default) needs transcribe.cpp, lags words 210 ms, fails silently past 120 s chunks.
  Qwen3-ASR, Granite, Canary give no usable word timestamps.
- `transcribe-openai` second opinion (2026-09-25, Flemish standup, aligned per Leexi paragraph, 20-word
  hint: 5 min in 5 s, ≈$0.03): fixed every product name Leexi got wrong, still missed a rare device
  name, ≈10% fewer words (drops repeated fillers), so the vendor stays the literal/timing layer.
  `gpt-transcribe` best words but no timestamps (hence `--align`); `-diarize` takes no prompt and
  has worse names; `gpt-audio` chat models invented sentences and swapped speakers: never a speech
  layer. Long hints dilute: ≤20 words, the previous turn carries context.

## Frames and opaque IDs

`select-frames` replaced ffmpeg `select=gt(scene,0.1)`, which missed same-layout page switches and
scrolled forms and kept talking heads. A 1280×720 frame ≈ 1.2k Claude visual tokens.

Original 720p frame, ≤3 crops at 3× lanczos: Claude (Opus, Read) read a 36-char UUID with 35 right
and one honest `?`; Codex (gpt-6-astra) returned several wrong characters, once at medium
confidence. Use Claude for ID crops, require `?`, treat any fully "read" ID as a candidate
([exact-identifiers.md](exact-identifiers.md)). Synthetic clean address bars were read perfectly by
both: synthetic tests overstate real fidelity.

## Gemini versus local (same 42-minute recording, 2026-09-18)

Gemini 3.8 Flash High: aligned transcript + visual timeline in ~150 s; 31% speech disagreement
(paraphrases, merges short turns, worse late in the file), speakers 67% agreement, honest
UNREADABLE for UUIDs but missed an editor URL Opus read from a frame. Whisper: 17%, literal, no
speakers. Gemini for the continuous narrative, local for literal words and exact screen text; both
need held-out checks.
