"""Searchable backup archive of T3 threads (`~/.t3/backups/t3-archive.sqlite`).

Written by `t3-purge-threads apply` (its cohort, before deleting) and `t3-thread-archive`;
read by `t3-find-thread` as its fallback. Dependency-free; mode 600 (transcripts hold secrets).

Kept per thread: metadata + lineage, every user/assistant message, reasoning head, one entry per
finished tool call (call line + output head/tail), file diffs, sub-agent prompt/result,
questions/answers, errors. Dropped: the event log, started/updated tool states, context-window /
task progress / checkpoint noise, images. Schema contract for readers: `threads` (one row per
thread) and FTS5 `entries` (text, thread_id, seq, role, tool, created_at; role is
user|assistant|reasoning|tool|event). Re-archiving a thread replaces its rows; nothing expires.

Every write goes through `write_thread`, which redacts secrets (`t3_redact`) and stamps
`threads.redaction` with the rule version; `scrub` rebuilds the whole file under the current rules.
One writer at a time: `open_archive` holds `<archive>.lock` for the life of the process.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import t3_redact
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
  first_entry INTEGER, last_entry INTEGER,  -- the thread's contiguous `entries` rowids
  redaction INTEGER  -- t3_redact.VERSION its text went through; NULL = written before redaction
);
CREATE VIRTUAL TABLE IF NOT EXISTS entries USING fts5(
  text, thread_id UNINDEXED, seq UNINDEXED, role UNINDEXED, tool UNINDEXED, created_at UNINDEXED,
  tokenize = "unicode61 remove_diacritics 2"
);
CREATE VIRTUAL TABLE IF NOT EXISTS vocab USING fts5vocab(entries, 'row');
-- Writers without redaction (an older copy of this file) fail here: only `open_archive` registers
-- the function. Readers never fire it.
CREATE TRIGGER IF NOT EXISTS redacting_writer BEFORE INSERT ON threads
  BEGIN SELECT RAISE(ABORT, 'archive writer predates redaction') WHERE t3_redaction_version() < 1; END;
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


_LOCKS: dict[Path, int] = {}


def writer_lock(path: Path) -> None:
    """Exclusive `<archive>.lock` until the process exits: purge, sync, import and scrub never
    interleave, and nobody writes into a file `scrub` is about to replace."""
    path = path.resolve()
    if path in _LOCKS:
        return
    fd = os.open(path.with_name(path.name + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"waiting for another archive writer ({path.name}.lock)…", file=sys.stderr)
        fcntl.flock(fd, fcntl.LOCK_EX)
    _LOCKS[path] = fd


def open_archive(path: Path = ARCHIVE) -> sqlite3.Connection:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    writer_lock(path)  # before connecting: a replaced file must be opened afresh
    # SQLite gives journal / WAL files the database file's mode.
    path.touch(mode=0o600)
    os.chmod(path, 0o600)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    register(db)
    db.execute("PRAGMA secure_delete = ON")  # a re-archived thread's old text is zeroed, not left in free pages
    db.executescript(SCHEMA)
    if "redaction" not in {row[1] for row in db.execute("PRAGMA table_info(threads)")}:
        db.execute("ALTER TABLE threads ADD COLUMN redaction INTEGER")
    db.execute("INSERT OR REPLACE INTO meta VALUES ('version', ?)", (VERSION,))
    db.commit()
    if stale := stale_threads(db):
        print(f"archive: {stale} threads (or leftover index text) predate redaction v{t3_redact.VERSION}; "
              "run `t3-thread-archive scrub`", file=sys.stderr)
    return db


def register(db: sqlite3.Connection) -> None:
    db.create_function("t3_redaction_version", 0, lambda: t3_redact.VERSION, deterministic=True)


def stale_threads(db: sqlite3.Connection) -> int:
    """Threads under older rules, plus 1 while old text may linger in FTS segments: re-archiving a
    stale thread replaces its rows, but FTS5 keeps deleted tokens until a rebuild (`scrub`)."""
    stale = db.execute("SELECT COUNT(*) FROM threads WHERE coalesce(redaction, 0) < ?", (t3_redact.VERSION,)).fetchone()[0]
    return stale + bool(db.execute("SELECT 1 FROM meta WHERE key = 'scrub_required'").fetchone())


# --- text shaping -------------------------------------------------------------

_BLOB = re.compile(r"[A-Za-z0-9+/=_-]{400,}")  # base64 images, minified bundles, tokens


# Redactions made while clipping, credited to the next `write_thread` (entries are built per thread
# right before it writes them).
CLIP_HITS: Counter = Counter()
_MARGIN = 16_384  # context kept around the parts that survive a cut, before redacting


def _redact_for_cut(text: str, head: int, tail: int) -> tuple[str, int]:
    """Redact before cutting: a cut can drop a key (`PASSWORD = …`) or split a token so the kept part
    no longer matches a rule. Huge texts keep a margin around head and tail (rules are local)."""
    total = len(text)
    if total > head + tail + 2 * _MARGIN:
        text = text[:head + _MARGIN] + "\n" + text[-(tail + _MARGIN):]
    text, found = t3_redact.redact(text)
    CLIP_HITS.update(found)
    return text, total - len(text)  # chars already dropped by the margin cut


def _snap(text: str, at: int, forward: bool = False) -> int:
    """The nearest whitespace ≤ 200 chars from a cut, so the cut splits no marker or word."""
    if forward:
        found = re.search(r"\s", text[at:at + 200])
        return at + found.start() if found else at
    found = re.search(r"\s\S*\Z", text[max(0, at - 200):at])
    return max(0, at - 200) + found.start() if found else at


def clip(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    text, dropped = _redact_for_cut(text, cap, 0)
    if len(text) <= cap:
        return text
    cut = _snap(text, cap)
    return text[:cut] + f" …[+{len(text) - cut + dropped} chars]"


def head_tail(text: str, head: int = OUTPUT_HEAD, tail: int = OUTPUT_TAIL) -> str:
    if len(text) <= head + tail:
        return text
    text, dropped = _redact_for_cut(text, head, tail)
    if len(text) <= head + tail:
        return text
    start, end = _snap(text, head), _snap(text, len(text) - tail, forward=True)
    return f"{text[:start]}\n…[{end - start + dropped} chars]…\n{text[end:]}"


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


def write_thread(db: sqlite3.Connection, meta: dict, entries: list[tuple[str, str, str, str]],
                 hits: Counter | None = None) -> None:
    """Replace one thread's rows (idempotent re-archive), secrets redacted; `hits` counts them."""
    hits = Counter() if hits is None else hits
    tid = meta["thread_id"]
    entries = [(at, role, tool, redacted(text, hits)) for at, role, tool, text in entries]
    meta = {**meta, "title": redacted(meta.get("title") or "", hits)}
    hits.update(CLIP_HITS)
    CLIP_HITS.clear()
    if old := db.execute("SELECT first_entry, last_entry, coalesce(redaction, 0) FROM threads WHERE thread_id = ?", (tid,)).fetchone():
        if old[2] < t3_redact.VERSION:  # its unredacted tokens stay in FTS segments until a rebuild
            db.execute("INSERT OR REPLACE INTO meta VALUES ('scrub_required', ?)", (now(),))
        db.execute("DELETE FROM entries WHERE rowid BETWEEN ? AND ?", tuple(old[:2]))  # no thread_id scan
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
        "redaction": t3_redact.VERSION,
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


def redacted(text: str, hits: Counter) -> str:
    text, found = t3_redact.redact(text)
    hits.update(found)
    return text


def archive_threads(src: sqlite3.Connection, db: sqlite3.Connection, ids: Iterable[str] | None = None, *,
                    changed_only: bool = False, hits: Counter | None = None) -> int:
    """Copy threads (all when `ids` is None) from a statev2 connection; returns the count written.
    `changed_only` skips threads whose `updated_at` matches the archived copy and whose redaction is
    current (older rules → rewritten from the source); `hits` counts redactions."""
    wanted = None if ids is None else set(ids)
    have = {r[0]: r[1] for r in db.execute("SELECT thread_id, updated_at FROM threads WHERE redaction >= ?",
                                           (t3_redact.VERSION,))} if changed_only else {}
    count = 0
    factory, src.row_factory = src.row_factory, sqlite3.Row
    try:
        for row in src.execute(THREADS_SQL).fetchall():
            if (wanted is None or row["thread_id"] in wanted) and have.get(row["thread_id"]) != row["updated_at"]:
                write_thread(db, thread_meta(row), thread_entries(src, row["thread_id"]), hits)
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


def import_backup(path: Path, db: sqlite3.Connection, store: Path, hits: Counter | None = None) -> int:
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
            count = archive_threads(backup, db, fresh, hits=hits)
        else:
            count = _import_v1(backup, db, have, hits)
    finally:
        backup.close()
    db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (f"imported:{path.name}", now()))
    return count


def imported(db: sqlite3.Connection, path: Path) -> bool:
    return db.execute("SELECT 1 FROM meta WHERE key = ?", (f"imported:{path.name}",)).fetchone() is not None


def _import_v1(backup: sqlite3.Connection, db: sqlite3.Connection, have: set[str], hits: Counter | None) -> int:
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
        write_thread(db, meta, messages.get(tid, []), hits)
        count += 1
    return count


# --- retroactive redaction -------------------------------------------------------------------


def scan(path: Path = ARCHIVE) -> tuple[Counter, int]:
    """(redactions the current rules would make, threads they touch); read-only, values never leave."""
    db = sqlite3.connect(f"file:{quote(str(path), safe='/')}?mode=ro", uri=True)
    hits, threads = Counter(), set()
    try:
        for tid, title in db.execute("SELECT thread_id, title FROM threads"):
            if found := t3_redact.redact(title or "")[1]:
                hits.update(found)
                threads.add(tid)
        for tid, text in db.execute("SELECT thread_id, text FROM entries"):
            if found := t3_redact.redact(text)[1]:
                hits.update(found)
                threads.add(tid)
    finally:
        db.close()
    return hits, len(threads)


def scrub(path: Path = ARCHIVE, *, step=print) -> Counter:
    """Rebuild the archive under the current redaction rules and swap it in atomically.

    A fresh file, not UPDATEs in place: the old text would linger in FTS5 segments, free pages and
    the rollback journal. Thread ids, rowids and `first_entry`/`last_entry` stay identical, so
    readers and re-archives keep working. Verified before the swap (integrity, FTS integrity,
    row/rowid parity, a second pass finds nothing); any failure leaves the old archive untouched.
    Holds the writer lock throughout. Disk: one archive-sized temp file next to it."""
    path = path.resolve()
    writer_lock(path)
    old = open_archive(path)  # migrates the schema and rolls back any hot journal
    old.close()
    tmp = path.with_name(path.name + ".scrub-tmp")
    for leftover in (tmp, tmp.with_name(tmp.name + "-journal")):
        leftover.unlink(missing_ok=True)
    os.close(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    hits: Counter = Counter()
    try:
        db = sqlite3.connect(f"file:{quote(str(tmp), safe='/')}", uri=True)
        register(db)
        db.create_function("redact", 1, lambda text: redacted(text, hits) if text else text, deterministic=True)
        db.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;" + SCHEMA)
        db.execute("ATTACH DATABASE ? AS old", (f"file:{quote(str(path), safe='/')}?mode=ro",))
        columns = [row[1] for row in db.execute("PRAGMA table_info(threads)")]
        pick = ", ".join({"title": "redact(title)", "redaction": str(t3_redact.VERSION)}.get(c, c) for c in columns)
        with db:
            db.execute("INSERT INTO meta SELECT * FROM old.meta WHERE key != 'scrub_required'")
            db.execute("INSERT OR REPLACE INTO meta VALUES ('redaction', ?)", (str(t3_redact.VERSION),))
            db.execute(f"INSERT INTO threads ({', '.join(columns)}) SELECT {pick} FROM old.threads")
            step(f"threads copied ({db.execute('SELECT COUNT(*) FROM threads').fetchone()[0]}), redacting entries")
            db.execute("INSERT INTO entries (rowid, text, thread_id, seq, role, tool, created_at) "
                       "SELECT rowid, redact(text), thread_id, seq, role, tool, created_at FROM old.entries ORDER BY rowid")
            db.execute("INSERT INTO entries (entries) VALUES ('optimize')")
        step(f"redacted {sum(hits.values())} values; verifying")
        verify_scrub(db)
        db.execute("DETACH DATABASE old")
        db.close()
        fd = os.open(tmp, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    step(f"swapped in {path} ({path.stat().st_size / 1_048_576:.0f} MB)")
    return hits


def verify_scrub(db: sqlite3.Connection) -> None:
    """Raise unless the rebuilt archive (`main`) mirrors `old` row for row and is fully redacted."""
    def one(sql: str):
        return db.execute(sql).fetchone()[0]

    problems = []
    if (check := one("PRAGMA main.integrity_check")) != "ok":
        problems.append(f"integrity_check: {check}")
    try:
        with db:
            db.execute("INSERT INTO entries (entries) VALUES ('integrity-check')")
    except sqlite3.DatabaseError as error:
        problems.append(f"fts integrity-check: {error}")
    for table, key in (("threads", "thread_id"), ("entries", "rowid")):
        if one(f"SELECT COUNT(*) FROM main.{table}") != one(f"SELECT COUNT(*) FROM old.{table}"):
            problems.append(f"{table}: row count differs")
        if one(f"SELECT COUNT(*) FROM main.{table} n JOIN old.{table} o ON n.{key} = o.{key}") != one(f"SELECT COUNT(*) FROM old.{table}"):
            problems.append(f"{table}: {key}s differ")
    if one("SELECT COUNT(*) FROM main.entries n JOIN old.entries o ON n.rowid = o.rowid "
           "WHERE n.thread_id IS NOT o.thread_id OR n.seq IS NOT o.seq OR n.role IS NOT o.role"):
        problems.append("entries: thread/seq/role differ")
    if one("SELECT COUNT(*) FROM main.threads n JOIN old.threads o USING (thread_id) "
           "WHERE n.first_entry IS NOT o.first_entry OR n.last_entry IS NOT o.last_entry "
           "OR n.parent_thread_id IS NOT o.parent_thread_id OR n.root_thread_id IS NOT o.root_thread_id"):
        problems.append("threads: entry ranges or lineage differ")
    again = sum(1 for (text,) in db.execute("SELECT text FROM main.entries") if t3_redact.redact(text)[1])
    if again:
        problems.append(f"{again} entries still match a rule after redaction (not idempotent)")
    if problems:
        raise SystemExit("scrub verification failed, archive left untouched: " + "; ".join(problems))
