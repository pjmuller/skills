# Account inventory and cross-mailbox lookup

INTENT: one user, several mailboxes (personal, support, company), each behind its own wrapper. A
pasted Gmail link often names no account (`/u/1` is a browser slot), so find the mailbox that holds
it without guessing, borrowing tokens or reading content in the wrong mailbox. Code:
`scripts/gws_core/accounts.py`; `gws.py accounts --help` (no `--config` needed).

**Inventory**: `$GWS_ACCOUNTS`, else `~/.config/google-workspace/accounts.json` (paths only, no
secrets; keep it in your setup repo and symlink it):

```json
{"accounts": [
  {"config": "/abs/repo/.agents/skills/support-mail/workspace.json", "gmail_lookup": true, "note": "support"},
  {"config": "/abs/repo/.agents/skills/google-workspace/workspace.json", "gmail_lookup": false}
]}
```

- Rows point at wrapper configs; this module never opens token files. `accounts list [--check]`
  (`--check` verifies each identity with its own token); `accounts discover ROOT…` suggests rows.
- `gmail_lookup: true` is the **user's** standing permission to try exact references in that mailbox
  when a link names no account. A token, scope or discovered config never grants it; each person
  sets their own. Row order = try order.

**Lookup** (`accounts locate REF`, `locate_any`; `t3-mail-link --all-accounts`):

- Exact references only: thread/message/draft ids from Print all, Show original, `#label/<id>`,
  Mail-ref. Per mailbox: Gmail profile must match the configured account, then metadata-only
  (`format=minimal`) gets; content is read only afterwards, in the matching mailbox.
- First mailbox holding the id wins (ids are per mailbox). 404/400 = absent; 403, auth, network or
  identity mismatch = **unknown**, reported, never "not found".
- An explicitly named account constrains the lookup to its wrapper; never substitute.
- Print all of a thread you started carries `permthid=thread-a:r…`: no API id, never converted; its
  `simpl=msg-f:` refs (received messages) are the candidates. `msg-a:r…` = a draft id (`drafts.get`).
- Content search (`t3-mail-link --search`) and FMfcg… tab tokens stay per account; t3-mail-link maps
  an FMfcg tab to the inventory row of the tab's signed-in account.
- Resolution never drafts, sends, claims, watches, mints, exports or swaps a token; an expired access
  token refreshes into that wrapper's own cache, as on any read.
