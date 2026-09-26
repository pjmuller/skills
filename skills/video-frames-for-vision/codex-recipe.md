# Run it in Codex (Linux / WSL / macOS), no Gemini

Codex CLI reads images, not video or audio (0.156.1/0.157.0: an attached MP4/WAV returns
"couldn't be processed" with exit 0; [why](../video-shrink-for-gemini/local-route.md#why-local-asr-is-mandatory-on-a-subscription)).
So: transcript from the vendor, frames from `select-frames`, Codex reads the frames as images.

## Install once

Everything lives where Codex runs; on Windows that is the WSL distribution, not PowerShell.
Needs `ffmpeg`/`ffprobe` (`apt install ffmpeg` / `brew install ffmpeg`) and
[uv](https://docs.astral.sh/uv/). Register the skills in the working repository
(`pnpm dlx skills add pjmuller/skills -s leexi -s video-frames-for-vision -y`) or use its
committed copy. `scripts/install` links commands into `~/.local/bin` (optional; `uv run --script
<path>` works without it). Leexi credentials must be in the environment Codex inherits
([leexi](../leexi/SKILL.md)).

## Per meeting

Say to Codex, in the repository: *"verwerk de Leexi-meeting van vandaag rond 14u"* or *"maak
van deze Leexi-call een to-do lijst met prompts: <url>"*. The agent runs:

```sh
uv run --script .agents/skills/leexi/scripts/download-leexi --at "today 14:00"        # → .local/leexi/<uuid>/
uv run --script .agents/skills/video-frames-for-vision/scripts/select-frames .local/leexi/<uuid>/source.webm
```

(`.local/` must be git-ignored; frames land in `…/source.frames/`.) Then it fills
[annotate-prompt.md](annotate-prompt.md) and follows it.

Measured (50-minute meeting, 137 frames from the exhaustive pass, `codex exec`, gpt-6-astra):
14 min, 3.0M input tokens (2.6M cached), 18k output. Defaults keep ≈100 frames for such a meeting.

## Codex CLI gotchas

- Work from the repository root so `.local/` is writable. Ignored directories are readable by
  path but `rg --files` skips them: open frames by the exact `manifest.md` paths.
- Interactive session with its image tool is the intended mode; `codex exec` with the prompt on
  stdin also works (the agent opens images itself). Headless `-i` attachments cannot loop over a
  manifest.
- `-i` is variadic: put the prompt **before** it. Close stdin (`</dev/null`) in non-interactive
  shells or `codex exec` blocks. One 1280×720 frame round trip ≈ 12–34k tokens incl. overhead.

## What the reader gets

`analysis.md` per the [annotate-prompt.md](annotate-prompt.md) contract; its per-action prompts
carry the meeting evidence, so they work outside the run directory.
