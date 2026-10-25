"""Clickable Google links that open the right account: `authuser=<email>`, never `/u/<N>/`.

N is the account's sign-in order in that browser: sign out and back in, in another order, and
/u/2 opens someone else's mailbox. The email always resolves to the same account."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

SLOT_RE = re.compile(r"/u/\d+(?=/|$)")


def _email(account: str) -> str:
    return quote(account.strip().lower(), safe="@")


def with_account(url: str, account: str) -> str:
    """Any Google URL (Docs, Sheets, Drive, Apps Script, Cloud Console, Gmail) pinned to `account`:
    drops a /u/<N> slot and any authuser, then adds authuser=<email>."""
    parts = urlsplit(url)
    path = SLOT_RE.sub("", parts.path) or "/"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "authuser"]
    query.append(("authuser", account.strip().lower()))
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query, safe="@"), parts.fragment))


def gmail_url(account: str, view: str = "inbox") -> str:
    """A Gmail view: `inbox`, `drafts`, `sent`, `all/<thread id>`, `search/<query>`.
    /mail/u/<email>/ answers 404, so the email goes in the query."""
    return f"https://mail.google.com/mail/?authuser={_email(account)}#{view}"


def gmail_thread_url(account: str, thread_id: str) -> str:
    return gmail_url(account, f"all/{thread_id}")


def gmail_draft_url(account: str, message_id: str) -> str:
    """Opens one draft in the compose window; `message_id` is the draft's message.id, not its r-… id."""
    return gmail_url(account, f"drafts?compose={message_id}")
