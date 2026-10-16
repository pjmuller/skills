"""t3-my-prompts against a synthetic statev2 store: authorship filtering, compaction, budget.

  uv run --with pytest pytest test_t3_my_prompts.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from v2_fixture import Store

SCRIPT = Path(__file__).with_name("t3-my-prompts")


@pytest.fixture
def store(tmp_path: Path) -> Path:
    s = Store(tmp_path / "statev2.sqlite")
    s.thread("live", "Live")
    s.message("live", "user", "the user request\n````python\n```\nCODE SECRET\n````\nkeep this", 9)
    s.message("live", "user", "[from thread x] MANUAL-THREAD AGENT SECRET", 8, by="agent", sender="w")
    for i in range(20):
        s.message("live", "user", "long the user text " + "x" * 300, 7 - i * 0.01)
    s.thread("launched", "Worker")
    s.message("launched", "user", "brief AGENT SECRET", 9, by="agent", sender="live")
    s.message("launched", "user", "user-looking follow-up inside worker thread", 8)
    s.thread("legacy", "🏓 old worker")  # imported 0.0.x history: author unknown
    s.message("legacy", "user", "LEGACY WORKER SECRET", 9)
    s.thread("sub", "Explore", parent="live")
    s.message("sub", "user", "SUBAGENT SECRET", 9, by="agent")
    s.thread("gone", "Deleted secret", deleted=True)
    s.message("gone", "user", "DELETED SECRET", 9)
    return s.close()


def run(store: Path, *args: str) -> str:
    return subprocess.run(
        [str(SCRIPT), "--store", str(store), "--days", "1", *args],
        text=True, capture_output=True, check=True,
    ).stdout


def test_agent_rows_filtered(store: Path) -> None:
    output = run(store, "--budget", "20000")
    for secret in ("AGENT SECRET", "user-looking follow-up", "LEGACY WORKER", "SUBAGENT SECRET"):
        assert secret not in output
    assert "agent author 1" in output and "ping-pong title 1" in output
    assert "1 ping row(s) inside manual threads" in output


def test_code_block_stripped(store: Path) -> None:
    output = run(store, "--budget", "20000")
    assert "[code " in output and "keep this" in output
    assert "CODE SECRET" not in output


def test_budget_is_hard_cap(store: Path) -> None:
    output = run(store, "--budget", "700")
    assert len(output) <= 700
    assert "budget dropped" in output


def test_deleted_thread_excluded(store: Path) -> None:
    output = run(store, "--budget", "20000")
    assert "DELETED SECRET" not in output
    assert "1 deleted-thread row" in output
