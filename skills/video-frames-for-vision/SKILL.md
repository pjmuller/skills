---
name: video-frames-for-vision
description: Turn a meeting or screen recording into the few frames a vision-only model needs (Codex, Claude Code, any model without video input), plus an annotation prompt that aligns them with a timestamped transcript into screen events, topics, action items and ready-to-paste prompts. Use when Gemini/Antigravity is unavailable, on Windows with Codex, or whenever a coding agent must know what was on screen during a call. Deterministic Python, no model downloads.
---

# Video frames for vision-only models

`select-frames VIDEO [--out DIR]` → `DIR/manifest.md` + `frames/` + `sheets/`. Then fill
[annotate-prompt.md](annotate-prompt.md) and let the agent read the frames next to the
transcript. Speech comes from a vendor transcript (sibling skill `leexi`, or Fathom via
`video-shrink-for-gemini`); this skill never listens.

```sh
uv run --script scripts/select-frames recording.webm          # any OS; or `select-frames` after scripts/install
select-frames --max-frames 60 --views-per-page 2 recording.webm  # cheaper pass
select-frames --no-crop --features recording.webm                # whole frames, dump features for tuning
```

## What it does (and why)

1. Samples at 1 fps into 320×180 thumbnails with one sequential ffmpeg decode (50 min ≈ 25 s). A
   `select` filter keeps the first source frame at or after each second and `showinfo` reports its
   real pts, so the full-resolution extraction (`-ss` at that pts) is the very same frame. Encoders
   drop frames on static screens, so time gaps between samples mean "unchanged", not "missing".
2. **People-only detection.** A frame is `gallery` when there is no large bright content region
   and the frame is mostly skin tones on a flat client background, or when the largest region is
   itself a face. Everything else is `screen`. False positives cost a frame; false negatives cost
   evidence, so the rule leans to `screen`, and every people-only stretch gets a sentinel every 20 s
   on an audit sheet the model scans.
3. **Content region.** Meeting clients draw shared content as one large rectangle next to small
   webcam tiles; the widest run of non-background columns/rows isolates it. Kept frames are that
   crop from the original video, upscaled 2× when narrower than 1400 px (a 1280×720 Meet recording
   yields a 1856×1080 crop in which address bars and ticket titles are legible).
4. **Views.** Consecutive screen samples with pHash distance ≤ 6 and SSIM ≥ 0.90 (on the crop) are
   one view. Views shorter than `--min-seconds` (3) are transient: audit sheet only.
5. **Pages.** Consecutive views whose top 30 % band (browser chrome + page header) matches
   (SSIM ≥ 0.85, pHash ≤ 20) are one page; glitches up to `--gap` (3 s) do not split a page; a page
   that returns later is a new page. Each page yields its longest settled view plus up to
   `--views-per-page − 1` other scroll positions, longest first. Over `--max-frames` (120), extra
   scroll views are demoted first, then the shortest pages. Page identity from cheap features is
   fuzzy (same page scrolled vs a different page overlap on every metric tried), so a **coverage
   rule** adds one frame whenever a screen-share stretch exceeds `--max-gap` (20 s) without one;
   continuous scrolling therefore costs about one frame per 20 s, not one per second.
6. Output: `frames/<page><view>-h-mm-ss.jpg`, `manifest.md` (table: id, second shown, view span,
   page span, file) and `manifest.json` (same plus pages, transients, demoted, gallery spans),
   `sheets/sheet-NN.jpg` (kept frames, 4×3 with labels) and `sheets/audit-NN.jpg`.

Measured on a 50-minute Google Meet standup (720p, 41 min of screen share): 136 pages, 133 frames
(120 page + 13 coverage), people-only 8:41 matching a Gemini pass over the same recording; seven
reference screen events (Dentex site, ClickUp list and task, Gmail, demo site, pricing page, PWA)
all mapped to a kept frame. Runtime ≈ 40 s on an M-series Mac.

## Limits, stated in every output

Sampled frames prove what was on screen at that second, not what happened between samples;
1 fps misses sub-second flashes. Heuristics are tuned on Google Meet bot recordings with a
side-tile layout; other layouts fall back to whole-frame comparison (`--no-crop` forces it).
Faces inside shared content (photos, testimonials) are handled by the content-region rule, but a
full-screen photo slideshow can be misclassified as people-only: check the audit sheets.

Same recording through Codex (`codex exec`, gpt-6-astra): all 137 frames read in 14 min, 3.0M input
tokens (2.6M cached), a complete analysis with exact on-screen text. Through one Claude Code agent
(Opus, Read tool): the harness stopped returning images after 54 frames ("media removed: request
limit"), so on Claude split the batches over several sub-agents, one batch each, notes on disk.

## Files

- `scripts/select-frames` — the selector (PEP 723; opencv-headless, numpy, imagehash, pillow).
- `scripts/make-fixture` — synthetic test video (people tiles, a page, the same page scrolled,
  a second page); `test_select_frames.py` asserts the classification and grouping.
- [annotate-prompt.md](annotate-prompt.md) — the model prompt and `analysis.md` contract.
- [codex-recipe.md](codex-recipe.md) — install once + per-meeting steps for Codex (Linux/WSL/macOS),
  token budget, sandbox notes; why video/audio attachments do not work in Codex.
- `scripts/install` / `--check` — links `select-frames`; needs `ffmpeg`, `ffprobe`, `uv`.
