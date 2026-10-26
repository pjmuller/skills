# Links for humans: `authuser=<email>`, never `/u/<N>/`

`/u/2` is the browser's sign-in order, not an identity: after a re-sign-in in another order it opens
another account (or "no access"). The email always resolves. Build links with
`scripts/gws_core/links.py`:

| Function | Result |
|---|---|
| `gmail_url(account, "drafts")` | `mail.google.com/mail/?authuser=<email>#drafts` (`inbox`, `sent`, `search/<q>`) |
| `gmail_thread_url(account, thread_id)` | `…#all/<hex thread id>` (what `Open:` prints) |
| `gmail_draft_url(account, message_id)` | `…#drafts?compose=<message id>`: the draft's `message.id`, not its `r-…` id |
| `with_account(url, account)` | any Google URL (Docs, Sheets, Drive, Apps Script, Cloud Console): strips `/u/<N>`, sets `authuser` |

Gmail takes the email only in the query (`/mail/u/<email>/` is a 404). A pasted `/u/<N>/` link is fine
as input; never hand one back out.
