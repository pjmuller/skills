## Rich-content contract

ClickUp's public task API documents Markdown writes and exposes `description`, `text_content`
and optional `markdown_description`; these are lossy projections. In particular, rebuilding a
description from Markdown destroys unknown native embeds. The public v3 task surface has no
equivalent full rich-description update.

The proven preservation seam is:

1. Read `GET https://api.clickup.com/api/v1/task/<id>?fields[]=content` with the personal token.
   This internal endpoint returns the exact JSON-encoded Quill delta.
2. Parse `{"ops":[...]}`; fail closed if absent or malformed.
3. Keep every existing op unchanged. Append only required newline ops plus the new
   `md_to_delta()` ops.
4. Write the complete `content` string with v2 `PUT /task/<id>`.
5. Read back v1 content and v2 Markdown. Compare ordered plain-text runs plus every
   embed/formatted op; coalesce only adjacent unformatted strings because ClickUp may merge them.
   A raw op-prefix check is too strict, while globally concatenated text misses movement around an
   embed. Markdown alone cannot prove preservation.

The v1 endpoint and `content` schema are private, unstable ClickUp interfaces. Keep fixture tests
covering unknown embeds and retain API readback around live writes.

## Native mentions

Descriptions use Quill embeds:

- User: `{"insert":{"user_mention":{"id":101,"name":"Alex Example"}}}`
- Task: `{"insert":{"task_mention":{"task_id":"abc123"}}}`

The CLIs accept known `@alias` values, `[@Name](#user_mention#ID)`, `[[task-id]]`, bare ClickUp
task URLs and Markdown links targeting a ClickUp task. The task forms become native task chips.

Comments use ClickUp's structured `comment` array:

- User: `{"type":"tag","user":{"id":101}}`
- Task: `{"type":"task_mention","text":"Resolved task title","task_mention":{"task_id":"abc123","team_id":"…"}}`

Resolve task title and validate workspace before posting; then verify the created comment by its
returned id and confirm every expected structured part. `comment_text`, a plain `@Name`, and a
plain URL are not evidence of a native mention. Public Markdown can link to a ClickUp Doc, but no
native Doc-chip write was proven.

Threads: POST/GET `/comment/{root_id}/reply`; replies always target the thread root (URL `comment=`),
never a `threadedComment` reply id.

## Comment formatting

Descriptions and comments share ONE markdown parser (`_md_blocks` + `_inline_events`); `md_to_delta`
and `comment_parts` are thin emitters. Comment parts take the same Quill attributes as descriptions:
bold, italic, strike, code, link, header, list (bullet|ordered|checked|unchecked) + indent,
blockquote, code-block. `comment_text` is plain text only (markdown shows up literally). A markdown
table becomes a native `table-embed` part — undocumented, the shape the UI writes: `rows`/`columns`
with opaque random ids, `cells` keyed `"r:c"` holding Quill `content`, colspan/rowspan `"1"`.
Dividers/images have no comment part and degrade to a rule line / a plain link.

## Normalization and limits

Description list/blockquote/code-block attributes use nested objects; comment attributes stay flat.
The fixture suite covers these shapes, unknown embeds, ordered text preservation and media chips.
Private content interfaces have no stability guarantee. Probe new embed shapes through UI-write and
API readback before extending the parser. Task descriptions cannot prove notification delivery.

## SyncUp recordings

`scripts/syncup.py` follows the chain: SyncUp root chat message (`A SyncUp Happened` in text/plain) →
reply from the ClickUp AI bot (`user_id` `-4`) linking the notes Doc → Doc pages via v3
`docs/{id}/pages?content_format=text/md` → a bare `*.clickup-attachments.com` media link on the
notes page. Calls over ~1 h get an audio-only recording (1 GB cap), so any media extension counts.
Notes and the recording appear 5–10 min after the call (exit 75). The "Meeting Transcript" page is
the live notetaker's: untimed and possibly partial (it can stop mid-sentence while the recording
runs on). The web player's timed captions come from a private AI-service endpoint
(`/ai/v1/workspaces/{ws}/transcriptions/attachment/{uuid}` on the shard from
`shard/v1/handshake/{ws}`) that rejects personal tokens, so they are unsupported; for a timed
transcript run the recording through video-shrink-for-gemini's local route
(`transcribe-local`) or Gemini.

Official API references: [tasks](https://developer.clickup.com/docs/tasks),
[comment formatting](https://developer.clickup.com/docs/comment-formatting),
[rate limits](https://developer.clickup.com/docs/rate-limits).
