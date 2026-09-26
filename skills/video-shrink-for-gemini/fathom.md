# Fathom URL → transcript or media

`download-fathom --help` lists modes and artifacts. Needs `FATHOM_API_KEY` from the operator's
existing environment (mise projects: `mise exec -- download-fathom …`); check the project's
Fathom integration before asking for a share link. No browser or cookies involved.

- `--transcript-only`: raw API JSON, segment timings and `transcript.md`; no yt-dlp/ffmpeg/Gemini/ASR,
  so stop there. Works for an accessible call without a share URL. Keep Fathom's speaker labels
  and wording; label interpretations separately (Fathom can misattribute speakers).
- Media (`--timings` adds the timing reference): the helper matches the call via
  `GET /external/v1/meetings` and passes its **existing** `share_url` to yt-dlp. A `/share/TOKEN`
  URL needs no API unless `--timings`. `--resolve-only` checks resolution only.

Hard rule: never create or change sharing permissions; missing access is a blocker to report,
not an account setting to flip. `--out` must be git-ignored (the helper refuses otherwise);
treat all artifacts as private. ffprobe the streams and duration after download.

The timestamped text is the default speech layer: as literal as local Whisper, plus speakers
([local-route.md](local-route.md)). It still has wrong words/speakers and sees no screen, so it
does not replace Gemini or frame reading. Keep its provenance distinct; preserve Gemini drafts
when correcting timings.
