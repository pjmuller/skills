"""Searchable backup archive of T3 threads (`~/.t3/backups/t3-archive.sqlite`).

Written by `t3-purge-threads apply` (its cohort, before deleting) and `t3-thread-archive`;
read by `t3-find-thread` as its fallback. Dependency-free; mode 600 (transcripts hold secrets).

Kept per thread: metadata + lineage, every user/assistant message, reasoning head, one entry per
finished tool call (call line + output head/tail), file diffs, sub-agent prompt/result,
questions/answers, errors. Dropped: the event log, started/updated tool states, context-window /
task progress / checkpoint noise, images. Schema contract for readers: `threads` (one row per
thread) and FTS5 `entries` (text, thread_id, seq, role, tool, created_at; role is
user|assistant|reasoning|tool|event). Re-archiving a thread replaces its rows; nothing expires.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from t3_store import id_key

ARCHIVE = Path(
    os.environ.get("T3_ARCHIVE", Path(os.environ.get("T3CODE_HOME", Path.home() / ".t3")) / "backups" / "t3-archive.sqlite")
)
VERSION = "1"

# Caps in chars, tuned on a 6.6 GB store (→ CHANGELOG). Messages stay whole: they are the story.
REASONING_CAP = 1_500  # the "why" behind a step; full reasoning is mostly restating
CALL_CAP = 2_000  # the command / arguments
OUTPUT_HEAD, OUTPUT_TAIL = 2_000, 1_000  # errors and verdicts sit at the tail
FAILED_HEAD, FAILED_TAIL = 4_000, 2_000
DIFF_CAP = 8_000
SUBAGENT_CAP = 8_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS threads (
  thread_id TEXT PRIMARY KEY, id_key TEXT NOT NULL, subagent INTEGER NOT NULL DEFAULT 0,
  parent_thread_id TEXT, root_thread_id TEXT, relationship TEXT,
  project_id TEXT NOT NULL, project_title TEXT NOT NULL, workspace_root TEXT NOT NULL,
  workspace_name TEXT NOT NULL, title TEXT NOT NULL, created_by TEXT,
  provider_instance_id TEXT, model TEXT, branch TEXT, worktree_path TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT, deleted_at TEXT,
  settled INTEGER NOT NULL DEFAULT 0, user_msgs INTEGER NOT NULL DEFAULT 0,
  assistant_msgs INTEGER NOT NULL DEFAULT 0, tool_calls INTEGER NOT NULL DEFAULT 0,
  last_msg_at TEXT, source TEXT NOT NULL, backed_up_at TEXT NOT NULL,
  first_entry INTEGER, last_entry INTEGER  -- the thread's contiguous `entries` rowids
);
CREATE VIRTUAL TABLE IF NOT EXISTS entries USING fts5(
  text, thread_id UNINDEXED, seq UNINDEXED, role UNINDEXED, tool UNINDEXED, created_at UNINDEXED,
  tokenize = "unicode61 remove_diacritics 2"
);
CREATE VIRTUAL TABLE IF NOT EXISTS vocab USING fts5vocab(entries, 'row');
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def open_archive(path: Path = ARCHIVE) -> sqlite3.Connection:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # SQLite gives journal / WAL files the database file's mode.
    path.touch(mode=0o600)
    os.chmod(path, 0o600)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    db.execute("INSERT OR REPLACE INTO meta VALUES ('version', ?)", (VERSION,))
    return db


# --- text shaping -------------------------------------------------------------

_BLOB = re.compile(r"[A-Za-z0-9+/=_-]{400,}")  # base64 images, minified bundles, tokens


def clip(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[:cap] + f" …[+{len(text) - cap} chars]"


def head_tail(text: str, head: int = OUTPUT_HEAD, tail: int = OUTPUT_TAIL) -> str:
    if len(text) <= head + tail:
        return text
    return f"{text[:head]}\n…[{len(text) - head - tail} chars]…\n{text[-tail:]}"


def flatten(value: object) -> str:
    """Text leaves of a tool payload; image blocks and blobs dropped."""
    if value is None:
        return ""
    if isinstance(value, str):
        return _BLOB.sub("[blob]", value)
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(filter(None, (flatten(item) for item in value)))
    if isinstance(value, dict):
        if value.get("type") in ("image", "input_image", "localImage") or "base64" in value:
            return "[image]"
        if "text" in value and isinstance(value["text"], str):
            return flatten(value["text"])
        if "content" in value:
            return flatten(value["content"])
        return "\n".join(
            f"{key}: {text}" if not isinstance(item, (dict, list)) else text
            for key, item in value.items()
            if key not in ("_meta", "tool_use_id", "type", "is_error", "structuredContent")
            and (text := flatten(item))
        )
    return ""


def call_line(value: object) -> str:
    """The most telling argument (command, path, query, prompt), else compact JSON."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("command", "cmd", "file_path", "path", "query", "url", "pattern", "description", "prompt", "code"):
            if isinstance(value.get(key), str):
                rest = {k: v for k, v in value.items() if k != key and isinstance(v, (str, int, float, bool))}
                extra = " " + json.dumps(rest, ensure_ascii=False) if rest else ""
                return value[key] + clip(extra, 300)
        return json.dumps(value, ensure_ascii=False)
    return flatten(value)


def tool_entry(tool: str, call: str, output: str, failed: bool = False) -> tuple[str, str]:
    text = f"{tool}: {clip(call.strip(), CALL_CAP)}"
    if output.strip():
        text += "\n" + (head_tail(output.strip(), FAILED_HEAD, FAILED_TAIL) if failed else head_tail(output.strip()))
    return tool, text


# --- per source shape -----------------------------------------------------------


def questions_text(questions: object) -> str:
    return "\n".join(
        q.get("question", "") + " — " + " / ".join(o.get("label", "") for o in q.get("options") or [])
        for q in questions or [] if isinstance(q, dict)
    )


def legacy_activity(kind: str, summary: str, payload: dict) -> tuple[str, str, str] | None:
    """(role, tool, text) for a 0.0.x `projection_thread_activities` row worth keeping."""
    if kind == "user-input.requested":
        return "event", "question", questions_text(payload.get("questions"))
    if kind == "user-input.resolved":
        return "event", "answer", flatten(payload.get("answers") or payload)
    if kind in ("runtime.error", "provider.turn.start.failed", "context-compaction"):
        return "event", kind, summary
    if kind != "tool.completed":
        return None
    data = payload.get("data") or {}
    item = data.get("item") or {}
    item_type = payload.get("itemType") or ""
    detail = payload.get("detail") or payload.get("title") or ""
    tool = data.get("toolName") or (
        f"{item.get('server')}.{item.get('tool')}" if item.get("server") else item_type
    )
    if item_type == "command_execution":
        tool = "Bash"
    if item_type == "image_view":
        return "tool", tool, f"{tool}: {call_line(data.get('input')) if data.get('input') else detail} [image]"
    if item_type == "file_change" and item.get("changes"):
        diffs = "\n".join(f"{c.get('path')}\n{c.get('diff') or ''}" for c in item["changes"])
        return "tool", "file_change", "file_change: " + clip(diffs, DIFF_CAP)
    if item_type == "file_change" and isinstance(data.get("input"), dict):
        args = data["input"]
        body = args.get("new_string") or args.get("content") or ""
        return "tool", tool, f"{tool}: {args.get('file_path', '')}\n" + clip(body, DIFF_CAP)
    if item_type == "collab_agent_tool_call":
        args = data.get("input") or {}
        prompt = args.get("prompt") or detail
        return "tool", tool, f"{tool}: {clip(prompt, SUBAGENT_CAP)}\n→ {clip(flatten(data.get('result')), SUBAGENT_CAP)}"
    if "input" in data:
        call, output = call_line(data["input"]), flatten(data.get("result"))
        failed = bool((data.get("result") or {}).get("is_error")) if isinstance(data.get("result"), dict) else False
    else:
        call = item.get("command") or (call_line(item["arguments"]) if item.get("arguments") is not None else detail)
        output = flatten(item.get("aggregatedOutput") or item.get("result") or item.get("error"))
        failed = item.get("exitCode") not in (None, 0) or bool(item.get("error"))
        if item.get("exitCode") not in (None, 0):
            output = f"[exit {item['exitCode']}]\n{output}"
    return ("tool", *tool_entry(tool, call or detail, output, failed))


def turn_item(item_type: str, status: str, payload: dict) -> tuple[str, str, str] | None:
    """(role, tool, text) for a V2 turn item; messages come from the messages table."""
    if item_type == "reasoning":
        return "reasoning", "", clip(payload.get("text") or "", REASONING_CAP)
    failed = status == "failed" or payload.get("exitCode") not in (None, 0)
    if item_type == "command_execution":
        output = flatten(payload.get("output"))
        if payload.get("exitCode") not in (None, 0):
            output = f"[exit {payload['exitCode']}]\n{output}"
        return ("tool", *tool_entry("Bash", call_line(payload.get("input")), output, failed))
    if item_type == "dynamic_tool":
        tool = payload.get("toolName") or "tool"
        return ("tool", *tool_entry(tool, call_line(payload.get("input")), flatten(payload.get("output")), failed))
    if item_type == "file_change":
        return "tool", "file_change", f"file_change: {payload.get('fileName', '')}\n" + clip(payload.get("diffStr") or "", DIFF_CAP)
    if item_type == "subagent":
        return "tool", "subagent", (
            f"subagent {payload.get('title') or ''}: {clip(payload.get('prompt') or '', SUBAGENT_CAP)}\n"
            f"→ {clip(flatten(payload.get('result')), SUBAGENT_CAP)}"
        )
    if item_type == "web_search":
        found = "\n".join(r.get("url", "") for r in payload.get("results") or [] if isinstance(r, dict))
        return "tool", "web_search", "web_search: " + clip(flatten(payload.get("patterns")), CALL_CAP) + (
            "\n" + clip(found, CALL_CAP) if found else "")
    if item_type == "error":
        failure = payload.get("failure") or {}
        return "event", "error", clip(f"{failure.get('class', '')}: {failure.get('message', '')}", CALL_CAP)
    if item_type == "user_input_request":
        answers = (payload.get("questionAnswer") or {}).get("answers") or {}
        answered = "\n".join(f"→ {q}: {flatten(a)}" for q, a in answers.items())
        return "event", "question", questions_text(payload.get("questions")) + ("\n" + answered if answered else "")
    if item_type == "compaction":
        return "event", "compaction", f"compacted {payload.get('beforeTokenCount')} → {payload.get('afterTokenCount')} tokens"
    if item_type == "handoff":
        return "event", "handoff", clip(payload.get("summary") or "", CALL_CAP)
    return None


# --- archiving from statev2 ------------------------------------------------------


def table_exists(db: sqlite3.Connection, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone() is not None


def thread_entries(src: sqlite3.Connection, tid: str) -> list[tuple[str, str, str, str]]:
    """(created_at, role, tool, text) in time order."""
    rows: list[tuple[str, str, str, str]] = []
    for m in src.execute(
        "SELECT role, created_at, json_extract(payload_json, '$.text') AS text, "
        "(SELECT group_concat(a.value ->> '$.name', ', ') FROM json_each(payload_json, '$.attachments') a) AS files "
        "FROM orchestration_v2_projection_messages WHERE thread_id = ?", (tid,)
    ):
        text = (m["text"] or "") + (f"\n[attachments: {m['files']}]" if m["files"] else "")
        rows.append((m["created_at"], m["role"], "", text))
    if table_exists(src, "projection_thread_activities"):
        for a in src.execute(
            "SELECT kind, summary, payload_json, created_at FROM projection_thread_activities WHERE thread_id = ? "
            "AND kind IN ('tool.completed', 'user-input.requested', 'user-input.resolved', 'runtime.error', "
            "'provider.turn.start.failed', 'context-compaction')", (tid,)
        ):
            if hit := legacy_activity(a["kind"], a["summary"], json.loads(a["payload_json"] or "{}")):
                rows.append((a["created_at"], *hit))
    if table_exists(src, "orchestration_v2_projection_turn_items"):
        for t in src.execute(
            "SELECT type, status, updated_at, payload_json FROM orchestration_v2_projection_turn_items WHERE thread_id = ? "
            "AND type NOT IN ('user_message', 'assistant_message') AND status != 'running'", (tid,)
        ):
            payload = json.loads(t["payload_json"] or "{}")
            if hit := turn_item(t["type"], t["status"], payload):
                rows.append((payload.get("startedAt") or t["updated_at"], *hit))
    rows = [r for r in rows if r[3].strip()]
    rows.sort(key=lambda r: r[0] or "")
    return rows


THREADS_SQL = """
SELECT t.thread_id, t.project_id, t.title, t.created_at, t.updated_at, t.archived_at, t.deleted_at,
       t.provider_instance_id, t.payload_json, coalesce(p.title, t.project_id) AS project_title,
       coalesce(p.workspace_root, '') AS workspace_root
  FROM orchestration_v2_projection_threads t LEFT JOIN projection_projects p USING (project_id)
"""


def write_thread(db: sqlite3.Connection, meta: dict, entries: list[tuple[str, str, str, str]]) -> None:
    """Replace one thread's rows (idempotent re-archive)."""
    tid = meta["thread_id"]
    if old := db.execute("SELECT first_entry, last_entry FROM threads WHERE thread_id = ?", (tid,)).fetchone():
        db.execute("DELETE FROM entries WHERE rowid BETWEEN ? AND ?", tuple(old))  # no thread_id scan
        db.execute("DELETE FROM threads WHERE thread_id = ?", (tid,))
    first = (db.execute("SELECT max(rowid) FROM entries").fetchone()[0] or 0) + 1
    meta = {"subagent": 0, "settled": 0, **meta,
        "id_key": id_key(tid),
        "workspace_name": Path(meta.get("workspace_root") or "").name,
        "user_msgs": sum(1 for e in entries if e[1] == "user"),
        "assistant_msgs": sum(1 for e in entries if e[1] == "assistant"),
        "tool_calls": sum(1 for e in entries if e[1] == "tool"),
        "last_msg_at": max((e[0] for e in entries if e[1] in ("user", "assistant")), default=None),
        "backed_up_at": now(),
        "first_entry": first,
        "last_entry": first + len(entries) - 1,
    }
    columns = [row[1] for row in db.execute("PRAGMA table_info(threads)")]
    db.execute(
        f"INSERT INTO threads ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        [meta.get(column) for column in columns],
    )
    db.executemany(
        "INSERT INTO entries (rowid, text, thread_id, seq, role, tool, created_at) VALUES (?,?,?,?,?,?,?)",
        [(first + seq, text, tid, seq, role, tool, at) for seq, (at, role, tool, text) in enumerate(entries)],
    )


def archive_threads(src: sqlite3.Connection, db: sqlite3.Connection, ids: Iterable[str] | None = None, *, changed_only: bool = False) -> int:
    """Copy threads (all when `ids` is None) from a statev2 connection; returns the count written.
    `changed_only` skips threads whose `updated_at` matches the archived copy."""
    wanted = None if ids is None else set(ids)
    have = {r[0]: r[1] for r in db.execute("SELECT thread_id, updated_at FROM threads")} if changed_only else {}
    count = 0
    factory, src.row_factory = src.row_factory, sqlite3.Row
    try:
        for row in src.execute(THREADS_SQL).fetchall():
            if (wanted is None or row["thread_id"] in wanted) and have.get(row["thread_id"]) != row["updated_at"]:
                write_thread(db, thread_meta(row), thread_entries(src, row["thread_id"]))
                count += 1
    finally:
        src.row_factory = factory
    return count


def thread_meta(row: sqlite3.Row) -> dict:
    payload = json.loads(row["payload_json"] or "{}")
    lineage = payload.get("lineage") or {}
    return {
        **{k: row[k] for k in ("thread_id", "project_id", "title", "created_at", "updated_at", "archived_at",
                               "deleted_at", "provider_instance_id", "project_title", "workspace_root")},
        "subagent": int(lineage.get("relationshipToParent") == "subagent"),
        "parent_thread_id": lineage.get("parentThreadId"),
        "root_thread_id": lineage.get("rootThreadId"),
        "relationship": lineage.get("relationshipToParent"),
        "created_by": payload.get("createdBy"),
        "model": (payload.get("modelSelection") or {}).get("model"),
        "branch": payload.get("branch"),
        "worktree_path": payload.get("worktreePath"),
        "settled": int(payload.get("settledOverride") == "settled"),
        "source": "statev2",
    }


def import_backup(path: Path, db: sqlite3.Connection, store: Path) -> int:
    """Fold an old slim purge backup (`purged-threads-*.sqlite`) in: the 0.0.x shape
    (`projection_threads` + `projection_thread_messages`) or the V2 one (threads + messages tables).
    Project titles come from the live `store`; threads already archived are left alone; the file
    is remembered in `meta` so purge knows it is superseded."""
    backup = sqlite3.connect(f"file:{quote(str(path), safe='/')}?mode=ro", uri=True)
    backup.row_factory = sqlite3.Row
    backup.execute("ATTACH DATABASE ? AS live", (f"file:{quote(str(store), safe='/')}?mode=ro",))
    have = {r[0] for r in db.execute("SELECT thread_id FROM threads")}
    try:
        if table_exists(backup, "orchestration_v2_projection_threads"):
            fresh = [r[0] for r in backup.execute("SELECT thread_id FROM orchestration_v2_projection_threads") if r[0] not in have]
            count = archive_threads(backup, db, fresh)
        else:
            count = _import_v1(backup, db, have)
    finally:
        backup.close()
    db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (f"imported:{path.name}", now()))
    return count


def imported(db: sqlite3.Connection, path: Path) -> bool:
    return db.execute("SELECT 1 FROM meta WHERE key = ?", (f"imported:{path.name}",)).fetchone() is not None


def _import_v1(backup: sqlite3.Connection, db: sqlite3.Connection, have: set[str]) -> int:
    projects = {r[0]: (r[1], r[2]) for r in backup.execute("SELECT project_id, title, workspace_root FROM live.projection_projects")}
    messages: dict[str, list[tuple[str, str, str, str]]] = {}
    for m in backup.execute(
        "SELECT thread_id, role, text, created_at, (SELECT group_concat(a.value ->> '$.name', ', ') "
        "FROM json_each(coalesce(attachments_json, '[]')) a) AS files FROM projection_thread_messages ORDER BY created_at"
    ):
        text = (m["text"] or "") + (f"\n[attachments: {m['files']}]" if m["files"] else "")
        if text.strip():
            messages.setdefault(m["thread_id"], []).append((m["created_at"], m["role"], "", text))
    count = 0
    for row in backup.execute("SELECT * FROM projection_threads").fetchall():
        tid = row["thread_id"]
        if tid in have:
            continue
        title, root = projects.get(row["project_id"], (row["project_id"], ""))
        meta = {
            **{k: row[k] for k in ("thread_id", "project_id", "title", "created_at", "updated_at", "archived_at", "deleted_at", "branch", "worktree_path")},
            "project_title": title, "workspace_root": root,
            "model": (json.loads(row["model_selection_json"] or "{}") or {}).get("model"),
            "settled": int(row["settled_override"] == "settled"),
            "source": "v1-backup",
        }
        write_thread(db, meta, messages.get(tid, []))
        count += 1
    return count
