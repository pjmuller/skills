---
name: video-frames-for-vision
description: Turn a meeting or screen recording into the few frames a vision-only model needs (Codex, Claude Code, any model without video input), plus an annotation prompt that aligns them with a timestamped transcript into screen events, topics, action items and ready-to-paste prompts. Use when Gemini/Antigravity is unavailable, on Windows with Codex, or whenever a coding agent must know what was on screen during a call. Deterministic Python, no model downloads.
---

# Video frames for vision-only models

`select-frames VIDEO` (flags: `--help`; `uv run --script scripts/select-frames` on any OS) →
`<video>.frames/` with `manifest.md`/`.json`, `frames/`, `sheets/sheet-NN.jpg` and
`sheets/audit-NN.jpg`. Then fill [annotate-prompt.md](annotate-prompt.md) and let the agent read
the frames next to the transcript. This skill never listens: speech comes from a vendor
transcript ([leexi](../leexi/SKILL.md), Fathom) or ASR. Continuous audiovisual narrative with
Gemini instead: [video-shrink-for-gemini](../video-shrink-for-gemini/SKILL.md). Codex/WSL setup:
[codex-recipe.md](codex-recipe.md).

Exhaustive pass: `--max-frames 120 --views-per-page 2`. Tuning: `--no-crop --features`.

## What it does (and why)

Goal: few but relevant full-resolution frames, never losing a screen that mattered. Mechanism
and thresholds live in `scripts/select-frames` docstrings and `--help` defaults; design choices:

- **Lean to `screen`.** A people-only (`gallery`) false positive costs one frame, a false
  negative costs evidence; people-only stretches still get periodic sentinels on the audit sheets.
- **Crop the shared content** (largest bright rectangle beside webcam tiles) from the original
  video and upscale narrow crops, so address bars and ticket titles become legible.
- **Views → pages.** Near-identical samples form a view; views sharing the top chrome band form a
  page; a page that returns later is a new page. Over the cap, scroll views, then near-duplicate
  pages, then the shortest are demoted, so a brief but novel screen survives.
- **Coverage rule.** Page identity from cheap features is fuzzy (scrolled vs different page
  overlap on every metric tried), so any screen-share stretch longer than `--max-gap` gets a
  frame; continuous scrolling costs about one frame per 20 s, not one per second.
- One sequential ffmpeg decode; full-res extraction reuses the exact sampled pts. Encoders drop
  frames on static screens, so time gaps mean "unchanged", not "missing".

Measured on a 50-minute Google Meet standup (720p, 41 min shared): ≈40 s runtime, defaults keep
≈100 frames; people-only 8:41 matched a Gemini pass; 6 of 7 reference screen events hit a kept
frame (the exhaustive pass, 133 frames, hit all 7).

## Limits, stated in every output

Frames prove what was on screen at that second, not what happened between samples; 1 fps misses
sub-second flashes. Tuned on Google Meet bot recordings with side tiles; other layouts fall back
to whole-frame comparison (`--no-crop` forces it). A full-screen photo slideshow can be
misclassified as people-only: check the audit sheets.

Claude Code (one Opus agent, Read tool) stopped returning images after 54 frames ("media removed:
request limit"): on Claude, split batches over sub-agents, notes on disk. Codex read all 137
frames in one session ([measured](codex-recipe.md#per-meeting)).

## Files

- `scripts/select-frames`: the selector (PEP 723; opencv-headless, numpy, imagehash, pillow).
- `scripts/make-fixture` + `test_select_frames.py`: synthetic video and classification/grouping test.
- [annotate-prompt.md](annotate-prompt.md): model prompt and `analysis.md` contract.
- [codex-recipe.md](codex-recipe.md): install + per-meeting steps for Codex, token budget, CLI gotchas.
- `scripts/install` / `--check`: links `select-frames`; needs `ffmpeg`, `ffprobe`, `uv`.
