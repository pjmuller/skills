# Native agy route (fallback)

Use when no Gemini API key/project is available in the environment. Verified: `agy` 1.2.5–1.3.1,
Gemini 3.8 Flash High; a 42-minute 720p meeting took ~150 s (2026-09-18).

Cost (2026-10-08): agy quota draws at API-price ratios plus ~12k tokens of agent prompt per call;
on Google AI Plus a 2-minute clip took ~4.9% of the weekly Gemini pool (`agy -p /usage
--output-format json`); the same clip cost $0.02–0.06 via `transcribe-gemini`. The plan is roughly
API parity, not a subsidy. Antigravity terms allow training on interactions unless opted out.

1. `agy models` checks native auth (separate from T3 login) and lists model IDs; never silently
   substitute a model or change billing.
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
4. Send the brief with an absolute `<name>.transcript.md` path; require direct media perception
   (not logs or source code); approve that file write.
5. Read the file; check speech, visual changes, timestamps and coverage against the recording;
   report gaps; exit the CLI. A `media_summary_generation` 503 is harmless; a main-run 429 blocks.
