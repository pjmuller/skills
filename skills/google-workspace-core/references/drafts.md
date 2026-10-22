## Access checks

Report account identity, offline refresh, granted scopes and access to the requested resource
separately: a profile request proves neither refreshability nor write access. `doctor --live`
tests refresh + identity without saving or printing tokens. Writes stay "untested" unless the task
included a verified write; never mutate user data to test permissions. A resource 404 can mean
missing access or an obsolete id, so reauthentication alone is not a demonstrated fix.

## Composing messages

Write the body as plain text (`gmail-draft --body-file PATH`): ordinary paragraphs and `- `
bullets (blank line between long bullets), no fixed-width line breaks. The core always stores a
`multipart/alternative`: that text as `text/plain` plus an escaped HTML twin (`<br>` per line).
`--html` / `--html-file` only when layout itself matters: minimal paragraphs/lists, no fixed
widths, layout tables, fonts or pasted editor markup; never auto-convert Markdown.

> [!IMPORTANT]
> Why the HTML twin (verified 2026-10-22, test mails `[test wrap 1-3]`): Gmail web opens a
> `text/plain`-only draft in **Plain text mode** and hard-wraps every paragraph at ~70 chars when
> a human clicks Send. With an HTML part it opens in rich mode: the sent HTML reflows (its plain
> alternative is wrapped by Gmail as for any mail). API sends (`gmail-send`) are never rewrapped.
> `gmail-draft-update` keeps a draft's existing shape, so an old plain-only draft stays exposed.

From: the mailbox's default send-as identity (`Name <alias>`, Gmail settings), else the
account address; `--from alias` or `--from 'Name <alias>'` picks another verified alias.

Diagnose wrapping from the decoded MIME body (`api GET …/messages/<id> --param format=raw`), not
wire lines: quoted-printable soft breaks vanish on decode. `format=flowed` is not a fix (needs RFC
3676 encoding and client support). Never send a test email without authorization.

Refs: [Gmail drafts](https://developers.google.com/workspace/gmail/api/guides/drafts),
[sendAs](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.sendAs),
[Python MIME](https://docs.python.org/3/library/email.contentmanager.html).

## Attachments

- `--attach PATH` (repeatable) on `gmail-draft`, `gmail-send` and `gmail-draft-update`: text
  part(s) first, then one `attachment` part per file in a `multipart/mixed` (mimetype guessed,
  else `application/octet-stream`). Use it to forward invoice PDFs, e.g. to a Yuki mail-in address.
- Missing files, symlinks and more than 20 MB in total are refused before Gmail is called; larger
  files go as a Drive link.
- Output `files=<n>` is the read-back count of stored attachments; a mismatch is an error.
  `gmail-draft-update --attach` appends to the draft's existing files.

## Existing Gmail drafts (either account)

Edit the latest text from `gmail-draft-get`, keeping the user's wording outside the requested change;
`gmail-draft-update <draft-id> --body-file PATH --expect-message <message-id>` swaps only the body
in place (HTML part = escaped text unless `--html-file`), never sends and verifies the read-back.
MIME shapes it cannot rewrite without touching other parts are refused before writing
(`update_draft` in `scripts/gws_core/gmail.py`). After a `gmail-draft` timeout, list drafts before retrying.
