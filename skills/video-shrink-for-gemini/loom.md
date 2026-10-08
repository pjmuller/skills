# Loom URL → transcript + media

`download-loom URL --out PRIVATE_DIR [--transcript-only|--resolve-only]` (`--help`). Cookie-free,
no API key: public share pages embed Loom's logged-out Apollo cache (`window.__APOLLO_STATE__`) with
video metadata and a signed CloudFront URL to Loom's own transcription JSON (`phrases[].ts/value`).
Missing there → the helper retries the plain `FetchVideoTranscript` GraphQL query; still nothing →
prints "transcript unavailable without login; continue Gemini-only" and carries on.

Artifacts: `<id>.loom.json` (title, owner, duration, created, privacy), `<id>.loom-transcript.md`
(timestamped, provenance header), `<id>.mp4` (yt-dlp, ≤1080p, merged audio). `--out` must be
git-ignored. Never change sharing settings.

The Loom text is Whisper ASR without speaker labels: use it as the literal speech layer, Gemini for
screen actions and corrections; flag disagreements. Verified on a public 105 s share (2026-10-08): speech merged cleanly, but Gemini
invented most spreadsheet text and a scroll; frames every 5 s were the screen source.

Not covered: password-protected or workspace-only videos (`needs_password`, private visibility). A
logged-in browser cookie would unlock those plus comments/chapters; the helper stays cookie-free by
design, so report them as blocked rather than adding a session.
