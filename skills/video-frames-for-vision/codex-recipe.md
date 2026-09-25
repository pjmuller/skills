# Run it in Codex (Linux / WSL / macOS), no Gemini

Codex CLI reads images, not video or audio (verified 2026-09-25 on 0.156.1 and 0.157.0: an
attached MP4/WAV returns "couldn't be processed" with exit 0). So: transcript from the vendor,
frames from `select-frames`, and Codex reads the frames as images.

## Install once

Everything lives where Codex runs. On a Windows machine that is the WSL distribution (Ubuntu),
not PowerShell: install nothing on the Windows side.

```sh
sudo apt install -y ffmpeg                      # Debian/Ubuntu/WSL; macOS: brew install ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh  # if `uv --version` fails
uv --version; ffmpeg -version | head -1; ffprobe -version | head -1
```

Register the skills in the repository you work in:
`pnpm dlx skills add pjmuller/skills -s leexi -s video-frames-for-vision -y`, or use the committed
copy that repository already carries. Optional: each skill's `scripts/install` links its commands
into `~/.local/bin`; `uv run --script <path>` works without it.

Leexi key: `LEEXI_KEY_ID` / `LEEXI_KEY_SECRET` in the environment the Codex session inherits
(a `.env` the project's `mise` loads, or `export …` in `~/.bashrc`).

## Per meeting

Say to Codex, in the repository: *"verwerk de Leexi-meeting van vandaag rond 14u"* or *"maak
van deze Leexi-call een to-do lijst met prompts: <url>"*. The agent then runs:

```sh
uv run --script .agents/skills/leexi/scripts/download-leexi --at "today 14:00"        # → .local/leexi/<uuid>/
uv run --script .agents/skills/video-frames-for-vision/scripts/select-frames .local/leexi/<uuid>/source.webm
```

(`--out` defaults: `.local/leexi/<uuid>/` and `…/source.frames/`; `.local/` must be git-ignored.)
Then it fills [annotate-prompt.md](annotate-prompt.md) and follows it: transcript first, frames in
batches of 12–24 with notes persisted to `screen-notes.md`, then `analysis.md`.

Measured (50-minute meeting, 137 frames from the exhaustive pass, `codex exec`, gpt-6-astra): 14 minutes,
3.0M input tokens of which 2.6M cache hits, 18k output. Defaults now keep ≈100 frames for such a
meeting; `--max-frames 120 --views-per-page 2` is the exhaustive pass.

Codex sandbox notes: work from the repository root so `.local/` is inside the writable workspace;
hidden/ignored directories are readable by path, but `rg --files` skips them, so open frames by the
exact paths from `manifest.md`. Headless (`codex exec`) attaches images only via repeated `-i` and
cannot loop over a manifest by itself; the interactive session with its image tool is the intended
mode, `codex exec` with the prompt on stdin also worked (the agent opens the images itself).

## What the reader gets

`analysis.md`: coverage, screen events with exact on-screen text, topics with decisions and
quotes, action items per owner, and one ready-to-paste prompt per action item for a new Codex
session. Prompts contain the meeting evidence (timestamps, frame ids), so they work outside the
run directory.
