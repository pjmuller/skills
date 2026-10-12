# Fit readable video into native agy

Goal: fewest files under the 50 MiB `agy` limit with screen text still readable. Preset
fps/CRF/width live in `scripts/shrink-video`; audio is mono 16 kHz AAC 32k (enough for meeting
speech; budget more bytes if audio quality matters). `slow` saves substantial space over
`veryfast` on screen recordings. No recipe guarantees a size.

Try `normal`, then `compact`, then `heavy`, each in its own `--out` dir; measure bytes. Keep
720p, compare address-bar text, listen to a speech sample. Do not downscale further just to fit:
opaque IDs need independently checked crops anyway, and sparse frames can miss brief screens
(extract exact original frames for those). Example: a 46-minute 720p meeting fit in one file at
normal 38.6 MiB, compact 29.3, heavy 24.4.

## Fallback: fewest practical chunks

Still over after `heavy`: `shrink-video --max-bytes 48M` (headroom under 50 MiB) keeps
`<name>.gemini.mp4` and adds balanced, overlapping `<name>.gemini.partNN.mp4` stream-copy parts
plus `<name>.chunks.md` (absolute start/end, bytes). Sizing, overlap and keyframe logic:
`split_parts` in `scripts/shrink-video`.

Merging: one Gemini run per part; give each its absolute start offset and context, write
distinct drafts, then stitch. Deduplicate the overlap without dropping unfinished sentences.
Fathom timings help align speech, but crop times only locate visual evidence, never spoken-topic
starts. Mark uncertain timings.

## Crop the Meet share tile

Gemini bills a fixed token count per frame, not per pixel ([media resolution](https://ai.google.dev/gemini-api/docs/media-resolution):
Gemini 3 video 70/frame default, 280 high), so cropping saves nothing; it gives the shared screen the
pixels (the tile is ~51% of a 720p Meet frame). 2026-10-12, one Leexi Meet call, 4-min web-app demo clip
(booking form, calendar dashboard, mobile agenda), 3.8 Flash, thinking medium, same prompt, 3 runs per
arm, 25 small-UI facts read from source frames:

| | default (66/frame) | `--media-resolution high` (264/frame) |
| --- | --- | --- |
| no crop | 0.08 (2/25 every run) · $0.032 | 0.76 · $0.078 |
| crop | 0.43 · $0.040 | 0.88 · $0.081 |

Input tokens identical per column (22,791 / 71,103); crop costs only longer output. Uncropped default
invented page names, 2023 dates and practitioners. Bonus: webcam faces are not uploaded. Video tokens =
seconds × 66 although the file has 0.5 fps: Gemini samples 1 fps, duplicating frames. Tile box:
`share_box` (detect-screenshare), overlay graph: `video_filter` (shrink-video).
