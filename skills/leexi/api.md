# Leexi public API notes

[Reference](https://docs.public-api.leexi.ai/reference/public-api) (append `.md` for markdown).

- Base `https://public-api.leexi.ai/v1/`; HTTP Basic `base64(KEY_ID:KEY_SECRET)`, no HMAC.
  Keys: Settings → Company Settings → API Keys (admin).
- **Scope gotcha:** each key has a call access scope (whole company, one user's access, or
  rules). An out-of-scope call answers **404**; a fresh key with no scope lists zero calls.
- Python's default User-Agent gets **403**: send any descriptive one. Limit 50 requests/minute.
- `GET /calls`: `page`, `items` (≤100), `order` (`performed_at|updated_at asc|desc`),
  `from`/`to` (ISO with offset; filter on `created_at` unless `date_filter=performed_at|updated_at`),
  `participating_user_uuid[]`, `owner_uuid[]`, `conversation_type_uuid`. Response:
  `data[]` plus `pagination.page/items/count/pages`. List items already carry the full call
  object incl. `duration` (seconds, number or string).
- `GET /calls/{uuid}` adds `transcript` (paragraphs with `speaker_index`, `start_time`,
  word `items`), `simple_transcript`, `call_ai_topics`. Also `summary`, `tasks` (follow-up
  tasks with `subject`, `owner`, `done`), `prompts`, `chapters`, `speakers[].index/name`,
  `recording_url`, `transcript_url`, `leexi_url`, `conversation_type.slug`, `performed_at` (UTC).
- `recording_url` is a presigned URL (Google Meet bot: 720p VP8, 60 fps, Opus webm); `null`
  when the recording was archived (`video_archived_at`/`audio_archived_at`) or retention is off.
- Webhook `call.processed` posts the same call object once transcript and completions exist;
  also endpoints for users, teams, meeting events, call notes and call upload via presigned URL.
