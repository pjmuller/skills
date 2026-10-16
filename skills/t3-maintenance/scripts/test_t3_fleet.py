"""t3-fleet against a synthetic statev2 store: kinds, lineage, stalled tasks, filters.

  uv run --with pytest pytest test_t3_fleet.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from v2_fixture import Store

SCRIPT = Path(__file__).with_name("t3-fleet")
PARENT = "aaaaaaaa-0000-0000-0000-00000000aaaa"
LAUNCHED = "mcp:bbbbbbbb-0000-0000-0000-00000000bbbb"
STUCK = "thread:delegated-task:command%3Amcp%3Ax%3Adelegate-task%3Astuck"
DONE = "thread:delegated-task:command%3Amcp%3Ax%3Adelegate-task%3Adone"
SUB = "thread:provider:claudeAgent:native-thread:sub"


@pytest.fixture
def store(tmp_path: Path) -> Path:
    s = Store(tmp_path / "statev2.sqlite")
    s.thread(PARENT, "Orchestrator", run="running")
    s.message(PARENT, "user", "kick off", 300)
    s.thread(LAUNCHED, "📤 side quest", minutes=30, run="completed")
    s.message(LAUNCHED, "user", "brief", 200, by="agent", sender=PARENT)
    s.message(LAUNCHED, "assistant", "launched summary", 30)
    s.thread(STUCK, "Stuck review", parent=PARENT, minutes=40, run="completed")
    s.task(PARENT, STUCK, "running")
    s.thread(DONE, "Done review", parent=PARENT, minutes=40, run="completed")
    s.task(PARENT, DONE, "completed", "acknowledged")
    s.thread(SUB, "Explore", parent=PARENT, minutes=5)
    s.task(PARENT, SUB, "running", origin="provider_native")
    s.thread("cccccccc-0000-0000-0000-00000000cccc", "elsewhere", project="q", minutes=90)
    s.thread("dddddddd-0000-0000-0000-00000000dddd", "old settled", settled=True, minutes=60 * 96)
    s.thread("eeeeeeee-0000-0000-0000-00000000eeee", "trashed", deleted=True)
    return s.close()


def run(store: Path, *args: str) -> list[dict]:
    out = subprocess.run(
        [str(SCRIPT), "--store", str(store), "list", "--json", *args],
        text=True, capture_output=True, check=True,
    ).stdout
    return json.loads(out)


def titles(rows: list[dict]) -> set[str]:
    return {row["title"] for row in rows}


def test_default_hides_subagents_and_deleted(store: Path) -> None:
    assert titles(run(store)) == {"Orchestrator", "📤 side quest", "elsewhere", "old settled"}


def test_kinds_parent_and_git_leftovers_shape(store: Path) -> None:
    rows = {row["title"]: row for row in run(store, "--subagents")}
    assert rows["📤 side quest"]["kind"] == "launched"
    assert rows["📤 side quest"]["parent_id"] == PARENT
    assert rows["📤 side quest"]["short_id"] == "bbbbbbbb"
    assert rows["Stuck review"]["kind"] == "task"
    assert rows["Explore"]["kind"] == "subagent"
    assert rows["Orchestrator"]["session_status"] == "running"
    assert rows["📤 side quest"]["session_status"] == "idle"
    assert rows["📤 side quest"]["last_text"] == "launched summary"
    for key in ("thread_id", "workspace_root", "settled", "deleted", "archived"):
        assert key in rows["Orchestrator"]


def test_stalled_only_stuck_tasks(store: Path) -> None:
    rows = run(store, "--stalled")
    assert [(r["title"], r["stall_state"]) for r in rows] == [("Stuck review", "stuck")]


def test_parent_by_short_id(store: Path) -> None:
    assert titles(run(store, "--parent", "aaaaaaaa")) == {
        "📤 side quest", "Stuck review", "Done review", "Explore"
    }


def test_filters(store: Path) -> None:
    assert titles(run(store, "--project", "other")) == {"elsewhere"}
    assert titles(run(store, "--recent", "4h")) == {"📤 side quest", "elsewhere"}
    assert titles(run(store, "--older-than", "3d")) == {"old settled"}
    assert titles(run(store, "--settled")) == {"old settled"}
    assert titles(run(store, "--title-prefix", "📤")) == {"📤 side quest"}
    assert "trashed" in titles(run(store, "--all"))
