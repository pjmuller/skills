# Fit readable video into native agy

Goal: fewest files under the 50 MiB `agy` limit with screen text readable. Preset fps/CRF/width live
in `scripts/shrink-video`; audio is mono 16 kHz AAC 32k (enough for meeting speech). No recipe
guarantees a size.

Try `normal`, then `compact`, then `heavy`, each in its own `--out` dir; measure bytes. Keep 720p,
compare address-bar text, listen to a speech sample. Don't downscale further just to fit: opaque IDs
need checked source crops anyway, and sparse frames miss brief screens (extract original frames for
those). Example: a 46-minute 720p meeting fit at normal 38.6 MiB, compact 29.3, heavy 24.4.

## Fallback: fewest practical chunks

Still over after `heavy`: `shrink-video --max-bytes 48M` adds overlapping stream-copy parts
`<name>.gemini.partNN.mp4` plus `<name>.chunks.md` (absolute start/end, bytes); sizing and keyframe
logic: `split_parts`.

Merging: one Gemini run per part with its absolute start offset and context, distinct drafts, then
stitch. Deduplicate the overlap without dropping unfinished sentences. Fathom timings help align
speech; crop times only locate visual evidence, never spoken-topic starts. Mark uncertain timings.

## Crop the Meet share tile

Gemini bills a fixed token count per frame, not per pixel
([media resolution](https://ai.google.dev/gemini-api/docs/media-resolution)), so cropping costs
nothing extra; it gives the shared screen the pixels (the tile is ~51% of a 720p Meet frame).
2026-10-12, one Leexi Meet call, 4-min web-app demo, 3.8 Flash, thinking medium, 3 runs per arm, 25
small-UI facts read from source frames:

| | low/medium (66/frame) | high (264/frame, default) |
| --- | --- | --- |
| no crop | 0.08 · $0.032 | 0.76 · $0.078 |
| crop | 0.43 · $0.040 | 0.88 · $0.081 |

Resolution is the big lever, the crop adds on top (input tokens identical per column; crop only
writes longer output). Uncropped low invented page names, 2023 dates and practitioners. Webcam faces
are not uploaded. Video tokens = seconds × 66 even at 0.5 fps: Gemini samples 1 fps. Tile box:
`share_box` (detect-screenshare); overlay graph: `video_filter` (shrink-video).

## Encoding resolution vs media resolution

Gemini 3 bills a fixed 280 tokens/frame at `high`, 70 at `low`/`medium`, audio 25/s
([media resolution](https://ai.google.dev/gemini-api/docs/media-resolution), checked 2026-11-02); the encoded
pixel size is not an input. 2026-11-02, 33 s of a CleanShot desktop demo (ClickUp chat, Google results) at 1 fps,
3.8 Flash, thinking medium, same prompt, 2 runs per arm, 19 visible facts held out from the source frames:

| encode | bytes | API resolution | input tokens | facts found | $ / run |
| --- | --- | --- | --- | --- | --- |
| 1920×1080 | 630 KB | high | 9,847 | 13, 13 | 0.020–0.022 |
| 1280×720 (presets) | 420 KB | high | 9,847 | 16, 13 | 0.021–0.023 |
| 854×480 | 297 KB | high | 9,847 | 16, 12 | 0.016–0.023 |
| 1280×720 | 420 KB | low | 3,313 | 6, 5 | 0.012–0.019 |

Run-to-run spread exceeds any resolution effect; `low` loses the message texts. All arms misread about half of
the ~9 px message times (8:59 → 9:19, 18:51 → 16:51) and two invented an app (1Password) or a Google Doc ID:
small text and IDs need source frames at any encode. Keep the 720p presets (smaller upload, same read).
