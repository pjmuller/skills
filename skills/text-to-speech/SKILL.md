---
name: text-to-speech
description: "Use to produce prerecorded speech with ElevenLabs or Gemini TTS (\"generate a voice-over\", \"find a voice\", \"read this in a regional accent\", \"compare these takes\", \"make the clips equally loud\"). Not live voice agents or transcription."
---

# Text to speech

`scripts/tts.py` (`models`, `voices`, `generate`, `normalize`, `compare`; `--help` for flags) does **one
generation request at a time** plus read-only discovery and offline processing. It does not converse,
transcribe, create stored voices, or pick a provider account.

## Choose, then generate

1. Fix the exact spoken transcript and delivery goal. Write dates, numbers, names and abbreviations as
   they should sound; keep provider instructions out of the spoken text.
2. `models` / `voices` find candidates. ElevenLabs `voices` searches only voices **already on the account**
   (the shared library is separate); `--model` shows model-specific verification metadata. For a regional
   accent prefer a voice whose **catalog language/accent metadata** matches; a style prompt on an unrelated
   voice is only a trial. No fit → [specific-voice workflow](references/provider-controls.md#find-or-design-a-specific-voice).
   Audition 2-3 on the **same short verbatim text** at matched level; judge pronunciation, accent, pace and
   phone/speaker intelligibility by ear **on the intended model** (an accent on one model is unverified on another).
3. Pick the voice before the full script. Generate independent lines separately when partial replacement
   matters. Listen to the audio, not the HTTP result; takes vary.
4. Keep raw audio and its key-free JSON sidecar (text, provider, model, voice, controls, fingerprint)
   together. Identical requests reuse the cached take; regenerate only changed lines. `--take` only changes
   the local cache identity for a deliberate alternate performance, **not** the provider request or a seed.
   Never overwrite the chosen original to compare.
5. Side-by-side playback: `normalize` (FFmpeg; static gain + limiter, raw kept) evens loudness, `compare`
   builds a local HTML page from existing sidecars (no paid calls). Listen again after processing.

Run from the **consumer project root**; keep recordings under its artifacts, outside the replaceable skill tree:

```bash
take="$(uv run --no-project .agents/skills/text-to-speech/scripts/tts.py generate --provider elevenlabs --text-file line.txt --voice VOICE_ID --model eleven_v4 --out-dir artifacts/tts/takes)"
uv run --no-project .agents/skills/text-to-speech/scripts/tts.py compare --sample "$take" --out-dir artifacts/tts/comparison --normalize
```

**Keys and account mutations:** the caller selects the account. `ELEVENLABS_API_KEY` / `GEMINI_API_KEY` come
from the invoking project's environment, or `--api-key-stdin` (one line from an authorized channel). Never
search other repos/accounts for a fallback key, store keys in this skill, or put them in sidecars. A requested
generation is authorized; saving or adding a **voice** to the account is a separate mutation, only when the task calls for it.

Model controls, catalog filters, Voice Design, tempo/silence edits and loudness method:
[provider controls](references/provider-controls.md) (checked 2026-09-30; verify linked docs before relying on a
model-specific claim). Tempo (`atempo`) and silence trimming are edits outside this CLI; neither replaces a voice
with the right natural pacing. Record any external edit in provenance before selecting that take.
