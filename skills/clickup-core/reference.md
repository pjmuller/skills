Undocumented ClickUp shapes the CLI depends on. Code: [scripts/clickup.py](scripts/clickup.py);
fixture tests: `scripts/test_clickup.py` + `scripts/fixtures/`.

## Rich-content contract

Public task fields (`description`, `text_content`, `markdown_description`) are lossy: rebuilding
from them destroys unknown native embeds, and v3 has no full rich-description update. The only
proven lossless seam: private v1 `GET /api/v1/task/<id>?fields[]=content` (JSON Quill delta),
written back via v2 `PUT /task/<id>` `content`. `append_ops_to_content` keeps every existing op and
only appends; missing/malformed content fails closed.

Verification (`verify_task_content` → `content_signature`) compares ordered plain-text runs plus
every embed/formatted op, coalescing adjacent unformatted strings (ClickUp merges them). A raw
op-prefix check is too strict; concatenated text misses movement around an embed; Markdown
readback proves nothing. v1 is private and unstable: keep the unknown-embed fixtures and API
readback around live writes. `attach --embed` player/file-chip ops (`embed_ops`) copy what the UI
stores; `verify_embed` proves they landed.

## Native mentions

- Description (Quill embed): `{"insert":{"user_mention":{"id":101,"name":"Alex Example"}}}`,
  `{"insert":{"task_mention":{"task_id":"abc123"}}}`.
- Comment part: `{"type":"tag","user":{"id":101}}`,
  `{"type":"task_mention","text":"<resolved title>","task_mention":{"task_id":"abc123","team_id":"…"}}`.

`[[file:NAME]]` is a pre-pass (`link_attachments`) to `[NAME](<attachment url>)` from the target
task's one GET: exact title, else unique case-insensitive; duplicates → newest `date`. Bare
filename titles outside code/links/URLs get the same rewrite (stderr `linked attachment:`).
`create` has no attachments yet, so it fails closed.

Task mentions resolve title and workspace before posting; the created comment is re-read by id.
`comment_text`, a plain `@Name` or a plain URL is not a native mention. No native Doc-chip write
is proven (a Markdown link to a Doc works). Thread replies: `/comment/{root_id}/reply`, always the
root (`?comment=`), never a `threadedComment` id.

## Comment formatting

One parser (`_md_blocks` + `_inline_events`); `md_to_delta` and `comment_parts` are thin emitters
sharing Quill attributes. `comment_text` is plain text (Markdown shows literally). A Markdown table
becomes a `table-embed` part in the UI's shape (opaque row/column ids, `cells` keyed `"r:c"`).
Column `width` is fixed px (no auto-fit): `_column_widths` sizes columns to their longest cell,
short columns first, within ~840 px (body) / 480 px (comment panel). Cells carry paragraph inline
markdown; an images-only cell holds `{"insert": {"image": url}}` ops shown at column width
(verified in a description by readback + DOM, 2026-10-23; comments unverified). Dividers/images
have no comment part: they degrade to a rule line / plain link.

Description list/blockquote/code-block attributes are nested objects; comment attributes stay flat.
Before parsing a new embed, write it in the UI and read it back through the API.

Description Markdown that ClickUp rewrites on save (2026-10):

- A `**bold**` or `` `code` `` span whose markers sit on different source lines comes back escaped
  (`\*\*…`): keep each span on one physical line. Bold around a whole paragraph with nested italic
  breaks too; use a short bold lead-in.
- A link before inline code (not only before a code block) is mangled into a broken autolink:
  put bare URLs after the prose.

## Workspace admin limits

Probed against live lists, 2026-09/10:

- **List statuses are add-only by API.** `POST /v2/list/<id>/status` with a nested body
  `{"status": {"name": …, "type": "custom", "color": …}}` (flat shapes return `STATUS_026 "Status
  name is required"`). It lands just before the closed status (`orderindex` ignored; only a UI drag
  reorders) and converts an inherited space group into a list-level copy. No delete or rename (a
  POST with an existing id creates a second status). The one undo, all-or-nothing:
  `PUT /v2/list/<id>` `{"override_statuses": false}` reverts the list to the space set. Then fix
  `clickup.toml` statuses (`topology` → `matches_skill_constants`).
- **Dropdown options are UI-only**: no API edits a custom field's options (create/delete only, and
  delete drops every task's value). A person adds the option; read its id back with `fields`.
- **No auto-number field** (`auto_number`/`unique_id` → `FIELD_422`). The task id is already unique;
  sequential ids need the Custom Task IDs ClickApp (paid plans, per Space, UI only, renumbers the
  Space).
- **Date-only fields**: compute epoch ms in the operator's ClickUp timezone (`GET /user`), not UTC;
  ClickUp normalises the stored time ([docs](https://developer.clickup.com/docs/customfields#date):
  04:00 local), so compare the local day on readback, never the timestamp.

## Chat

The public v3 chat API posts Markdown only, and stores `![](url)` as an image with
`src="http://null/"` whatever the URL (2026-10-05). v2 `/view/{id}/comment` can't reach chat views
(DMs answer `can_use_public_api_dev_key`). Inline images therefore replay the web app, private and
unstable like the v1 seam:

1. `POST https://id.app.clickup.com/data/v3/workspaces/{ws}/authentication/access_tokens` with the
   `cu_refresh` cookie + `Origin`/`X-CSRF` headers → workspace bearer (48 h). `cu_refresh` lives a
   year, unrotated: `chat session` reads it once from a Chrome profile (headless Chrome decrypts a
   copy of the jar, no keychain prompt) and caches it in `~/.cache/clickup-core/`. The personal
   token can do none of this.
2. `POST {frontdoor}/v1/attachment` multipart `attachment`, `parent=<channel id>`, `type=8` →
   attachment JSON. The frontdoor host is region-bound (`CHAT_FRONTDOOR`, override `[chat].frontdoor`).
3. `POST {frontdoor}/comment-service/v3/workspaces/{ws}/comments/view/{channel}` (message, `type` 8)
   or `…/comments/comment/{root}` (thread reply, `parent=root`, `type` 2): `comment_parts(text)` +
   `chat_image_part(att)` per image, plus `attachment_ids`.

Readback is public v3 (`![name](url)` per image); a count mismatch fails the command. A thread URL
carries the message the pane was opened from, possibly a reply: `chat_root_of` walks the last 100
roots and their replies.

## SyncUp recordings

[scripts/syncup.py](scripts/syncup.py): root chat message (`A SyncUp Happened`) → ClickUp AI bot
reply (`user_id` `-4`) linking the notes Doc → v3 `docs/{id}/pages?content_format=text/md` → bare
`*.clickup-attachments.com` media link on the notes page.

- Notes and recording appear 5–10 min after the call (exit 75 until then).
- Calls over ~1 h get audio only (1 GB cap), so any media extension counts.
- "Meeting Transcript" is the live notetaker's: untimed, possibly cut off mid-call.
- The player's timed captions come from a private endpoint that rejects personal tokens. Timed
  transcript: video-shrink-for-gemini `transcribe-local`, or Gemini on the recording. Follow-up
  prompts from a call: skill `recording-followups`.

Official: [tasks](https://developer.clickup.com/docs/tasks),
[comment formatting](https://developer.clickup.com/docs/comment-formatting),
[rate limits](https://developer.clickup.com/docs/rate-limits).
