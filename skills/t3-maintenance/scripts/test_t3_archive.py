"""t3_archive: what a thread keeps, idempotent re-archive, old backup import.

  uv run --with pytest pytest test_t3_archive.py
"""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest
import t3_archive
from v2_fixture import Store


@pytest.fixture
def store(tmp_path: Path) -> Path:
    s = Store(tmp_path / "statev2.sqlite")
    s.thread("t1", "Fix the deploy", minutes=60, settled=True)
    s.message("t1", "user", "why does the deploy fail", 59)
    s.message("t1", "assistant", "The migration lock times out.", 50)
    # 0.0.x Claude Bash: the whole output is huge; head and tail survive
    s.activity("t1", "tool.completed", {"itemType": "command_execution", "data": {
        "toolName": "Bash", "input": {"command": "make deploy", "description": "Deploy"},
        "result": {"type": "tool_result", "content": "start\n" + "x " * 5000 + "\nERROR lock timeout"}}}, 58)
    s.activity("t1", "tool.updated", {"itemType": "command_execution", "data": {}}, 58)  # dropped
    # 0.0.x Codex command + an image view (image bytes dropped)
    s.activity("t1", "tool.completed", {"itemType": "command_execution", "detail": "short…", "data": {
        "item": {"command": "git log -1 --format=%H", "aggregatedOutput": "abc123", "exitCode": 0}}}, 57)
    s.activity("t1", "tool.completed", {"itemType": "image_view", "data": {
        "toolName": "Read", "input": {"file_path": "/tmp/shot.png"}, "result": {"content": [{"type": "image", "source": {"data": "A" * 9000}}]}}}, 56)
    s.activity("t1", "context-window.updated", {"usedTokens": 1}, 56)  # dropped
    # V2 items: reasoning, diff, failing command, a still-running call (skipped)
    s.item("t1", "reasoning", {"text": "think " * 1000}, 55)
    s.item("t1", "file_change", {"fileName": "db/lock.rb", "diffStr": "+timeout 30"}, 54)
    s.item("t1", "command_execution", {"input": "bin/test", "output": "1 failure", "exitCode": 1}, 53)
    s.item("t1", "command_execution", {"input": "sleep 999"}, 52, status="running")
    s.item("t1", "error", {"failure": {"class": "transport_error", "message": "stream disconnected"}}, 51, status="failed")
    s.item("t1", "user_input_request", {"questions": [{"question": "Which db?", "options": [{"label": "pg"}, {"label": "mysql"}]}],
                                        "questionAnswer": {"answers": {"Which db?": "pg"}}}, 50)
    s.thread("t2", "Other", minutes=30)
    s.message("t2", "user", "unrelated", 29)
    return s.close()


def archive(store: Path, path: Path, ids=None, **kw) -> sqlite3.Connection:
    db = t3_archive.open_archive(path)
    with sqlite3.connect(store) as src, db:
        t3_archive.archive_threads(src, db, ids, **kw)
    return db


def texts(db: sqlite3.Connection, tid: str) -> list[tuple[str, str, str]]:
    return [tuple(r) for r in db.execute("SELECT role, tool, text FROM entries WHERE thread_id = ? ORDER BY seq", (tid,))]


def test_keeps_conversation_and_tool_gist(store: Path, tmp_path: Path) -> None:
    db = archive(store, tmp_path / "a.sqlite", ["t1"])
    rows = texts(db, "t1")
    roles = [r[0] for r in rows]
    assert roles.count("user") == 1 and roles.count("assistant") == 1 and roles.count("reasoning") == 1
    bash = next(r[2] for r in rows if "make deploy" in r[2])
    assert bash.startswith("Bash: make deploy") and bash.endswith("ERROR lock timeout") and len(bash) < t3_archive.OUTPUT_HEAD + t3_archive.OUTPUT_TAIL + 100
    assert any(r[2] == "Bash: git log -1 --format=%H\nabc123" for r in rows)  # full command, not the detail
    image = next(r[2] for r in rows if "shot.png" in r[2])
    assert "AAAA" not in image
    assert any("db/lock.rb" in r[2] and "+timeout 30" in r[2] for r in rows)
    assert any(r[2].startswith("Bash: bin/test\n[exit 1]") for r in rows)
    assert not any("sleep 999" in r[2] for r in rows)
    assert ("event", "error", "transport_error: stream disconnected") in rows
    assert ("event", "question", "Which db? — pg / mysql\n→ Which db?: pg") in rows
    assert len(next(r[2] for r in rows if r[0] == "reasoning")) < t3_archive.REASONING_CAP + 40
    meta = db.execute("SELECT settled, tool_calls, user_msgs FROM threads WHERE thread_id = 't1'").fetchone()
    assert tuple(meta) == (1, 5, 1)
    assert db.execute("SELECT thread_id FROM entries WHERE entries MATCH 'timeout'").fetchone()[0] == "t1"
    assert stat.S_IMODE((tmp_path / "a.sqlite").stat().st_mode) == 0o600


def test_rearchive_replaces_and_skips_unchanged(store: Path, tmp_path: Path) -> None:
    path = tmp_path / "a.sqlite"
    archive(store, path).close()
    before = sqlite3.connect(path).execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    db = t3_archive.open_archive(path)
    with sqlite3.connect(store) as src, db:
        assert t3_archive.archive_threads(src, db, changed_only=True) == 0
        assert t3_archive.archive_threads(src, db) == 2
    assert db.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == before


def test_import_old_v1_backup(store: Path, tmp_path: Path) -> None:
    old = tmp_path / "purged-threads-old.sqlite"
    with sqlite3.connect(old) as b:
        b.executescript("""
            CREATE TABLE projection_threads (thread_id, project_id, title, branch, worktree_path, created_at,
              updated_at, deleted_at, archived_at, model_selection_json, settled_override);
            CREATE TABLE projection_thread_messages (message_id, thread_id, role, text, created_at, attachments_json);
            INSERT INTO projection_threads VALUES ('v1', 'p', 'Old referral stats', NULL, NULL,
              '2026-04-01T00:00:00Z', '2026-04-02T00:00:00Z', NULL, NULL, '{"model":"m"}', 'settled');
            INSERT INTO projection_thread_messages VALUES ('m', 'v1', 'user', 'count referrals', '2026-04-01T00:00:01Z',
              '[{"type":"image","name":"chart.png"}]');
        """)
    db = t3_archive.open_archive(tmp_path / "a.sqlite")
    with db:
        assert t3_archive.import_backup(old, db, store) == 1
        assert t3_archive.import_backup(old, db, store) == 0
    row = db.execute("SELECT project_title, source, user_msgs FROM threads WHERE thread_id = 'v1'").fetchone()
    assert tuple(row) == ("fixture", "v1-backup", 1)
    assert texts(db, "v1") == [("user", "", "count referrals\n[attachments: chart.png]")]
    assert t3_archive.imported(db, old)
