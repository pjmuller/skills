"""t3-retro-prep against a synthetic statev2 store: which threads it flags, and what it never flags.

  uv run --with pytest pytest test_t3_retro_prep.py
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from v2_fixture import Store

SCRIPT = Path(__file__).with_name("t3-retro-prep")
EPERM = "Caused by: failed to open file `/Users/x/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)"


def fail(s: Store, tid: str, minutes: float, output: str = EPERM, cmd: str = "uv run tool.py") -> None:
    s.item(tid, "command_execution", {"input": {"command": cmd}, "output": output, "exitCode": 2}, minutes, status="failed")


@pytest.fixture
def store(tmp_path: Path) -> Path:
    s = Store(tmp_path / "statev2.sqlite")
    # silent omission: a failure, then "done" with no word about it
    s.thread("silent", "Silent")
    s.message("silent", "user", "Build the export and run its tests.", 60)
    fail(s, "silent", 59)
    s.message("silent", "assistant", "Done ✅ the export is built.", 58)
    # recovered failure: the answer says what happened
    s.thread("recovered", "Recovered")
    s.message("recovered", "user", "Install the helper.", 60)
    fail(s, "recovered", 59)
    s.message("recovered", "assistant", "The uv cache was not permitted, so I used a local cache instead. Done.", 58)
    # same error in a third thread, inside a sub-agent: recurring, but the sub-agent reports to its lead
    s.thread("lead", "Lead")
    s.message("lead", "user", "Investigate the cache.", 60)
    s.thread("child", "Explore", parent="lead")
    fail(s, "child", 59)
    s.message("lead", "assistant", "Investigated: the cache lives in your home folder.", 58)
    # correction after a done-claim vs a legitimate follow-up
    s.thread("corrected", "Corrected")
    s.message("corrected", "user", "Build all dashboard screens.", 60)
    s.message("corrected", "assistant", "All screens built ✅", 50)
    s.message("corrected", "user", "No, the billing screen is missing.", 40)
    s.thread("followup", "Follow-up")
    s.message("followup", "user", "Build the settings screen.", 60)
    s.message("followup", "assistant", "Done, the settings screen is live.", 50)
    s.message("followup", "user", "Great, now add a logout link too.", 40)
    # unasked extras: only counts when files changed
    s.thread("extras", "Extras")
    s.message("extras", "user", "Fix the typo in the header.", 60)
    s.item("extras", "file_change", {"fileName": "header.tmpl"}, 55)
    s.message("extras", "assistant", "Fixed. I also refactored the nav helper while I was there.", 50)
    # an empty search is not friction
    s.thread("benign", "Benign")
    s.message("benign", "user", "Find the config.", 60)
    fail(s, "benign", 59, output="", cmd="grep -r foo .")
    s.message("benign", "assistant", "No config found; nothing to change.", 58)
    # agent-written brief + secret; the user's own reply is kept, the brief is not typed
    s.thread("brief", "Worker")
    s.message("brief", "user", "Read and execute /tmp/brief.md API_TOKEN=sk-live-abcdefghijklmnopqrstuvwx1234", 60, by="agent", sender="x")
    s.message("brief", "assistant", "Done.", 55)
    s.message("brief", "user", "you have my green light to merge", 50)
    for tid in ("silent", "recovered", "corrected"):
        s.message(tid, "user", "ok you have my green light to merge", 30)
    return s.close()


def prep(store: Path, tmp_path: Path) -> tuple[str, dict]:
    out = tmp_path / "out"
    env = {**os.environ, "T3_RETRO_STATE": str(tmp_path / "state"), "T3_ARCHIVE": str(tmp_path / "none.sqlite")}
    subprocess.run([str(SCRIPT), "--store", str(store), "--days", "1", "--out", str(out)],
                   check=True, capture_output=True, text=True, env=env)
    selection = json.loads((out / "selection.json").read_text())
    return (out / "packets.md").read_text(), {t["id"]: t for t in selection["threads"]}


def test_signals(store: Path, tmp_path: Path) -> None:
    _, picked = prep(store, tmp_path)
    assert picked["silent"]["signals"].get("silent-failure") == 1
    assert "silent-failure" not in picked["recovered"]["signals"]
    assert picked["recovered"]["signals"].get("fallback-then-done") == 1
    assert "silent-failure" not in picked["lead"]["signals"]  # sub-agent failure
    assert picked["lead"]["signals"].get("recurring-error") == 1
    assert picked["corrected"]["signals"].get("correction-after-done") == 1
    assert "correction-after-done" not in picked["followup"]["signals"]
    assert picked["extras"]["signals"].get("unasked-extras") == 1
    assert not picked["benign"]["signals"]


def test_packets(store: Path, tmp_path: Path) -> None:
    packets, _ = prep(store, tmp_path)
    assert "3 threads · `Caused by: failed to open file <q>: Operation not permitted (os error <n>)`" in packets
    assert '4 threads · "have my green light to merge"' in packets  # typed in 4 threads, overlaps folded
    assert "sk-live-" not in packets and "[redacted:" in packets
    assert "**Opening (agent-written brief)**" in packets
    assert "Previous report: none (first run)" in packets


def test_selection_is_reproducible(store: Path, tmp_path: Path) -> None:
    env = {**os.environ, "T3_RETRO_STATE": str(tmp_path / "state"), "T3_ARCHIVE": str(tmp_path / "none.sqlite")}
    runs = []
    for name in ("a", "b"):
        subprocess.run([str(SCRIPT), "--store", str(store), "--until", "2100-01-01", "--days", "36600",
                        "--out", str(tmp_path / name)], check=True, capture_output=True, env=env)
        runs.append([t["id"] for t in json.loads((tmp_path / name / "selection.json").read_text())["threads"]])
    assert runs[0] == runs[1] and len(runs[0]) == 8


def test_quiet_week_fills_slots_across_projects(tmp_path: Path) -> None:
    s = Store(tmp_path / "statev2.sqlite")
    for i in range(24):  # no signals anywhere; 20 threads in one project, 4 in another
        tid = f"t{i:02d}"
        s.thread(tid, tid, project="p" if i < 20 else "q")
        s.message(tid, "user", f"Plain ask number {i}.", 60)
        s.message(tid, "assistant", "Here you go.", 50)
    _, picked = prep(s.close(), tmp_path)
    assert len(picked) == 12
    assert sum(1 for t in picked if t in {"t20", "t21", "t22", "t23"}) == 4


def test_lookback_keeps_human_authorship(tmp_path: Path) -> None:
    s = Store(tmp_path / "statev2.sqlite")
    s.thread("old", "Old ask")
    s.message("old", "user", "Build the export, my own words.", 36 * 60)
    s.message("old", "assistant", "Done ✅", 30 * 60)
    s.message("old", "user", "No, the CSV is missing.", 60)
    s.message("old", "assistant", "Added the CSV.", 50)
    packets, picked = prep(s.close(), tmp_path)
    assert "**Opening (typed)**: Build the export" in packets
    assert picked["old"]["signals"].get("correction-after-done") == 1
