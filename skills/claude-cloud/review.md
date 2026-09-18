# Read-only session review

- `sessions --since 21d --limit 50 --json`: API activity order (all pages filtered by creation date); date cutoffs also accept `2026-09-01`.
- `read ID --json`: ordered user/assistant turns with text, timestamp and tool summaries; failed tools retain a 300-character error excerpt. Thinking and lifecycle events are omitted.
- `export --since 7d --dir /tmp/cloud-review --profile work`: Markdown per session plus `index.json`; indexed Markdown skips event requests; interrupted exports resume. Delete the export directory when finished.

Session JSON includes ID/URL, creation/activity dates, origin, repository, outcome branches, title/status, user-message count, model, cost, token counters, task summary and Claude Code version. Missing account metadata stays null.
The export index adds turn/error counts and the first prompt (300 characters). Files are private (0600); the index retains older exports. Exports redact `(sk-|token|Bearer )\S+`; this narrow pattern is not a general secret scanner. Raw `read --json` is unredacted. Existing files retain their original snapshot; remove one to refresh it.
