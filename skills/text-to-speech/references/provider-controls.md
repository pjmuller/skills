# Provider controls

Checked **2026-09-30** against official docs. Recheck before changing API requests or claiming a model supports a control.

## ElevenLabs

- The CLI's `voices --provider elevenlabs` searches only [voices available to the account](https://elevenlabs.io/docs/api-reference/voices/search) (`GET /v2/voices`). Its language, accent, gender, and search filters narrow candidates; `--model` selects the model-specific `verified_languages` evidence to display. Without `--model`, that evidence is absent. The wider [shared Voice Library](https://elevenlabs.io/docs/api-reference/voices/voice-library/get-shared) is a separate `GET /v1/shared-voices` catalog, not searched by this CLI; adding one to the account is a separate mutation. Listening **on the intended model** decides. Voice names and a good result on another model do not establish that model's accent.
- [Eleven v4 and v4 Turbo](https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech) use **Stability** and **Similarity** controls; **Style and Speed sliders are unavailable** for those models. Do not pass `--speed` with v4. Both accept [audio tags](https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/how-do-audio-tags-work-with-eleven-v3-and-v4) such as a short bracketed delivery cue. Tags can affect performance; audition the actual take. v4 does not support SSML break tags.
- Earlier supported models have different controls; the [text-to-speech guide](https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech) documents model-specific Speed and pause behavior. Select the model first, then set only its valid options. In this CLI, Eleven options include `--stability`, `--similarity`, `--speed`, `--tag`, and `--seed` when supported.
- [Voice Design](https://elevenlabs.io/docs/api-reference/text-to-voice/design/) can return preview voices from a description. Adding the chosen preview to an account is another step; do it only when a reusable new voice is part of the task.

## Gemini

- [Gemini 3.8 Flash TTS](https://ai.google.dev/gemini-api/docs/speech-generation) uses the **Interactions API**. Its `input` text is the verbatim transcript; sustained delivery goes in the `speech_metadata.style` annotation, and the selected voice goes in `generation_config.speech_config`. The default single-request output is WAV. Do not reuse older Gemini 3.1 prompt formats that mix spoken words with stage directions.
- Search [Gemini voices](https://ai.google.dev/api/voices) (`GET /v1beta/voices`) by `language_code`, `region_code`, `accent`, gender, or context. A prebuilt voice plus a regional style prompt is an experiment, not proof of a native accent. For a persistent accent/persona, consider a matching catalog voice or [Voice Design](https://ai.google.dev/gemini-api/docs/voice-design); a stored design writes to the selected project and returns a reusable voice ID.
- The CLI's Gemini `--style` maps to `speech_metadata.style`. It does not set the speaker's innate accent. Google documents no seed control for these TTS requests, and the CLI exposes none for Gemini. `--take` changes only the local cache ID; it sends the same provider request for another performance.

## Fair listening and processing

- Use the same short spoken words for voice trials, except when the wording itself is under test. Mark different wording separately. Match playback loudness before comparing voices and keep provider/model/settings alongside each raw file.
- FFmpeg [atempo](https://ffmpeg.org/ffmpeg-filters.html#atempo) changes tempo; its [implementation](https://ffmpeg.org/pipermail/ffmpeg-devel/2012-June/125646.html) preserves pitch. Trimming measured silence changes pauses without speeding the articulated words.
- FFmpeg [ebur128](https://ffmpeg.org/ffmpeg-filters.html#ebur128) measures integrated loudness and true peak. For a set of short lines, measure → static gain → limiter → verify the encoded clips. FFmpeg [loudnorm](https://ffmpeg.org/ffmpeg-filters.html#loudnorm) can operate dynamically and can fall back from requested linear mode; do not assume a one-pass setting preserved the take's dynamics.
