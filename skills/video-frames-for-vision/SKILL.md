---
name: video-frames-for-vision
description: "Use when a model without video input (Codex, Claude Code) must know what was on screen during a recording: Gemini is unavailable, on Windows with Codex, or opaque on-screen IDs must be checked against source frames. Picks the few frames that matter plus an annotation prompt."
---

# Video frames for vision-only models

`select-frames VIDEO` (`--help`; `uv run --script scripts/select-frames` on any OS) →
`<video>.frames/` with `manifest.md`/`.json`, `frames/`, `sheets/sheet-NN.jpg`,
`sheets/audit-NN.jpg`. Then fill [annotate-prompt.md](annotate-prompt.md) and let the agent read
the frames next to the transcript. This skill never listens: speech comes from a vendor transcript
([leexi](../leexi/SKILL.md), Fathom) or ASR. Continuous audiovisual narrative with Gemini instead:
[video-shrink-for-gemini](../video-shrink-for-gemini/SKILL.md). Codex/WSL install and per-meeting
steps: [codex-recipe.md](codex-recipe.md). `scripts/install` links the command (`--check`: ffmpeg,
ffprobe, uv).

Exhaustive pass: `--max-frames 120 --views-per-page 2`. Tuning: `--no-crop --features`.

## Design intent (mechanism and thresholds: `scripts/select-frames` docstrings)

Few full-resolution frames, never losing a screen that mattered:

- **Lean to `screen`**: a people-only false positive costs one frame, a false negative costs
  evidence; people-only stretches still get sentinels on the audit sheets.
- **Crop the shared content** from the original video and upscale narrow crops so address bars
  and ticket titles become legible.
- **Pages over views**, and over the cap demote scroll views, then near-duplicate pages, then the
  shortest, so a brief but novel screen survives.
- **Coverage rule**: page identity from cheap features is fuzzy, so any share stretch longer than
  `--max-gap` gets a frame (continuous scrolling ≈ one frame per 20 s).
- Encoders drop frames on static screens: time gaps mean "unchanged", not "missing".

Measured, 50-minute Meet standup (720p, 41 min shared): ≈40 s, ≈100 frames by default; 6 of 7
reference screen events hit a kept frame (exhaustive pass, 133 frames: all 7).

## Limits, stated in every output

Frames prove what was on screen at that second, not what happened between samples; 1 fps misses
sub-second flashes. Tuned on Google Meet bot recordings with side tiles; other layouts fall back to
whole-frame comparison. A full-screen photo slideshow can be misclassified as people-only: check
the audit sheets.

Claude Code (one Opus agent, Read tool) stopped returning images after 54 frames ("media removed:
request limit"): on Claude, split batches over sub-agents with notes on disk. Codex read all 137
frames in one session ([measured](codex-recipe.md#per-meeting)).
