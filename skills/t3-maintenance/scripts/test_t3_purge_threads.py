"""t3-purge-threads against a synthetic statev2 store: cohorts, families, wakes, hard purge.

  uv run --with pytest pytest test_t3_purge_threads.py
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from v2_fixture import Store

SCRIPT = Path(__file__).with_name("t3-purge-threads")
DAY = 24 * 60


def load_cli():
    loader = importlib.machinery.SourceFileLoader("t3_purge_threads", str(SCRIPT))
    spec = importlib.util.spec_from_loader("t3_purge_threads", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["t3_purge_threads"] = module  # dataclasses resolve __module__ here
    spec.loader.exec_module(module)
    return module


cli = load_cli()


@pytest.fixture
def store(tmp_path: Path) -> Path:
    s = Store(tmp_path / "statev2.sqlite")
    s.thread("archold", "archold", archived=True, minutes=10 * DAY)
    s.message("archold", "user", "SECRET", 10 * DAY, attachments=["archold-att"])
    s.thread("archold-task", "child", parent="archold", minutes=10 * DAY)
    s.thread("archold-grandchild", "grandchild", parent="archold-task", minutes=10 * DAY)
    s.thread("archold-fork", "fork", parent="archold", fork=True, minutes=10 * DAY)
    s.thread("archnew", "archnew", archived=True, minutes=13 * 60)
    s.thread("settold", "settold", settled=True, minutes=10 * DAY)
    s.thread("delold", "delold", deleted=True, minutes=10 * DAY)
    s.thread("otherpr", "otherpr", archived=True, project="q", minutes=10 * DAY)
    s.thread("pinned", "pinned", archived=True, pinned=True, minutes=10 * DAY)
    s.thread("running", "running", archived=True, run="running", minutes=10 * DAY)
    s.thread("livechild", "livechild-parent", archived=True, minutes=10 * DAY)
    s.thread("livechild-sub", "sub", parent="livechild", run="waiting", minutes=10 * DAY)
    s.thread("active", "active", minutes=10 * DAY)
    s.thread("sched", "sched", settled=True, minutes=10 * DAY)
    s.db.execute("INSERT INTO scheduled_tasks VALUES ('t1', 'nightly', 1, 'sched')")
    s.db.execute("INSERT INTO orchestration_events VALUES (1, 'archold', '{}')")
    return s.close()


def selected(store: Path, *args: str, wakes=None) -> set[str]:
    parsed = cli.build_parser().parse_args(["list", *args])
    threads = cli.load_threads(store, datetime.now(UTC))
    rows, _kept = cli.select(parsed, threads, wakes or {})
    return {row.thread_id for row in rows}


@pytest.mark.parametrize("value,expected", [("3d", timedelta(days=3)), ("12h", timedelta(hours=12))])
def test_parse_duration(value: str, expected: timedelta) -> None:
    assert cli.parse_duration(value) == expected


@pytest.mark.parametrize("value", ["3", "3w", "three days", ""])
def test_parse_duration_rejects(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_duration(value)


def test_cohorts_and_exclusions(store: Path) -> None:
    # pinned, running and a family with a live sub-agent are never candidates
    assert selected(store, "--archived") == {"archold", "otherpr"}
    assert selected(store, "--settled") == {"settold", "sched"}
    assert selected(store, "--deleted") == {"delold"}
    assert "archnew" in selected(store, "--archived", "--older-than", "12h")
    assert selected(store, "--archived", "--project", "other") == {"otherpr"}
    with pytest.raises(SystemExit):
        selected(store)


def test_family_goes_together(store: Path) -> None:
    threads = cli.load_threads(store, datetime.now(UTC))
    assert sorted(threads["archold"].descendants) == ["archold-grandchild", "archold-task"]
    assert threads["archold-fork"].top_level  # a fork is its own thread, never purged with its source
    assert threads["archold"].attachment_ids == {"archold-att"}


def test_wakes_keep_threads(store: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    wakes = cli.pending_wakes(store)
    assert wakes == {"sched": "scheduled task nightly"}
    assert selected(store, "--settled", wakes=wakes) == {"settold"}


def test_pending_wakes_fails_closed(store: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        cli.subprocess, "run",
        lambda argv, **_: subprocess.CompletedProcess(argv, 1, "", "boom"),
    )
    with pytest.raises(SystemExit, match="refusing"):
        cli.pending_wakes(store)


def test_provider_log_name() -> None:
    name = cli.provider_log("thread:delegated-task:command%3Amcp%3Ab6678c96-9ecb").name
    assert name == "events.thread-delegated-task-command-3amcp-3ab6678c96-9ecb.log"


def hard_purge(store: Path, tmp_path: Path, monkeypatch, *extra: str) -> Path:
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    monkeypatch.setattr(cli, "PROVIDER_LOGS", logs)
    monkeypatch.setattr(cli, "ATTACHMENTS", tmp_path / "attachments")
    monkeypatch.setattr(cli, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(cli, "LOG_DIR", tmp_path / "actions")
    monkeypatch.setattr(cli, "t3_is_running", lambda: None)
    monkeypatch.setattr(cli, "offer_backup_cleanup", lambda current: None)
    args = cli.build_parser().parse_args(["apply", "--yes", "--archived", *extra])
    args.store = store
    threads = cli.load_threads(store, datetime.now(UTC))
    rows, kept = cli.select(args, threads, {})
    cli.attach_files(rows, threads)
    assert cli.cmd_apply(args, rows, kept) == 0
    return next((tmp_path / "backups").iterdir())


def test_hard_purge_deletes_every_thread_keyed_row(store: Path, tmp_path: Path, monkeypatch) -> None:
    child_log = tmp_path / "logs" / "events.archold-grandchild.log"
    fork_log = tmp_path / "logs" / "events.archold-fork.log"
    (tmp_path / "logs").mkdir()
    child_log.write_text("secret")
    fork_log.write_text("keep")
    backup = hard_purge(store, tmp_path, monkeypatch)
    assert not child_log.exists() and fork_log.exists()  # family files go, a fork's stay
    assert backup.name.startswith("purged-threads-")
    with sqlite3.connect(backup) as copy:
        assert copy.execute("SELECT COUNT(*) FROM orchestration_v2_projection_messages").fetchone()[0] == 1
    with sqlite3.connect(store) as live:
        left = {r[0] for r in live.execute("SELECT thread_id FROM orchestration_v2_projection_threads")}
        assert not left & {"archold", "archold-task", "archold-grandchild", "otherpr"}
        assert {"settold", "pinned", "livechild", "archold-fork"} <= left
        assert live.execute("SELECT COUNT(*) FROM orchestration_events").fetchone()[0] == 0
        assert live.execute("SELECT COUNT(*) FROM scheduled_tasks").fetchone()[0] == 1


def test_hard_purge_refuses_while_running(store: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "t3_is_running", lambda: "T3 server is reachable")
    with pytest.raises(SystemExit, match="Refusing"):
        cli.main(["apply", "--store", str(store), "--yes", "--archived"])


def test_drop_v1_dry_run_by_default(tmp_path: Path, store: Path, monkeypatch, capsys) -> None:
    v1 = tmp_path / "state.sqlite"
    v1.write_bytes(b"x" * 10)
    monkeypatch.setattr(cli, "V1_STORE", v1)
    assert cli.main(["drop-v1", "--store", str(store)]) == 0
    assert v1.exists() and "Dry run" in capsys.readouterr().out
    monkeypatch.setattr(cli, "t3_is_running", lambda: None)
    assert cli.main(["drop-v1", "--store", str(store), "--yes"]) == 0
    assert not v1.exists()


@pytest.mark.parametrize("answer,kept", [("", 0), ("y", 0), ("n", 2)])
def test_offer_backup_cleanup(tmp_path: Path, monkeypatch, answer: str, kept: int) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(cli, "BACKUP_DIR", backups)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    current = backups / "purged-threads-new.sqlite"
    for name in ("statev2-before-purge-old.sqlite", "purged-threads-older.sqlite", current.name):
        (backups / name).write_bytes(b"x")
    cli.offer_backup_cleanup(current, ask=lambda prompt: answer)
    assert current.exists()
    assert len(list(backups.iterdir())) == 1 + kept
