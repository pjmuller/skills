# Read-only session review

`sessions --since 21d|2026-09-01 [--limit N] --json`, `read ID --json` and
`export --since 7d --dir DIR` (Markdown per session + `index.json`). Row/turn fields:
`session_rows` and `review_turns` in `scripts/claude-cloud`.

- `--since` filters by creation date across all pages; the API lists by activity, not creation.
- Transcripts omit thinking and lifecycle events; failed tools keep a 300-character error excerpt.
- Export is a snapshot cache: files already indexed are not refetched (delete one to refresh), an
  interrupted run resumes, and the index keeps older windows.
- Privacy: export files are 0600 and redacted with the narrow `(sk-|token|Bearer )\S+` pattern,
  which is not a secret scanner; raw `read --json` is unredacted. Delete the export directory when done.
