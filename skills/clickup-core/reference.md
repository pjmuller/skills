Undocumented ClickUp shapes the CLI depends on. Code in [scripts/clickup.py](scripts/clickup.py);
fixture tests in `scripts/test_clickup.py` + `scripts/fixtures/`.

## Rich-content contract

Public task fields (`description`, `text_content`, `markdown_description`) are lossy: rebuilding
from them destroys unknown native embeds, and v3 has no full rich-description update. The only
proven lossless seam is the private v1 `GET /api/v1/task/<id>?fields[]=content` (JSON Quill delta),
written back via v2 `PUT /task/<id>` `content`. `append_ops_to_content` keeps every existing op and
only appends; missing/malformed content fails closed.

Verification (`verify_task_content` → `content_signature`) compares ordered plain-text runs plus every embed/formatted
op, coalescing adjacent unformatted strings (ClickUp merges them). A raw op-prefix check is too
strict; globally concatenated text misses movement around an embed; Markdown readback alone
proves nothing. v1 is private and unstable: keep the fixtures covering unknown embeds and keep API
readback around live writes. `attach --embed` player/file-chip ops (`embed_ops`) copy what the UI
stores; `verify_embed` proves they landed.

## Native mentions

- Description (Quill embed): `{"insert":{"user_mention":{"id":101,"name":"Alex Example"}}}`,
  `{"insert":{"task_mention":{"task_id":"abc123"}}}`.
- Comment part: `{"type":"tag","user":{"id":101}}`,
  `{"type":"task_mention","text":"<resolved title>","task_mention":{"task_id":"abc123","team_id":"…"}}`.

Attachment links: `[[file:NAME]]` (beside `[[task-id]]`) is a pre-pass (`link_attachments`) to
`[NAME](<attachment url>)` from the target task's one GET; exact title, else unique
case-insensitive; duplicates → newest `date`. Bare filename titles outside code/links/URLs get the
same rewrite (stderr `linked attachment:`). `create` has no attachments yet, so it fails closed.

Task mentions resolve title and workspace before posting; the created comment is re-read by id.
`comment_text`, a plain `@Name` or a plain URL is not a native mention. No native Doc-chip write
is proven (a Markdown link to a Doc works). Threads: `/comment/{root_id}/reply`, always the root
(`?comment=`), never a `threadedComment` id.

## Comment formatting

One parser (`_md_blocks` + `_inline_events`); `md_to_delta` and `comment_parts` are thin emitters
sharing Quill attributes. `comment_text` is plain text (Markdown shows literally). A Markdown table
becomes a `table-embed` part in the shape the UI writes (opaque row/column ids, `cells` keyed
`"r:c"`). Dividers/images have no comment part: they degrade to a rule line / plain link.

## Normalization and limits

Description list/blockquote/code-block attributes are nested objects; comment attributes stay flat.
Before extending the parser to a new embed, write it in the UI and read it back through the API.

## Chat

The public v3 chat API posts Markdown only, and its image syntax is broken: `![](url)` is stored as an
image part with `src="http://null/"`, whatever the URL (checked 2026-10-05). Chat views are not
reachable through v2 `/view/{id}/comment` either (DMs answer `can_use_public_api_dev_key`). Inline
images therefore replay what the web app does, private and unstable like the v1 content seam:

1. `POST https://id.app.clickup.com/data/v3/workspaces/{ws}/authentication/access_tokens` with the
   `cu_refresh` cookie + `Origin`/`X-CSRF` headers → workspace-scoped bearer (48 h). `cu_refresh` lives
   one year and is not rotated, so `chat session` reads it once from a Chrome profile (headless Chrome
   decrypts a copy of the jar, no keychain prompt) and caches it in `~/.cache/clickup-core/`. The
   personal token cannot do any of this.
2. `POST {frontdoor}/v1/attachment` multipart `attachment`, `parent=<channel id>`, `type=8` → attachment
   JSON (`id`, `url`, thumbnails, width/height). The frontdoor host is region-bound
   (`CHAT_FRONTDOOR`, override `[chat].frontdoor`).
3. `POST {frontdoor}/comment-service/v3/workspaces/{ws}/comments/view/{channel}` (channel message,
   `type` 8) or `…/comments/comment/{root}` (thread reply, `parent=root`, `type` 2) with `comment`
   parts: `comment_parts(text)` + `chat_image_part(att)` per image, plus `attachment_ids`.

Readback is public v3 (`![name](url)` per image); a count mismatch fails the command. Thread URLs
carry the message you opened the pane from, which may be a reply: `chat_root_of` walks the last 100
roots and their replies.

## SyncUp recordings

[scripts/syncup.py](scripts/syncup.py) chain: root chat message (`A SyncUp Happened`) → reply from
the ClickUp AI bot (`user_id` `-4`) linking the notes Doc → v3 `docs/{id}/pages?content_format=text/md`
→ bare `*.clickup-attachments.com` media link on the notes page.

- Notes and recording appear 5–10 min after the call (exit 75 until then).
- Calls over ~1 h get audio-only (1 GB cap), so any media extension counts.
- "Meeting Transcript" is the live notetaker's: untimed, possibly cut off mid-call.
- The web player's timed captions come from a private AI-service endpoint that rejects personal
  tokens: unsupported. For a timed transcript use video-shrink-for-gemini's `transcribe-local` or
  Gemini on the recording. Follow-up prompts from a call: the `recording-followups` skill in pjmuller/skills.

Official: [tasks](https://developer.clickup.com/docs/tasks),
[comment formatting](https://developer.clickup.com/docs/comment-formatting),
[rate limits](https://developer.clickup.com/docs/rate-limits).
