#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Cohort selection + --older-than parsing for t3-purge-threads.

Runs the real CLI against a tiny on-disk fixture store, so the SQL in
`load_threads` is exercised too (the read-only connection needs a real file).

  uv run --with pytest pytest test_t3_purge_threads.py
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("t3-purge-threads")


def load_cli():
    spec = importlib.util.spec_from_loader(
        "t3_purge_threads",
        importlib.machinery.SourceFileLoader("t3_purge_threads", str(SCRIPT)),
    )
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves __module__ through sys.modules; register before exec.
    sys.modules["t3_purge_threads"] = module
    spec.loader.exec_module(module)
    return module


cli = load_cli()


def stamp(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


@pytest.fixture
def store(tmp_path: Path) -> Path:
    path = tmp_path / "state.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE projection_projects (
          project_id TEXT PRIMARY KEY, title TEXT, workspace_root TEXT);
        CREATE TABLE projection_threads (
          thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT,
          created_at TEXT, updated_at TEXT, archived_at TEXT, deleted_at TEXT,
          settled_override TEXT, pinned_at TEXT,
          pending_approval_count INTEGER DEFAULT 0,
          pending_user_input_count INTEGER DEFAULT 0, model_selection_json TEXT);
        CREATE TABLE projection_thread_messages (
          message_id TEXT PRIMARY KEY, thread_id TEXT);
        CREATE TABLE projection_thread_sessions (
          thread_id TEXT PRIMARY KEY, status TEXT, provider_name TEXT,
          provider_instance_id TEXT);
        CREATE TABLE provider_session_runtime (
          thread_id TEXT PRIMARY KEY, provider_instance_id TEXT,
          runtime_payload_json TEXT, resume_cursor_json TEXT);
        CREATE TABLE orchestration_events (
          aggregate_kind TEXT, stream_id TEXT, payload_json TEXT);
        CREATE TABLE orchestration_command_receipts (
          command_id TEXT PRIMARY KEY, aggregate_kind TEXT, aggregate_id TEXT);
        CREATE TABLE projection_thread_activities (
          activity_id TEXT PRIMARY KEY, thread_id TEXT, payload_json TEXT);
        CREATE TABLE projection_turns (row_id INTEGER PRIMARY KEY, thread_id TEXT);
        CREATE TABLE projection_pending_approvals (
          request_id TEXT PRIMARY KEY, thread_id TEXT);
        CREATE TABLE projection_thread_proposed_plans (
          plan_id TEXT PRIMARY KEY, thread_id TEXT);
        CREATE TABLE checkpoint_diff_blobs (thread_id TEXT, diff TEXT);
        INSERT INTO projection_projects VALUES ('p','fixture','/tmp/fixture');
        INSERT INTO projection_projects VALUES ('q','other','/tmp/other');
    """)
    now = datetime.now(timezone.utc)

    def thread(name: str, days: float, **overrides: object) -> None:
        thread_id = f"{name:>08.8}-0000-0000-0000-000000000000".replace(" ", "0")
        when = stamp(now - timedelta(days=days))
        row = {
            "project_id": "p",
            "archived_at": None,
            "deleted_at": None,
            "settled_override": None,
            "pinned_at": None,
            "pending_approval_count": 0,
            "pending_user_input_count": 0,
            "status": "stopped",
        } | overrides
        connection.execute(
            "INSERT INTO projection_threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                thread_id, row["project_id"], name, when, when,
                row["archived_at"], row["deleted_at"], row["settled_override"],
                row["pinned_at"], row["pending_approval_count"],
                row["pending_user_input_count"], '{"instanceId":"claudeAgent"}',
            ),
        )
        connection.execute(
            "INSERT INTO projection_thread_sessions VALUES (?,?,?,?)",
            (thread_id, row["status"], "claudeAgent", "claudeAgent"),
        )
        connection.execute(
            "INSERT INTO orchestration_events VALUES ('thread',?,?)",
            (thread_id, "x" * 1024),
        )

    old = stamp(now - timedelta(days=30))
    thread("archold", 10, archived_at=old)
    thread("archnew", 1, archived_at=old)
    thread("settold", 10, settled_override="settled")
    thread("delold", 10, deleted_at=old)
    thread("activold", 10)
    thread("pinned", 10, archived_at=old, pinned_at=old)
    thread("running", 10, archived_at=old, status="running")
    thread("blocked", 10, archived_at=old, pending_approval_count=1)
    thread("otherpr", 10, archived_at=old, project_id="q")
    connection.commit()
    connection.close()
    return path


def selected(store: Path, *argv: str) -> set[str]:
    args = cli.build_parser().parse_args(["list", *argv])
    args.store = store
    threads = cli.load_threads(store, datetime.now(timezone.utc), with_sizes=True)
    return {item.title for item in cli.select(args, threads)}


@pytest.mark.parametrize(
    "value,expected",
    [("3d", timedelta(days=3)), ("12h", timedelta(hours=12)), ("0d", timedelta(0))],
)
def test_parse_duration(value: str, expected: timedelta) -> None:
    assert cli.parse_duration(value) == expected


@pytest.mark.parametrize("value", ["3", "3w", "3m", "three days", ""])
def test_parse_duration_rejects(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_duration(value)


def test_cohorts_are_ored_and_never_touch_active(store: Path) -> None:
    assert selected(store, "--archived") == {"archold", "otherpr"}
    assert selected(store, "--settled") == {"settold"}
    assert selected(store, "--deleted") == {"delold"}
    assert selected(store, "--archived", "--settled", "--deleted") == {
        "archold", "otherpr", "settold", "delold"
    }


def test_requires_a_cohort(store: Path) -> None:
    with pytest.raises(SystemExit):
        selected(store)


def test_older_than_excludes_recent(store: Path) -> None:
    assert "archnew" not in selected(store, "--archived", "--older-than", "3d")
    assert "archnew" in selected(store, "--archived", "--older-than", "12h")


def test_hard_exclusions(store: Path) -> None:
    picked = selected(store, "--archived", "--older-than", "1h")
    assert "pinned" not in picked
    assert "running" not in picked
    assert "blocked" not in picked


def test_project_filter(store: Path) -> None:
    assert selected(store, "--archived", "--project", "other") == {"otherpr"}
    assert "otherpr" not in selected(store, "--archived", "--project", "fixture")


def test_sizes_and_row_counts(store: Path) -> None:
    args = cli.build_parser().parse_args(["list", "--archived"])
    args.store = store
    threads = cli.load_threads(store, datetime.now(timezone.utc), with_sizes=True)
    rows = cli.select(args, threads)
    assert cli.summary(rows)["rows"]["orchestration_events"] == len(rows)
    assert rows[0].payload_bytes == 1024


def test_list_defaults_to_dry_run_json(store: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "list", "--store", str(store),
         "--archived", "--json"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    assert sorted(item["title"] for item in payload["threads"]) == ["archold", "otherpr"]
    assert payload["threads"][0]["state"] == "archived"
