# Loom URL → transcript + media

`download-loom URL --out DIR [--transcript-only|--resolve-only]`. Cookie-free, no API key: public
share pages embed Loom's logged-out Apollo cache (`window.__APOLLO_STATE__`) with metadata and a
signed URL to Loom's transcription JSON; missing there → the helper retries the `FetchVideoTranscript`
GraphQL query; still nothing → "transcript unavailable without login; continue Gemini-only".

Artifacts: `<id>.loom.json` (title, owner, duration, created, privacy), `<id>.loom-transcript.md`
(timestamped, provenance header), `<id>.mp4` (yt-dlp, ≤1080p).

The Loom text is Whisper ASR without speakers: literal speech layer; Gemini adds screen actions and
corrections; flag disagreements. Public 105 s share (2026-10-08): speech merged cleanly, but Gemini
invented most spreadsheet text and a scroll; frames every 5 s were the screen source.

Password-protected or workspace-only videos (`needs_password`, private): report as blocked. The
helper stays cookie-free by design; never add a logged-in session.
