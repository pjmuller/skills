import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import t3_context


def make_store(path: Path, used: int, window: int, compactions: int = 0) -> Path:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE orchestration_v2_projection_provider_threads (thread_id, updated_at, payload_json)")
    db.execute("CREATE TABLE orchestration_v2_projection_turn_items (thread_id, type)")
    db.execute("CREATE TABLE orchestration_v2_projection_threads (thread_id, title, deleted_at, payload_json)")
    db.executemany("INSERT INTO orchestration_v2_projection_threads VALUES (?, ?, NULL, ?)", [
        ("t1", "🧭 Alex routing", json.dumps({"pinnedAt": "2026-10-29"})),
        ("old", "🧭 Alex routing", json.dumps({"pinnedAt": "2026-10-20", "settledOverride": "settled"})),
        ("opinion", "🧭 Design opinion", "{}"),
    ])
    db.execute("INSERT INTO orchestration_v2_projection_provider_threads VALUES ('t1', '2026-10-30T10:00', ?)",
               (json.dumps({"contextUsage": {"usedTokens": used, "maxTokens": window}}),))
    db.executemany("INSERT INTO orchestration_v2_projection_turn_items VALUES ('t1', 'compaction')",
                   [()] * compactions)
    db.commit()
    db.close()
    return path


def run(capsys, store: Path, *extra: str) -> dict:
    t3_context.main(["t1", "--json", "--store", str(store), *extra])
    return json.loads(capsys.readouterr().out)


def test_below_checkpoint_is_ok(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(t3_context, "NOTICE_DIR", tmp_path / "state")
    out = run(capsys, make_store(tmp_path / "s.db", 100_000, 258_400))
    assert (out["status"], out["pct"], out["checkpoint"]) == ("ok", 39, 155_040)


def test_checkpoint_fires_once_per_compaction_cycle(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(t3_context, "NOTICE_DIR", tmp_path / "state")
    store = make_store(tmp_path / "s.db", 160_000, 258_400)
    assert run(capsys, store)["status"] == "checkpoint"
    assert run(capsys, store)["status"] == "noticed"
    after = make_store(tmp_path / "s2.db", 170_000, 258_400, compactions=1)
    assert run(capsys, after)["status"] == "checkpoint"


def test_large_window_uses_absolute_cap(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(t3_context, "NOTICE_DIR", tmp_path / "state")
    out = run(capsys, make_store(tmp_path / "s.db", 170_000, 1_000_000))
    assert (out["status"], out["checkpoint"]) == ("checkpoint", 160_000)


def test_unknown_thread_is_unknown_not_zero(tmp_path, capsys):
    store = make_store(tmp_path / "s.db", 1, 2)
    t3_context.main(["missing", "--json", "--store", str(store)])
    assert json.loads(capsys.readouterr().out)["status"] == "unknown"


def test_without_thread_id_falls_back_to_pinned_router(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(t3_context, "NOTICE_DIR", tmp_path / "state")
    monkeypatch.delenv("T3CODE_THREAD_ID", raising=False)
    store = make_store(tmp_path / "s.db", 100_000, 258_400)
    t3_context.main(["--store", str(store)])
    assert capsys.readouterr().out.startswith("t1 context 39%")
