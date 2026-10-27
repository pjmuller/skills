## Access checks

Report identity, offline refresh, granted scopes and access to the requested resource separately: a
profile request proves neither refreshability nor write access. `doctor --live` tests refresh +
identity without saving or printing tokens. Writes stay "untested" unless the task included a verified
write; never mutate user data to test permissions. A 404 can mean missing access or an obsolete id, so
reauthentication alone is not a demonstrated fix.

## Composing messages

Body = plain text (`gmail-draft --body-file PATH`): ordinary paragraphs, `- ` bullets (blank line
between long ones), no fixed-width line breaks. The core always stores `multipart/alternative`: that
text plus an HTML twin (`_text_html` in `scripts/gws_core/gmail.py`: line breaks, indentation and
`> ` quotes preserved, Gmail's soft wraps rejoined). `--html` / `--html-file` only when layout itself
matters: minimal paragraphs/lists, no fixed widths, layout tables, fonts or pasted editor markup; never
auto-convert Markdown. Visual check: render that HTML locally (headless Playwright), never Gmail's
print view (`view=pt` pops the OS print dialog).

> [!IMPORTANT]
> Why the HTML twin (verified 2026-10-22): Gmail web opens a `text/plain`-only draft in Plain text
> mode and hard-wraps every paragraph at ~70 chars when a human clicks Send; with an HTML part it
> opens in rich mode and reflows. API sends (`gmail-send`) are never rewrapped. `gmail-draft-update`
> keeps a draft's existing shape, so an old plain-only draft stays exposed.

From: the mailbox's default send-as identity (`Name <alias>`), else the account address; `--from
alias` or `--from 'Name <alias>'` picks another verified alias.

Diagnose wrapping from the decoded MIME body (`api GET …/messages/<id> --param format=raw`), not wire
lines: quoted-printable soft breaks vanish on decode. `format=flowed` is no fix (needs RFC 3676
encoding and client support). Never send a test email without authorization.

Replies: `--reply-to-message ID` resolves the message's thread and quotes/references its latest
non-draft message (including your own sent mail), ordered by Gmail's `internalDate`. The CLI prints
`Reply-to-message: <id>`; JSON includes `replyToMessage`. Recipients stay as explicitly supplied.
Read the latest thread before composing: advancing the reply target does not update your authored
text. Body-only `gmail-draft-update` and `gmail-draft-send` preserve the existing reply target.
The builder sets no Date header; Gmail supplies it. Quotes preserve the source Date and offset.

## Signatures

API drafts and sends never get the Gmail web signature (it is a compose-window feature of
[sendAs](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.sendAs)).
When the wrapper supplies one, put it once at the end of the newly authored text (the core appends
quoted history after it on replies), replacing a bare closing name rather than stacking; with
`--html-file`, the same visible signature in both alternatives. Check the decoded read-back.

Draft or send is the wrapper's policy; without one, deliver a draft and let the human send it.

## Attachments

- `--attach PATH` (repeatable) on `gmail-draft`, `gmail-send`, `gmail-draft-update`: one part per file
  after the text in a `multipart/mixed` (e.g. invoice PDFs to a mail-in address).
- Missing files, symlinks and >20 MB total are refused before Gmail is called; send larger files as a
  Drive link.
- `files=<n>` is the read-back count; a mismatch is an error. `gmail-draft-update --attach` appends.

## Existing drafts

Edit the latest text from `gmail-draft-get`, keeping the user's wording outside the requested change.
`gmail-draft-update <draft-id> --body-file PATH --expect-message <message-id>` swaps only the body in
place (HTML part = escaped text unless `--html-file`), never sends, verifies the read-back, and refuses
MIME shapes it cannot rewrite without touching other parts (`update_draft`). After a `gmail-draft`
timeout, list drafts before retrying.

Refs: [Gmail drafts](https://developers.google.com/workspace/gmail/api/guides/drafts),
[sendAs](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.sendAs).
