# Fathom URL → transcript or media

`download-fathom --help` lists modes and artifacts. Needs `FATHOM_API_KEY` from the operator's
environment (mise projects: `mise exec -- download-fathom …`); check the project's Fathom
integration before asking for a share link. No browser or cookies.

- `--transcript-only`: raw API JSON, segment timings and `transcript.md`; works for an accessible
  call without a share URL. Keep Fathom's speaker labels and wording; label interpretations
  separately (Fathom can misattribute speakers; check one that decides an owner with
  [speaker-frames](../video-frames-for-vision/SKILL.md#who-said-it-speaker-frames)).
- Media (`--timings` adds the timing reference): the helper matches the call via
  `GET /external/v1/meetings` and passes its **existing** `share_url` to yt-dlp. A `/share/TOKEN`
  URL needs no API unless `--timings`. `--resolve-only` checks resolution only.

Never create or change sharing permissions; artifacts are private. ffprobe streams and duration
after download.

The timestamped text is the default speech layer: as literal as local Whisper, plus speakers
([local-route.md](local-route.md)), but with wrong words/speakers and no screen, so it does not
replace Gemini or frame reading. Keep its provenance distinct; preserve Gemini drafts when
correcting timings.
