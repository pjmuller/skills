# Fit readable video into native agy

Start with `shrink-video --preset normal --out /private/normal INPUT`.
Measure bytes; if needed, try compact then heavy in separate output directories.
Preserve 720p, compare address-bar text and listen to a short speech sample. Sparse
frames may miss brief tickets: extract exact original frames for those transitions.
Do not downscale further just to fit; opaque IDs need independently checked crops.

The presets use H.264 `slow`, mono 16 kHz AAC 32k. Normal is 0.5 fps / CRF24;
compact 0.5 fps / CRF28; heavy 0.25 fps / CRF26. The slow encoder saves substantial
space versus veryfast on screen recordings. For richer audio, preserve higher audio
quality and budget more bytes. No recipe guarantees a maximum size.

## Fallback: fewest practical chunks

Use a 48 MiB target, leaving headroom below native agy's 50 MiB hard limit.
From measured encoded bytes B and duration D, start with
`N = ceil(B / (48 * 1024 * 1024))` equal-duration chunks with ~10 seconds overlap.
For each chunk, seek in the original source, encode with the accepted recipe and
measure the actual result. Content varies: shorten only oversized chunks and
recheck; do not assume proportional bytes guarantee a fit. Combine adjacent chunks
when their re-encoded union fits. Avoid unnecessary tiny fragments.

Example encode (substitute measured START/LENGTH and the accepted fps/CRF):

```sh
ffmpeg -ss START -i source.mp4 -t LENGTH -vf fps=1/2 \
  -c:v libx264 -preset slow -crf 24 -pix_fmt yuv420p -movflags +faststart \
  -ac 1 -ar 16000 -c:a aac -b:a 32k part.mp4
```

Sparse output can hold the final still until the next frame boundary (up to one
frame interval beyond audio). Check audio duration separately; use the source
recording timeline, not that padded video tail, for transcript coverage.

Save a manifest of each file's start, end, bytes and audio/video properties. Require
complete coverage with no gaps. Supply absolute offsets and local context to Gemini;
write distinct drafts. Deduplicate overlap without dropping unfinished sentences.
Fathom's timestamp reference can help align speech, but crop times only locate visual
evidence; never use them as spoken-topic start times. Mark uncertain timings.
