"""Shared read-only access to T3 Code's SQLite projection store.

Imported by the sibling `uv run --script` CLIs in this directory
(`t3-thread-maintenance`, `t3-fleet`, `t3-limited`, `t3-drafts`). Keep it
dependency-free: every importer except `t3-drafts` (which needs a LevelDB
reader) keeps its inline metadata at `dependencies = []`.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

DEFAULT_STORE = (
    Path(os.environ.get("T3CODE_HOME", Path.home() / ".t3"))
    / "userdata"
    / "state.sqlite"
)


def parse_time(value: str) -> datetime:
    raw = value.strip()
    if len(raw) == 10:
        raw += "T00:00:00+00:00"
    elif raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    return (
        parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    ).astimezone(timezone.utc)


def maybe_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parse_time(value)
    except ValueError:
        return None


def iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


@contextmanager
def connect_readonly(store: Path) -> Iterator[sqlite3.Connection]:
    """Use SQLite's WAL snapshot; readers do not block T3's writers."""
    if not store.exists():
        raise SystemExit(f"T3 store not found: {store}")
    uri = f"file:{quote(str(store), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()
