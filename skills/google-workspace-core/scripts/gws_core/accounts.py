"""Which of the user's mailboxes holds a pasted Gmail reference.

The account inventory lists the user's installed Workspace wrappers by their workspace.json path;
credentials stay wherever each wrapper puts them and are never read or listed here. Per entry,
`gmail_lookup: true` is the user's standing permission to try an exact reference in that mailbox
when a link names no account: holding a token never grants it. Docs: ../../references/accounts.md.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from .config import WorkspaceConfig, load_config
from .errors import ApiError, ConfigError, WorkspaceError

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
ENTRY_KEYS = {"config", "gmail_lookup", "note"}
# Scopes that can read message/thread metadata. gmail.compose/send alone cannot.
GMAIL_READ = {"gmail.readonly", "gmail.modify", "gmail.metadata", "mail.google.com"}
HEX = re.compile(r"[0-9a-f]{15,16}")
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "templates"}


class MailNotFound(WorkspaceError):
    """Every exact candidate answered 404/400 in the mailbox(es) checked: absent, not unknown."""


# --- references ------------------------------------------------------------------

@dataclass(frozen=True)
class GmailRef:
    """Exact ids a pasted reference carries. Decimal ids are converted only when Gmail labels them
    (`thread-f:`/`msg-f:`) or the whole input is one bare id; every candidate is checked by the API."""

    threads: tuple[str, ...] = ()   # hex thread ids (bare ids are tried as thread, then message)
    messages: tuple[str, ...] = ()  # hex message ids (msg-f: = received copy)
    drafts: tuple[str, ...] = ()    # compose ids r-<n> (msg-a:), resolved through drafts.get
    web: str | None = None          # new-UI FMfcg… token: server-side, not decodable
    ignored: tuple[str, ...] = ()   # thread-a: ids: no API equivalent, never guessed

    @property
    def exact(self) -> bool:
        return bool(self.threads or self.messages or self.drafts)


def _hex(decimal: str) -> str:
    return format(int(decimal), "x")


def parse_ref(value: str) -> GmailRef:
    """Gmail URL (Print all, Show original, #label/<id>, ?th=), Mail-ref, thread-f:/msg-f:/msg-a: or
    bare hex/decimal id → GmailRef. Raises WorkspaceError when nothing usable is present."""
    raw = value.strip().removeprefix("gmail:").split()[0] if value.strip() else ""
    text = unquote(raw)
    threads = [_hex(d) for d in re.findall(r"thread-f:(\d+)", text)]
    messages = [_hex(d) for d in re.findall(r"msg-f:(\d+)", text)]
    drafts = re.findall(r"msg-a:(r-?\d+)", text)
    ignored = [f"thread-a:{d}" for d in re.findall(r"thread-a:(r-?\d+)", text)]
    web = None
    url = urlparse(text)
    if url.scheme:
        threads += [t.lower() for t in parse_qs(url.query).get("th", []) if HEX.fullmatch(t.lower())]
        last = url.fragment.rsplit("/", 1)[-1] if "/" in url.fragment else ""
        if HEX.fullmatch(last.lower()):
            threads.append(last.lower())
        elif re.fullmatch(r"[A-Za-z0-9_-]{20,}", last):
            web = last
    elif HEX.fullmatch(text.lower()):
        threads, messages = [text.lower()], [text.lower()]
    elif re.fullmatch(r"\d{15,20}", text):
        threads, messages = [_hex(text)], [_hex(text)]
    ref = GmailRef(*(tuple(dict.fromkeys(ids)) for ids in (threads, messages, drafts)), web=web,
                   ignored=tuple(dict.fromkeys(ignored)))
    if ref.exact or ref.web:
        return ref
    if ref.ignored:
        raise WorkspaceError(
            f"{', '.join(ref.ignored)} is not a Gmail API id and is never guessed; paste the received "
            "mail's ⋮ → Show original (msg-f:) or a Print all URL whose simpl= lists msg-f: ids")
    raise WorkspaceError(f"not a Gmail URL or id: {value!r}")


def locate(ws, ref: GmailRef) -> str:
    """Thread id of an exact reference in this mailbox, metadata-only reads, first hit wins.
    404/400 on every candidate → MailNotFound; any other error (403, 5xx, auth) propagates."""
    if not ref.exact:
        raise WorkspaceError("no exact Gmail id to look up")
    probes = ([(f"{GMAIL}/threads/{t}", lambda d: d["id"]) for t in ref.threads]
              + [(f"{GMAIL}/messages/{m}", lambda d: d["threadId"]) for m in ref.messages]
              + [(f"{GMAIL}/drafts/{d}", lambda d: d["message"]["threadId"]) for d in ref.drafts])
    for url, thread_of in probes:
        try:
            return thread_of(ws.api("GET", url, params={"format": "minimal"}))
        except ApiError as exc:
            if exc.status not in (400, 404):
                raise
    raise MailNotFound(f"no thread, message or draft for {_describe(ref)}")


def _describe(ref: GmailRef) -> str:
    return ", ".join([*ref.threads, *(f"msg {m}" for m in ref.messages if m not in ref.threads),
                      *(f"draft {d}" for d in ref.drafts)])


# --- inventory -------------------------------------------------------------------

@dataclass
class Account:
    config_path: Path
    gmail_lookup: bool = False
    note: str = ""
    config: WorkspaceConfig | None = None
    error: str = ""  # config unreadable: listed, never used

    @property
    def gmail_readable(self) -> bool:
        return bool(self.config) and any(s.rstrip("/").rsplit("/", 1)[-1] in GMAIL_READ
                                         for s in self.config.scopes)


def inventory_path() -> Path:
    if value := os.environ.get("GWS_ACCOUNTS"):
        return Path(value).expanduser()
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "google-workspace" / "accounts.json"


def load_inventory(path: Path | None = None) -> list[Account]:
    """{"accounts": [{"config": "<wrapper>/workspace.json", "gmail_lookup": true, "note": "…"}]}.
    Relative config paths resolve against the inventory file. A broken entry is kept with its error."""
    path = path or inventory_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"no account inventory at {path}: create it (`gws.py accounts discover ROOT` "
                          "suggests entries) or set GWS_ACCOUNTS") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"unreadable account inventory {path}: {exc}") from exc
    entries = raw.get("accounts") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise ConfigError(f"{path}: expected {{\"accounts\": [...]}}")
    accounts = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("config"), str) or set(entry) - ENTRY_KEYS:
            raise ConfigError(f"{path}: each account needs \"config\"; allowed keys {sorted(ENTRY_KEYS)}")
        config_path = Path(entry["config"]).expanduser()
        if not config_path.is_absolute():
            config_path = path.parent / config_path
        account = Account(config_path, entry.get("gmail_lookup") is True, str(entry.get("note", "")))
        try:
            account.config = load_config(config_path)
        except ConfigError as exc:
            account.error = str(exc)
        accounts.append(account)
    return accounts


@dataclass
class Located:
    account: Account
    gmail_thread: str
    workspace: object  # open Workspace of the matching mailbox; the caller closes it
    checked: list[dict] = field(default_factory=list)


def locate_any(ref: GmailRef, accounts: list[Account], connect: Callable | None = None) -> Located:
    """Try an exact reference in each lookup-authorized, Gmail-readable mailbox, in inventory order,
    until one holds it. Each candidate's identity is verified through its Gmail profile first.
    Errors are recorded as unknown, never as absent; all-absent → MailNotFound."""
    if connect is None:
        from .session import Workspace as connect
    import httpx

    checked: list[dict] = []

    def note(account: Account, result: str) -> None:
        checked.append({"account": account.config.account if account.config else "?",
                        "config": str(account.config_path), "result": result})

    for account in accounts:
        if not account.gmail_lookup:
            continue
        if account.error:
            note(account, f"error: {account.error}")
            continue
        if not account.gmail_readable:
            note(account, "skipped: no Gmail read scope configured")
            continue
        ws = connect(account.config)
        try:
            actual = str(ws.gmail.profile().get("emailAddress") or "").lower()
            if actual != account.config.account.lower():
                note(account, f"error: authorized as {actual or 'unknown'}")
                ws.close()
                continue
            thread = locate(ws, ref)
        except MailNotFound:
            note(account, "not found")
            ws.close()
            continue
        except (WorkspaceError, httpx.HTTPError, OSError) as exc:
            note(account, f"error: {str(exc).splitlines()[0][:160]}")
            ws.close()
            continue
        note(account, "match")
        return Located(account, thread, ws, checked)
    if not checked:
        raise ConfigError("no account in the inventory has gmail_lookup: true")
    summary = "; ".join(f"{c['account']}: {c['result']}" for c in checked)
    if any(c["result"] != "not found" for c in checked):  # an error or a skipped mailbox proves nothing
        raise WorkspaceError(f"{_describe(ref)} not found where checked; unknown elsewhere ({summary})")
    raise MailNotFound(f"{_describe(ref)} not in any lookup mailbox ({summary})")


def discover(roots: list[Path], max_depth: int = 8) -> list[dict]:
    """Wrapper configs under ROOTS (account, Gmail readability, path), one row per credential dir.
    Reads workspace.json metadata only: never token or client files."""
    rows, seen = [], set()
    for root in roots:
        root = root.expanduser()
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            dirnames[:] = [] if depth >= max_depth else [d for d in dirnames if d not in SKIP_DIRS]
            if "workspace.json" not in filenames:
                continue
            path = Path(dirpath) / "workspace.json"
            try:
                config = load_config(path)
            except ConfigError:
                continue  # some other tool's workspace.json
            key = (config.account.lower(), str(config.config_dir))
            if key in seen:
                continue
            seen.add(key)
            rows.append({"account": config.account, "config": str(path),
                         "gmail_read": Account(path, config=config).gmail_readable})
    return rows
