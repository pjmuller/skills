---
name: text-to-speech
description: Find and audition voices, generate spoken audio with ElevenLabs or Gemini TTS, normalize clips, and compare takes offline. Use for prerecorded speech, not live voice agents or transcription.
---

# Text to speech

Use this skill for prerecorded speech where the spoken words, voice, accent, and output files matter. The bundled `scripts/tts.py` covers **one generation request at a time** plus read-only discovery and offline processing. It does not run a live conversation, transcribe audio, create stored voices, or pick a provider account for you.

## Choose, then generate

1. Set the exact spoken transcript and delivery goal. Write dates, numbers, names, and abbreviations as they should sound. Keep provider instructions separate from spoken text.
2. Use `models` and `voices` to discover candidates. ElevenLabs `voices` searches voices **already available to the account**; its wider shared library is a separate catalog. Pass `--model` to `voices` for model-specific verification metadata. For a regional accent, prefer a voice with matching **catalog language/accent metadata**; a style prompt on an unrelated voice is only a trial. Audition a small set (often 2–3) on the **same short verbatim text**, with the same playback level. Judge pronunciation, regional accent, pace, and phone/speaker intelligibility by ear **on the intended model**; an accent heard on one model is not verified on another.
3. Choose a voice before generating the full script. Generate each independent line separately when partial replacement matters. Check the audio, not just the HTTP result; models can vary between takes.
4. Keep the raw audio and its key-free JSON sidecar together. They record exact text, provider, model, voice, controls, and the request fingerprint. Reuse an identical cached take; regenerate only changed lines. Use `--take` only to request a deliberate alternate performance of the same text and settings. It changes the local cache identity, **not** the provider request or a seed. Never overwrite the chosen original just to compare it.
5. If clips will be played side by side, use `normalize` to make their loudness comparable, then `compare` to build a **local HTML page from existing sidecars**. `compare` makes no paid synthesis calls. Listen again after processing to catch clipping or unnatural pauses.

Run commands from the **consumer project root** with the installed skill path. Keep recordings and sidecars under that project's artifacts, outside the replaceable skill tree. `--help` lists exact flags; the core commands are `models`, `voices`, `generate`, `normalize`, and `compare`. Generation requires a text file, voice, model, output directory, and provider. A neutral example:

```bash
take="$(uv run --no-project .agents/skills/text-to-speech/scripts/tts.py generate --provider elevenlabs --text-file line.txt --voice VOICE_ID --model eleven_v4 --out-dir artifacts/tts/takes)"
uv run --no-project .agents/skills/text-to-speech/scripts/tts.py compare --sample "$take" --out-dir artifacts/tts/comparison --normalize
```

The caller selects the account. `ELEVENLABS_API_KEY` and `GEMINI_API_KEY` are accepted from the invoking project's environment; `--api-key-stdin` accepts one line from an already authorized credential channel. Do not search other repositories/accounts for a fallback key, store keys in this skill, or include them in sidecars. A requested generation is authorized work; creating or adding a **saved voice** is a separate account mutation and should happen only when the task calls for it.

For model controls, catalog filters, Voice Design, and current API links, read [provider controls](references/provider-controls.md) only when choosing a provider or changing synthesis settings. Provider capabilities change; verify the linked official docs before relying on a model-specific claim. This reference was checked **2026-09-30**.

## Processing choices

- `normalize` is optional; it uses FFmpeg when installed. For short clips, measure with `ebur128`, apply one **static gain** and a peak limiter to a chosen target, then measure the encoded result. Per-clip dynamic `loudnorm` can change a comparison's phrasing dynamics; its linear mode may fall back to dynamic when constraints fail. Keep the raw file intact.
- Changing **tempo** and shortening **silences** solve different problems. If requested outside this CLI, FFmpeg `atempo` changes tempo while preserving pitch; editing quiet gaps preserves speaking speed. Neither is a substitute for choosing a voice whose natural pacing works. Record any external edit in provenance before using it as a selected take.
- If voice metadata does not support the required accent, audition a genuinely regional catalog voice or consider provider Voice Design. An instruction to “sound regional” does not prove a native regional accent.
