# Native agy route (fallback)

Only when no Gemini API key/project is available. Verified `agy` 1.2.5–1.3.1, Gemini 3.8 Flash
High: a 42-minute 720p meeting took ~150 s (2026-09-18).

Not cheaper (2026-10-08): quota draws at API-price ratios plus ~12k agent-prompt tokens per call; on
Google AI Plus a 2-minute clip took ~4.9% of the weekly pool (`agy -p /usage --output-format json`)
versus $0.02–0.06 via `transcribe-gemini`. Antigravity terms allow training on interactions unless
opted out.

1. `agy models` checks native auth (separate from T3 login) and lists model IDs; never silently
   substitute a model or change billing. A listing does not prove quota is left.
2. Start `agy --model gemini-3.8-flash-high --effort high` in a folder holding only the video
   (it is an agent: given neighbouring transcripts it read those instead of watching, 2026-10-08).
3. Attach the **file**, not its path as text: copy the video file to the clipboard, Ctrl+V. Before
   submitting, confirm the indicator shows `video/mp4` and nonzero bytes (after submit it may say
   "image(s)" / 0 B). Headless: `osascript -e 'set the clipboard to (POSIX file "…")'`, `agy` in
   `tmux`, `tmux send-keys C-v`, confirm `Clipboard file URL read … video/mp4` in the newest
   `~/.gemini/antigravity-cli/log/cli-*.log`, then `tmux load-buffer` + `paste-buffer -p` the
   prompt. Sandboxed `osascript` can fail silently (empty `clipboard info`): run it unsandboxed.
   Headless stream-json takes text blocks only; do not invent video attachment JSON
   ([media-paste docs](https://antigravity.google/docs/cli/prompting/)).
4. Send the brief with an absolute `<name>.transcript.md` path and add what the API route does not
   need: "write the document to that path; return only the path and coverage gaps; perceive the media
   directly: no shell commands, frame extraction or other files". Approve that file write.
5. Read the file; check speech, visual changes, timestamps and coverage against the recording;
   report gaps; exit the CLI. A `media_summary_generation` 503 is harmless; a main-run 429 blocks.
   Spinning with no output file → read the session log (`~/.gemini/antigravity-cli/log/`) for
   quota/transport errors instead of sitting through backoff; logs diagnose, never content.
