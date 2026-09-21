# Leexi URL → transcript or media

For speech-only work, use `download-leexi URL --out /private/run --transcript-only`.
Outputs: the unedited call object in `leexi-call.json`, `source.json` metadata, and
`transcript.md` with Leexi's summary, its follow-up tasks and `MM:SS Speaker: text`
paragraphs. No media, ffmpeg, Gemini or ASR is involved; stop here. Leexi's summary
and tasks are generated notes, not evidence; the transcript is Leexi ASR with speaker
attribution that can mislabel speakers and words. Keep provenance distinct.

For audiovisual work, drop `--transcript-only`: the helper streams the call's
presigned `recording_url` to `source.webm` (Google Meet bot recordings are 720p VP8,
60 fps, Opus). Inspect with ffprobe, then shrink as usual; low fps presets suit a talking
meeting with occasional screen share. `--resolve-only` saves metadata without transcript
or media. `recording_url` is `null` when the recording was archived or the company
disabled audio/video retention; then only the transcript route exists.

Load `LEEXI_KEY_ID` and `LEEXI_KEY_SECRET` from the operator's existing environment;
for a mise-managed project run `mise exec -- download-leexi ...`. PJ's key lives in
DentAI's mise environment (`~/.config/mise-env/dentai-org/dentai.env`), wrapped by
DentAI's `leexi-transcript` and `standup-dispatch` skills. `--out` must be git-ignored
when inside a repository; outside git use a private directory.

## API notes ([reference](https://docs.public-api.leexi.ai/reference/public-api), markdown: append `.md`)

- Base `https://public-api.leexi.ai/v1/`; HTTP Basic `base64(KEY_ID:KEY_SECRET)`, no HMAC.
  Keys: Settings → Company Settings → API Keys (admin). Each key has a call access scope
  (whole company, one user's access, or rules); an out-of-scope call answers **404**, and a
  fresh key with no scope lists zero calls. Python's default User-Agent gets 403: send any
  descriptive one. Limits: 50 requests/minute.
- `GET /calls`: `page`, `items` (≤100), `order` (`performed_at|updated_at asc|desc`),
  `from`/`to` (ISO, filter on `created_at` unless `date_filter=performed_at|updated_at`),
  `participating_user_uuid[]`, `owner_uuid[]`, `conversation_type_uuid`.
- `GET /calls/{uuid}` adds `transcript` (paragraphs with `speaker_index`, `start_time`,
  word `items`), `simple_transcript`, `call_ai_topics`. Also `summary`, `tasks` (Leexi
  follow-up tasks with `subject`, `owner`, `done`), `prompts` (custom completions per
  category), `chapters`, `speakers[].index/name`, `recording_url`, `transcript_url`,
  `leexi_url`, `conversation_type.slug`, `performed_at`, `duration` (seconds, string).
- Webhook `call.processed` posts the same call object once transcript and completions
  exist; also endpoints for users, teams, meeting events, call notes and call creation
  through a presigned upload.
