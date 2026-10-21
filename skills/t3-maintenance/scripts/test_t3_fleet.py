"""t3-fleet against a synthetic statev2 store: kinds, lineage, stalled tasks, filters.

  uv run --with pytest pytest test_t3_fleet.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from v2_fixture import Store, ago

SCRIPT = Path(__file__).with_name("t3-fleet")
PARENT = "aaaaaaaa-0000-0000-0000-00000000aaaa"
LAUNCHED = "mcp:bbbbbbbb-0000-0000-0000-00000000bbbb"
STUCK = "thread:delegated-task:command%3Amcp%3Ax%3Adelegate-task%3Astuck"
DONE = "thread:delegated-task:command%3Amcp%3Ax%3Adelegate-task%3Adone"
SUB = "thread:provider:claudeAgent:native-thread:sub"
CLAIMED = "thread:delegated-task:command%3Amcp%3Ax%3Adelegate-task%3Aclaimed"
DELIVERED = "thread:delegated-task:command%3Amcp%3Ax%3Adelegate-task%3Adelivered"


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
    s.thread(CLAIMED, "Claimed review", parent=PARENT, minutes=40, run="completed")
    s.task(PARENT, CLAIMED, "completed", "claimed")
    s.thread(DELIVERED, "Delivered review", parent=PARENT, minutes=40, run="completed")
    s.task(PARENT, DELIVERED, "completed", "delivered")
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


def test_stalled_stuck_and_claimed_but_never_delivered(store: Path) -> None:
    rows = run(store, "--stalled")
    assert {(r["title"], r["stall_state"]) for r in rows} == {
        ("Stuck review", "stuck"), ("Claimed review", "undelivered")
    }  # acknowledged / delivered are terminal


def test_parent_by_short_id(store: Path) -> None:
    assert titles(run(store, "--parent", "aaaaaaaa")) == {
        "📤 side quest", "Stuck review", "Done review", "Claimed review", "Delivered review", "Explore"
    }


def test_filters(store: Path) -> None:
    assert titles(run(store, "--project", "other")) == {"elsewhere"}
    assert titles(run(store, "--recent", "4h")) == {"📤 side quest", "elsewhere"}
    assert titles(run(store, "--older-than", "3d")) == {"old settled"}
    assert titles(run(store, "--settled")) == {"old settled"}
    assert titles(run(store, "--title-prefix", "📤")) == {"📤 side quest"}
    assert "trashed" in titles(run(store, "--all"))


def limited_run(s: Store, tid: str, *, settled: bool = False, reset: bool = True) -> str:
    s.thread(tid, tid, settled=settled)
    rid = s.run(tid, "failed", minutes=30)
    failure = {"class": "usage_limit", "resetAt": ago(-60) if reset else None}
    s.db.execute("""INSERT INTO orchestration_v2_projection_turn_items
        (turn_item_id, thread_id, type, status, updated_at, payload_json, run_id, node_id, ordinal)
        VALUES (?,?,'error','failed',?,?,?,?,1)""",
        (f"error:{tid}", tid, ago(30), json.dumps({"failure": failure}), rid, f"root:{tid}"))
    return rid


def test_latest_queued_does_not_mask_failed_executed_run(tmp_path: Path) -> None:
    s = Store(tmp_path / "store.sqlite")
    rid = limited_run(s, "held")
    s.run("held", "queued", ordinal=2, started=False)
    s.run("held", "cancelled", ordinal=3, started=False)
    row, = run(s.close(), "--limited")
    assert row["run_status"] == "cancelled"  # Existing highest-ordinal field stays compatible.
    assert row["latest_executed_run_id"] == rid
    assert row["limit"] == {
        "status": "actionable", "actionable": True, "confidence": "high",
        "source": "root_error.failure.class", "run_id": rid, "limited_at": ago(30),
        "reset_at": ago(-60), "reset_status": "waiting",
    }


def test_stale_limit_metadata_and_later_recovery_not_current(tmp_path: Path) -> None:
    s = Store(tmp_path / "store.sqlite")
    limited_run(s, "settled", settled=True)
    s.thread("completed", "completed", run="completed")
    for tid in ("recovered", "active", "out_of_order"):
        limited_run(s, tid)
        s.run(tid, "running" if tid == "active" else "completed", ordinal=2, minutes=5)
    # End time beats submission ordinal: an earlier queued continuation ran later.
    s.run("out_of_order", "completed", ordinal=0, minutes=1)
    for tid in ("settled", "completed", "recovered", "active"):
        s.db.execute("""UPDATE orchestration_v2_projection_threads SET payload_json =
            json_set(payload_json, '$.limitRecovery', json(?)) WHERE thread_id = ?""",
            (json.dumps({"runId": f"run:{tid}:1", "resetAt": ago(-60), "autoResume": True}), tid))
    assert run(s.close(), "--limited") == []


def test_terminal_limit_text_despite_completed_status_is_only_suspected(tmp_path: Path) -> None:
    s = Store(tmp_path / "store.sqlite")
    s.thread("terminal", "terminal", run="completed", minutes=20)
    s.message("terminal", "assistant", "You've hit your session limit · resets later", 20)
    s.db.execute("UPDATE orchestration_v2_projection_messages SET run_id = 'run:terminal:1'")
    s.thread("old_text", "old_text")
    s.run("old_text", "completed", minutes=20)
    s.message("old_text", "assistant", "You've hit your limit", 20)
    s.run("old_text", "completed", ordinal=2, minutes=5)
    row, = run(s.close(), "--limited")
    assert row["title"] == "terminal"
    assert row["limit"]["status"] == "suspected"
    assert row["limit"]["actionable"] is False
    assert row["limit"]["source"] == "terminal_assistant_text"


def test_limited_includes_tasks_native_children_and_root_errors_only(tmp_path: Path) -> None:
    s = Store(tmp_path / "store.sqlite")
    s.thread(PARENT, "parent", run="completed", minutes=5)
    for tid, origin in ((STUCK, "app_owned"), (SUB, "provider_native")):
        limited_run(s, tid, reset=False)
        s.task(PARENT, tid, "running", origin=origin)
    limited_run(s, "nested_error")
    s.db.execute("UPDATE orchestration_v2_projection_turn_items SET node_id = 'nested' WHERE thread_id = 'nested_error'")
    rows = {r["thread_id"]: r for r in run(s.close(), "--limited")}
    assert set(rows) == {STUCK, SUB}
    assert rows[SUB]["parent_id"] == PARENT
    assert rows[SUB]["parent_evidence"]["source"] == "projection_subagents"
    assert rows[SUB]["limit"]["reset_status"] == "unknown"
    assert rows[SUB]["limit"]["status"] == "review_needed"
    assert rows[SUB]["limit"]["actionable"] is False
    assert rows[SUB]["limit"]["recovery_owner_id"] == PARENT
    assert rows[STUCK]["limit"]["actionable"] is False
    assert rows[STUCK]["limit"]["status"] == "review_needed"
    assert rows[STUCK]["limit"]["recovery_owner_id"] == PARENT


@pytest.mark.parametrize("wrapped", [True, False])
def test_lineage_corroborates_first_selection_without_fabricating_parent(tmp_path: Path, wrapped: bool) -> None:
    s = Store(tmp_path / "store.sqlite")
    s.thread(PARENT, "parent")
    selection = {"instanceId": "test-instance", "model": "test-model", "options": [{"id": "effort", "value": "high"}]}
    for tid in (LAUNCHED, "no_sender"):
        s.thread(tid, tid)
        s.message(tid, "user", "agent brief", 10, by="agent", sender=PARENT if tid == LAUNCHED else None)
        s.run(tid, "completed", selection=selection)
        s.db.execute("""UPDATE orchestration_v2_projection_threads SET payload_json =
            json_set(payload_json, '$.modelSelection', json(?)) WHERE thread_id = ?""", (json.dumps(selection), tid))
    output = {"threadId": LAUNCHED, "modelSelection": selection}
    s.item(PARENT, "dynamic_tool", {
        "toolName": "t3-code.t3_thread_launch", "input": {"modelSelection": selection},
        "output": {"structuredContent": output} if wrapped else output,
    }, 11)
    path = s.close()
    rows = {r["thread_id"]: r for r in run(path, "--lineage")}
    assert rows[LAUNCHED]["first_run_selection"] == selection
    assert rows[LAUNCHED]["options"] == selection["options"]
    assert rows[LAUNCHED]["parent_evidence"]["corroboration"]["model"] == "test-model"
    assert rows[LAUNCHED]["parent_evidence"]["corroboration"]["options"] == selection["options"]
    assert rows[LAUNCHED]["parent_evidence"]["corroboration"]["requested_target"] == selection
    assert rows["no_sender"]["parent_id"] is None
    assert rows["no_sender"]["parent_evidence"]["confidence"] == "unknown"
    assert titles(run(path, "--descendants", "aaaaaaaa")) == {LAUNCHED}


@pytest.mark.parametrize("role,text", [
    ("user", 'Error: HTTP429 {"error":{"type":"rate_limit","message":"Rate limit reached"}}'),
    ("system", 'Error: {"type":"rate_limit","message":"Request rejected"}'),
    ("assistant", "You've hit your session limit · resets later"),
])
def test_runless_failed_native_child_needs_owner_review(tmp_path: Path, role: str, text: str) -> None:
    s = Store(tmp_path / "store.sqlite")
    s.thread(PARENT, "recovery owner", run="completed", minutes=5)
    s.thread(SUB, "native child")  # Provider-native children have messages, no app-owned runs.
    s.task(PARENT, SUB, "failed", origin="provider_native")
    s.message(SUB, role, text, 30)
    s.thread("ordinary", "ordinary")
    s.message("ordinary", role, text, 30)  # Text alone cannot manufacture a native failure.
    row, = run(s.close(), "--limited")
    assert row["parent_id"] == PARENT
    assert row["latest_executed_run_id"] is None
    assert row["limit"]["status"] == "review_needed"
    assert row["limit"]["actionable"] is False
    assert row["limit"]["recovery_owner_id"] == PARENT
    assert row["limit"]["source"] == "native_failed_child_text"


def test_json_truncation_warns_and_limited_defaults_unbounded(tmp_path: Path) -> None:
    s = Store(tmp_path / "store.sqlite")
    for n in range(51):
        limited_run(s, f"limited-{n}")
    path = s.close()
    assert len(run(path, "--limited")) == 51
    assert len(run(path, "--lineage")) == 51
    result = subprocess.run([str(SCRIPT), "--store", str(path), "list", "--json", "--limit", "1"],
                            text=True, capture_output=True, check=True)
    assert len(json.loads(result.stdout)) == 1
    assert "WARNING: truncated: showing 1 of 51" in result.stderr
