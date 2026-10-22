"""Live-load contracts on a synthetic T3 store (only the columns fleet_load reads)."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "lib"))
from fleet_load import heavy, read_fleet

NOW = datetime.now(timezone.utc)
SCHEMA = """
CREATE TABLE orchestration_v2_projection_threads (thread_id TEXT PRIMARY KEY, updated_at TEXT,
  provider_instance_id TEXT, payload_json TEXT);
CREATE TABLE orchestration_v2_projection_runs (run_id TEXT PRIMARY KEY, thread_id TEXT, ordinal INTEGER,
  status TEXT, provider_instance_id TEXT, requested_at TEXT, completed_at TEXT, payload_json TEXT);
CREATE TABLE orchestration_v2_projection_messages (message_id TEXT PRIMARY KEY, thread_id TEXT, role TEXT,
  created_at TEXT, payload_json TEXT);
CREATE TABLE orchestration_v2_projection_subagents (subagent_id TEXT PRIMARY KEY, thread_id TEXT, run_id TEXT,
  child_thread_id TEXT, origin TEXT, status TEXT, provider_instance_id TEXT, started_at TEXT,
  updated_at TEXT, completed_at TEXT);
"""


def ago(minutes):
    return (NOW - timedelta(minutes=minutes)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    def __init__(self, path):
        self.path, self.db, self.n = path, sqlite3.connect(path), 0
        self.db.executescript(SCHEMA)

    def thread(self, tid, *, quiet=1, composer="composer", brief="Read and execute /tmp/brief.md"):
        self.db.execute("INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?,?)",
                        (tid, ago(quiet), composer, json.dumps({"modelSelection": {"instanceId": composer}})))
        self.message(tid, brief, minutes=60)

    def message(self, tid, text, minutes):
        self.n += 1
        self.db.execute("INSERT INTO orchestration_v2_projection_messages VALUES (?,?,?,?,?)",
                        (f"m{self.n}", tid, "user", ago(minutes), json.dumps({"text": text})))

    def run(self, tid, status, instance, ordinal=1, started=5, ended=None):
        run_id = f"run:{tid}:{ordinal}"
        payload = {"providerInstanceId": instance, "startedAt": None if status == "queued" else ago(started)}
        self.db.execute("INSERT INTO orchestration_v2_projection_runs VALUES (?,?,?,?,?,?,?,?)",
                        (run_id, tid, ordinal, status, instance, ago(started + 0.1),
                         ago(ended) if ended is not None else None, json.dumps(payload)))
        return run_id

    def native(self, parent, instance, run_id=None, status="running", active=1, started=10, ended=None):
        self.n += 1
        child = f"native-thread-{self.n}"
        self.db.execute("INSERT INTO orchestration_v2_projection_subagents VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (f"s{self.n}", parent, run_id, child, "provider_native", status, instance,
                         ago(started), ago(active), ago(ended) if ended is not None else None))
        return child

    def read(self):
        self.db.commit()
        return read_fleet(self.path, NOW)


def store(tmp_path):
    return Store(tmp_path / "statev2.sqlite")


def test_missing_or_unreadable_store_is_an_explicit_error(tmp_path):
    assert "not found" in read_fleet(tmp_path / "none.sqlite", NOW).error
    (tmp_path / "bad.sqlite").write_text("not a database")
    fleet = read_fleet(tmp_path / "bad.sqlite", NOW)
    assert "unreadable" in fleet.error and fleet.get("a").load == 0


def test_actual_run_instance_not_composer_and_queued_behind_counts_once(tmp_path):
    s = store(tmp_path)
    s.thread("t1", composer="a")
    s.run("t1", "running", "b")  # composer switched after the run started: the run's account counts
    s.run("t1", "queued", "a", ordinal=2)
    fleet = s.read()
    assert fleet.get("b").load == 1 and fleet.get("a").load == 0 and fleet.get("b").owners == 1


def test_queued_only_counts_unless_held_behind_a_failure(tmp_path):
    s = store(tmp_path)
    for tid, previous in (("ready", "completed"), ("held", "failed"), ("stopped", "interrupted")):
        s.thread(tid)
        s.run(tid, previous, "a", ended=3)
        s.run(tid, "queued", "a", ordinal=2)
    load = s.read().get("a")
    assert (load.load, load.queued, load.held) == (1, 1, 2)


def test_terminal_runs_excluded_recent_starts_diagnostic_only(tmp_path):
    s = store(tmp_path)
    for i, status in enumerate(("completed", "failed", "cancelled", "interrupted")):
        s.thread(f"t{i}")
        s.run(f"t{i}", status, "a", started=10, ended=2)
    s.thread("old")
    s.run("old", "running", "a", started=180)  # resumed long job: still counted
    load = s.read().get("a")
    assert load.load == 1 and load.recent_starts == 4 and len(load.ended) == 4


def test_quiet_running_job_still_counts_and_is_flagged(tmp_path):
    s = store(tmp_path)
    s.thread("silent", quiet=45)
    s.run("silent", "running", "a", started=60)
    load = s.read().get("a")
    assert (load.load, load.quiet) == (1, 1) and "quiet>20m" in load.summary()


def test_natives_group_with_owner_by_max_and_nesting(tmp_path):
    s = store(tmp_path)
    s.thread("owner")
    run = s.run("owner", "running", "a")
    child = s.native("owner", "a", run)
    s.native(child, "a")  # nested native: still the same owner's footprint
    s.native("owner", "a", run)
    s.native("owner", "a", run, status="completed", ended=1)  # terminal child ignored
    s.thread("solo")
    s.run("solo", "running", "a")
    load = s.read().get("a")
    assert (load.load, load.owners, load.natives) == (4, 2, 3)  # max(1, 3) + 1


def test_heavy_owner_is_not_a_subtree_multiplier(tmp_path):
    s = store(tmp_path)
    s.thread("builder", brief="Implement X.\n\nrouting-load: heavy\n")
    run = s.run("builder", "running", "a")
    s.native("builder", "a", run)
    assert s.read().get("a").load == 3  # max(3, 1), not 3 + 1 or 3 × 1
    for _ in range(4):
        s.native("builder", "a", run)
    load = s.read().get("a")
    assert (load.load, load.heavy) == (5, 1)


def test_delegate_task_child_counts_on_its_own_account(tmp_path):
    s = store(tmp_path)
    s.thread("lead")
    s.run("lead", "running", "a")
    s.thread("task-child")  # app-owned child: own runs, own account
    run = s.run("task-child", "running", "b")
    s.native("task-child", "b", run)
    s.native("task-child", "b", run)
    fleet = s.read()
    assert fleet.get("a").load == 1 and fleet.get("b").load == 2


def test_natives_after_owner_turn_ended_need_later_activity(tmp_path):
    s = store(tmp_path)
    s.thread("bg")
    spawn = s.run("bg", "completed", "a", started=30, ended=10)
    s.native("bg", "a", spawn, active=2)       # background work after the turn ended: live
    s.native("bg", "a", spawn, active=12)      # stale projection: orphan, not counted
    s.run("bg", "completed", "a", ordinal=2, started=4, ended=3)  # later short owner turn
    s.native("bg", "a", spawn, active=5)       # active after its own run ended: still live
    load = s.read().get("a")
    assert (load.load, load.natives, load.orphans) == (2, 2, 1)


def test_heavy_marker_only_exact_unquoted_line_in_first_message(tmp_path):
    assert heavy("Build it.\n  Routing-Load: heavy  \n")
    assert not heavy("Mention routing-load: heavy inline")
    assert not heavy("> routing-load: heavy")
    assert not heavy("Quoted brief:\n```\nrouting-load: heavy\n```\n")
    assert not heavy(None)
    s = store(tmp_path)
    s.thread("later")
    s.message("later", "routing-load: heavy", minutes=1)  # a later user message never upgrades
    s.run("later", "running", "a")
    assert s.read().get("a").load == 1


def test_stale_native_is_not_revived_by_a_later_unrelated_owner_run(tmp_path):
    s = store(tmp_path)
    s.thread("owner")
    spawn = s.run("owner", "completed", "a", started=30, ended=10)
    s.native("owner", "a", spawn, active=12)  # stale: no activity after its run ended
    s.run("owner", "running", "b", ordinal=2)  # new owner turn on another account
    fleet = s.read()
    assert (fleet.get("a").load, fleet.get("a").orphans, fleet.get("b").load) == (0, 1, 1)


def test_nested_native_without_run_id_inherits_its_ancestors_spawning_run(tmp_path):
    s = store(tmp_path)
    s.thread("owner")
    spawn = s.run("owner", "completed", "a", started=30, ended=10)
    child = s.native("owner", "a", spawn, active=5)
    s.native(child, "a", active=5)  # nested, no run_id: background after its ancestor's run
    assert s.read().get("a").load == 2
    s.run("owner", "completed", "a", ordinal=2, started=4, ended=3)  # later short owner turn
    load = s.read().get("a")
    assert (load.load, load.orphans) == (2, 0)
    s.native("ghost-parent", "a", active=1)  # no spawning run anywhere: unverifiable
    assert s.read().get("a").orphans == 1


def test_malformed_store_values(tmp_path):
    s = store(tmp_path)
    s.thread("typed", brief=42)  # valid JSON, wrong type: not heavy, no crash
    s.run("typed", "running", "a")
    s.db.execute("UPDATE orchestration_v2_projection_runs SET payload_json = '{\"startedAt\": 7}'")
    assert s.read().get("a").load == 1
    s.db.execute("UPDATE orchestration_v2_projection_messages SET payload_json = '{broken'")
    fleet = s.read()
    assert "unreadable" in fleet.error and "malformed JSON" in fleet.error  # explicit quota-only fallback
