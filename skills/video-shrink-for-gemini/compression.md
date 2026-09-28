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
