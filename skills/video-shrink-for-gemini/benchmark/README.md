# Screen-share benchmark

Measures `detect-screenshare` before a change ships: share-second precision/recall, boundary error,
missed shares, non-Meet fallback. One runner, any labelled set:

```bash
benchmark/make-clips /tmp/ss && benchmark/run /tmp/ss        # public synthetic set (also in pytest)
benchmark/run ~/.local/share/screenshare-benchmark/full      # private real recordings, if you have them
```

`DIR/labels.json`: `{"<name>": {"video": path (absolute or relative to DIR), "shares": [[start, end], …]
| "full", "layout": "note"}}`. A share = seconds Meet shows the presentation layout, presenter placeholder
tile included; `"full"` = not a Meet recording, expect `full-fallback`. Padding shows as −2/+2 s.

> [!IMPORTANT]
> Real calls contain faces, names, meeting codes and customer UI: they never enter this public repo.
> Keep them in a private, non-git directory (owner's machine: `~/.local/share/screenshare-benchmark/`
> with `full/` 17 tuning recordings, `heldout/` 5 recordings labelled after tuning, `clips/` 14 audio-free
> 35–80 s cuts). Labels hold only paths and seconds.

## Synthetic set (`make-clips`)

11 clips, 13 MB, generated in ~6 s: speaker view with a webcam or a camera-off avatar, 3/4-tile
galleries, spotlight, slides / dark editor / scrolling web app shares with 2–3 filmstrip tiles at both
gutter positions, a 12 s demo, two shares around 60 s of speaker view (same gutter), a non-Meet screen recording; 1 s and 50 s keyframe spacing. Its tiles
fall inside the real per-class signal ranges (webcam flat 0.33 vs real 0.23–0.39, screen 0.61–0.67 vs
0.55–0.78), so it guards the mechanics; only real recordings measure accuracy.

## Results 2026-10-27

| Set | Detector | Precision | Recall | Edges within 3 s |
| --- | --- | --- | --- | --- |
| tuning: 17 Meet recordings, 11.5 h | gutter rule (before) | 0.857 | 0.999 | |
| | layout + content votes | 0.995 | 0.995 | |
| held out: 5 recordings, 3.2 h, labelled before the run | gutter rule (before) | 0.962 | 1.000 | |
| | layout + content votes | 0.996 | 0.999 | |
| both, 98 share edges | before → after | | | 5 → 92 (median 15 → 2 s) |
| synthetic, 11 clips | layout + content votes | all 6 shares found, 0 s on the 5 no-share clips | | ±2 s |

<details><summary>Per layout (tuning + held out) and cost</summary>

| Layout | Calls | Before P / R | After P / R |
| --- | --- | --- | --- |
| Speaker view, 2 people + recorder tile (Fathom) | 6 | 0.69 / 1.00 (a no-share call: 29 of 30 min "shared") | 1.00 / 1.00 |
| 2×2 grid + recorder tile (Fathom) | 8 | 0.96 / 1.00 | 0.995 / 0.999 |
| Leexi galleries, 2–6 tiles incl. logo/avatar tiles | 8 | 0.91 / 1.00 | 0.994 / 0.994 |

CPU per hour of video: Fathom MP4 (1 s keyframes) ≈ 30 s, Leexi WebM (10 s keyframes, full decode)
≈ 55 s, shrunk `.gemini.mp4` (0.5 fps) ≈ 10 s; the shrunk files score P 0.993 / R 0.989. Private clip
set (14 cuts): P 0.97 / R 0.83, all of the loss in the isolated near-black terminal clip below.
</details>

## Known limits

- A share showing only near-black content from start to end (terminal at luma 20 vs Meet's 17) reads
  as empty background: missed. Inside a longer share it is bridged (up to 120 s while the gutter stays).
- A share that opens on a photo of people starts late (r6: +84 s) until slides or UI appear.
- Ranges with two gutter positions (participant count changed) crop to the wider box: a filmstrip
  sliver may stay in.
- Only Google Meet as recorded by Fathom/Leexi bots; Zoom/Teams/Loom/CleanShot → `full-fallback`.
