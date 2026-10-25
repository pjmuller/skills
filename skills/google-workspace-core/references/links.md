# Links for humans: `authuser=<email>`, never `/u/<N>/`

`/u/2` is the account's sign-in order in that browser, not an identity: after a sign-out and a
sign-in in another order it opens another account (or "no access"). The email always resolves.

Build links with `scripts/gws_core/links.py` (`from gws_core.links import …`):

| Function | Result |
|---|---|
| `gmail_url(account, "drafts")` | `mail.google.com/mail/?authuser=<email>#drafts` (`inbox`, `sent`, `search/<q>`) |
| `gmail_thread_url(account, thread_id)` | `…#all/<hex thread id>` (what `Open:` prints) |
| `gmail_draft_url(account, message_id)` | `…#drafts?compose=<message id>`: one draft in compose. The draft's `message.id`, not its `r-…` id |
| `with_account(url, account)` | any Google URL (Docs, Sheets, Drive, Apps Script, Cloud Console): strips `/u/<N>`, sets `authuser` |

Gmail only takes the email in the query: `/mail/u/<email>/` answers 404. A pasted link with
`/u/<N>/` is fine as input (ids parse the same); never hand one back out.
