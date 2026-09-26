## Access checks

Report account identity, offline refresh, granted scopes and access to the requested resource
separately: a profile request proves neither refreshability nor write access. `doctor --live`
tests refresh + identity without saving or printing tokens. Writes stay "untested" unless the task
included a verified write; never mutate user data to test permissions. A resource 404 can mean
missing access or an obsolete id, so reauthentication alone is not a demonstrated fix.

## Composing messages

Default: plain text (`gmail-draft --body-file PATH` → one `text/plain; charset=utf-8` part).
Ordinary paragraphs and `- ` bullets (blank line between long bullets); no fixed-width line
breaks. `--html` / `--html-file` only when layout itself matters: minimal paragraphs/lists with a
readable plain alternative, no fixed widths, layout tables, fonts or pasted editor markup; never
auto-convert Markdown.

Wrapping gotchas: Python may fold quoted-printable wire lines (soft breaks vanish on decode), and
Gmail's composer may rewrap a draft a person edits and sends. Diagnose from the decoded MIME body,
not wire lines. `format=flowed` is not a fix: it needs RFC 3676 encoding and client support, and
Gmail may rewrite it. Never send a test email without authorization.

Refs: [Gmail drafts](https://developers.google.com/workspace/gmail/api/guides/drafts),
[Python MIME](https://docs.python.org/3/library/email.contentmanager.html),
[RFC 3676](https://www.rfc-editor.org/rfc/rfc3676.html).

## Existing Gmail drafts (either account)

- Base the edit on the draft's latest text (or user-supplied replacement text); preserve the
  user's wording. A tone guide is not permission to rewrite unrelated passages.
- Read raw MIME (`gmail-draft-get`, or `api GET /gmail/v1/users/me/drafts/<id>?format=raw`) to keep
  recipients, subject, reply headers, attachments and multipart bodies. Edit the relevant body
  parts; whole-message `set_content` drops HTML alternatives and attachments.
- Re-fetch right before updating; if it changed, rebase the edit (reduces races, not a lock).
- Update the existing draft in place (no CLI command yet: `api PUT /gmail/v1/users/me/drafts/<id>`
  with the edited raw message), keeping `message.threadId`; don't recreate or send it. After
  a create timeout, list drafts before retrying.
- Read back: intended text, retained fields/attachments, `DRAFT` label. Report the verified outcome.
