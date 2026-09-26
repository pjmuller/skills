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

Target 48 MiB (headroom). Start with `N = ceil(bytes / 48 MiB)` equal-duration chunks, ~10 s
overlap, each seeked from the **original** and encoded with the accepted recipe (same ffmpeg
arguments as `shrink-video`, plus `-ss START -t LENGTH`). Measure each: shorten only oversized
chunks, merge neighbours whose union fits, avoid tiny fragments; not arbitrary ten-minute chunks.

Sparse output holds the last still up to one frame interval past the audio: use the source
timeline for coverage, not the padded video tail.

Save a manifest (start, end, bytes, audio/video properties per file) and require gap-free
coverage. Give Gemini absolute offsets and context; write distinct drafts; deduplicate overlap
without dropping unfinished sentences. Fathom timings help align speech, but crop times only
locate visual evidence, never spoken-topic starts. Mark uncertain timings.
