# Run it in Codex (Windows or macOS), no Gemini

Codex CLI reads images, not video or audio (verified 2026-09-25 on 0.156.1 and 0.157.0: an
attached MP4/WAV returns "couldn't be processed" with exit 0). So: transcript from the vendor,
frames from `select-frames`, and Codex reads the frames as images.

## Install once

Windows (PowerShell), then restart the shell:

```powershell
winget install --id=astral-sh.uv -e
winget install "FFmpeg (Essentials Build)"
uv --version; ffmpeg -version; ffprobe -version
```

macOS: `brew install uv ffmpeg`. Codex CLI itself per OpenAI's instructions. Register the skills in
the repository you work in: `pnpm dlx skills add pjmuller/skills -s leexi -s video-frames-for-vision -y`
(or take the committed copy that repository already carries).

Leexi key: `LEEXI_KEY_ID` / `LEEXI_KEY_SECRET` in the environment the Codex session inherits
(PowerShell: `setx LEEXI_KEY_ID "..."`, or a `mise`/`.env` file the project already loads).

## Per meeting

Say to Codex, in the repository: *"verwerk de Leexi-meeting van vandaag rond 14u"* or *"maak
van deze Leexi-call een to-do lijst met prompts: <url>"*. The agent then runs:

```powershell
uv run --script .agents\skills\leexi\scripts\download-leexi --at "today 14:00"        # → .local\leexi\<uuid>\
uv run --script .agents\skills\video-frames-for-vision\scripts\select-frames .local\leexi\<uuid>\source.webm
```

(`--out` defaults: `.local\leexi\<uuid>\` and `…\source.frames\`; `.local/` must be git-ignored.)
Then it fills [annotate-prompt.md](annotate-prompt.md) and follows it: transcript first, frames in
batches of 12–24 with notes persisted to `screen-notes.md`, then `analysis.md`. Expect roughly
1.1k input tokens per 1280-px frame; the default cap of 120 frames is ≈130k image tokens over the
whole session, fine in batches. A cheaper pass: `select-frames --max-frames 60 --views-per-page 2`.

Codex sandbox notes: work from the repository root (`-C`) so `.local/` is inside the writable
workspace; hidden/ignored directories are still readable by path, but `rg --files` skips them, so
open frames by the exact paths from `manifest.md`. Headless (`codex exec`) attaches images only
via repeated `-i` and cannot loop over a manifest by itself; the interactive session with its
image tool is the intended mode.

## What the reader gets

`analysis.md`: coverage, screen events with exact on-screen text, topics with decisions and
quotes, action items per owner, and one ready-to-paste prompt per action item for a new Codex
session. Prompts contain the meeting evidence (timestamps, frame ids), so they work outside the
run directory.
