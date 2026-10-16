"""Shared read-only access to T3 Code's store (T3 >= 0.1, `statev2.sqlite`).

Imported by the sibling `uv run --script` CLIs (`t3-fleet`, `t3-drafts`,
`t3-my-prompts`, `t3-purge-threads`, `t3-preview-gc`). Dependency-free.

Store facts the CLIs rely on:
- threads: `orchestration_v2_projection_threads`; settle/pin/lineage live in
  `payload_json` (`$.settledOverride`, `$.pinnedAt`, `$.lineage.parentThreadId`,
  `$.lineage.relationshipToParent` = 'subagent' for Agent-tool sub-agents and
  `delegate_task` children, which are not top-level threads).
- messages: `orchestration_v2_projection_messages`, roles user|assistant only
  (reasoning is a turn item, not a message); text, `$.createdBy` ('user' = the
  human) and `$.senderThreadId` (cross-thread sends) in `payload_json`.
- runs: `orchestration_v2_projection_runs.status`; LIVE_RUN = still working.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

USERDATA = Path(os.environ.get("T3CODE_HOME", Path.home() / ".t3")) / "userdata"
DEFAULT_STORE = USERDATA / "statev2.sqlite"
LIVE_RUN = frozenset({"queued", "preparing", "starting", "running", "waiting"})

# Thread ids are opaque since 0.1: a bare UUID (imported history), `mcp:<uuid>`,
# `thread:project:<project>:<uuid>`, or long provider/delegated-task ids.
_UUID_ID = re.compile(
    r"(?:mcp:|thread:project:[0-9a-f-]{36}:)?([0-9a-f]{8}-[0-9a-f-]{27})", re.IGNORECASE
)


def id_key(thread_id: str) -> str:
    """Stable handle: the thread's own UUID when it has one, else a sha1 of the id."""
    match = _UUID_ID.fullmatch(thread_id)
    return (
        match.group(1).lower()
        if match
        else hashlib.sha1(thread_id.encode()).hexdigest()
    )


def short_id(thread_id: str) -> str:
    return id_key(thread_id)[:8]


def resolve_id(thread_ids, needle: str) -> str:
    """Full id, or a >= 8 char prefix of `id_key` (what `short_id` prints)."""
    ids = list(thread_ids)
    if needle in ids:
        return needle
    if len(needle) < 8:
        raise SystemExit(f"thread id {needle!r} too short; use at least 8 characters")
    matches = [tid for tid in ids if id_key(tid).startswith(needle.lower())]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(
        f"{'unknown' if not matches else 'ambiguous'} thread id {needle}"
        + (f": {len(matches)} matches" if matches else "")
    )


def parse_time(value: str) -> datetime:
    raw = value.strip()
    if len(raw) == 10:
        raw += "T00:00:00+00:00"
    elif raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC)


def maybe_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parse_time(value)
    except ValueError:
        return None


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def connect_readonly(store: Path) -> Iterator[sqlite3.Connection]:
    """Use SQLite's WAL snapshot; readers do not block T3's writers."""
    if not store.exists():
        raise SystemExit(
            f"T3 store not found: {store} (T3 Code >= 0.1 must have run here)"
        )
    uri = f"file:{quote(str(store), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()
