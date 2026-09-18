# Fathom URL → local media

Use `download-fathom 'https://fathom.video/calls/123456' --out /private/run --timings`.
Load `FATHOM_API_KEY` from the operator's existing environment/secrets setup; for a
mise-managed project, run via `mise exec -- download-fathom ...`. Do not ask for a
share link until checking the existing project's Fathom integration/environment.
PJ's existing integration lives in Rootcause's `fathom-interviews` skill; its mise
environment already supplies the API key. No browser or cookie extraction is needed.

The helper lists `GET /external/v1/meetings` with `X-Api-Key`, follows pagination,
matches the call URL, then passes its existing `share_url` to yt-dlp. A supplied
`/share/TOKEN` works without API access unless `--timings` is requested. `--resolve-only`
checks resolution without media download. It never creates sharing permissions.
Missing access is a specific blocker, not a reason to change account settings.

`--out` must be ignored when inside git; outside git, use a private directory.
Artifacts: `source.json`, `source.<ext>`, optionally `fathom-timings.json` from
`GET /external/v1/recordings/{recording_id}/transcript`. Treat all as private. Inspect
video/audio streams and duration using ffprobe after download.

The timestamped text is the default speech layer when it exists: measured as literal as local
Whisper, with speakers and timestamps ([local route](local-route.md)). It can still have wrong
words and speakers, and it sees no screen: it does not replace Gemini audiovisual perception or
frame reading. Keep its provenance distinct, and preserve Gemini drafts when correcting timings.
