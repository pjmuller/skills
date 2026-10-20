"""t3-relay: argument guard, footer source, and the exact MCP instruction it posts (no live T3)."""
import json
import sqlite3
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "t3-relay"
relay = SourceFileLoader("t3_relay", str(SCRIPT)).load_module()


def test_effort_without_model_or_instance_is_refused():
    out = subprocess.run([str(SCRIPT), "launch", "--project", "/tmp", "--title", "x", "--effort", "high", "--", "hi"],
                         capture_output=True, text=True)
    assert out.returncode == 2 and "needs --model or --instance" in out.stderr


def test_footer_comes_from_settle_thread_md():
    footer = relay.completion_footer()
    assert footer.startswith("---\nConditional self-settlement") and '"action":"settle"' in footer


@pytest.fixture
def posted(monkeypatch, tmp_path):
    sent = {}
    monkeypatch.setattr(relay, "REQUESTS", tmp_path)
    monkeypatch.setattr(relay, "store", lambda: None)
    monkeypatch.setattr(relay, "pick_host", lambda con, via=None: relay.Host("task", "tok", "mcp:host", "i", "m"))
    monkeypatch.setattr(relay, "origin", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(relay, "project_id", lambda con, path: "proj-1")
    monkeypatch.setattr(relay, "pick", lambda models, instance=None: ("codex_a", "gpt-6.1-sol", "high"))
    monkeypatch.setattr(relay, "post", lambda base, tid, tok, body: sent.update(body) or "d1")

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["t3-relay", *argv])
        relay.main()
        head, payload = sent["instruction"].split("\n", 1)
        sent["record"] = json.loads((tmp_path / f"{sent['id']}.json").read_text())
        return head, json.loads(payload)
    run.sent = sent
    return run


def test_launch_instruction(posted):
    head, args = posted("launch", "--project", "/r", "--title", "⏰ T", "--model", "sol", "--settle-when-done", "--", "Read", "x.md")
    assert head == "Call t3_thread_launch once with exactly these arguments:"
    assert args["projectId"] == "proj-1" and args["title"] == "⏰ T"
    assert args["modelSelection"] == {"instanceId": "codex_a", "model": "gpt-6.1-sol",
                                      "options": [{"id": "reasoningEffort", "value": "high"}]}
    assert args["message"].startswith("Read x.md\n\n---\nConditional self-settlement")


def test_send_instruction_is_idempotent_per_request(posted):
    head, args = posted("send", "--thread", "mcp:abc", "--", 'quote " and {{body.x}}')
    assert head == "Call t3_thread_send once with exactly these arguments:"
    assert args["threadId"] == "mcp:abc" and args["message"] == 'quote " and {{body.x}}'
    assert args["clientRequestId"].startswith("relay-") and args["mode"] == "auto"


def db():
    con = sqlite3.connect(":memory:")
    con.executescript("""
      create table scheduled_tasks (task_id, title, enabled, schedule_json, webhook_token, thread_id,
                                    model_selection_json, created_at);
      create table orchestration_v2_projection_threads (thread_id, project_id, title, created_at, deleted_at);
      create table orchestration_v2_projection_runs (run_id, thread_id, ordinal, status, requested_at, completed_at);
      create table orchestration_v2_projection_messages (message_id, thread_id, run_id, role, created_at, payload_json);
      create table scheduled_task_webhook_deliveries (delivery_id, outcome, error);
    """)
    return con


def add_host(con, task, thread, instance="claudeAgent_x", created="1"):
    con.execute("insert into scheduled_tasks values (?, ?, 1, '{\"type\":\"webhook\"}', 'tok', ?, ?, ?)",
                (task, relay.RELAY_TITLE, thread, json.dumps({"instanceId": instance, "model": "claude-haiku-5-5"}), created))
    if thread:
        con.execute("insert into orchestration_v2_projection_threads values (?, 'p', 'host', '0', null)", (thread,))


AT = relay.datetime(2026, 10, 19, 12, 0, tzinfo=relay.timezone.utc)


@pytest.mark.parametrize("run, problem", [
    (None, None),
    (("completed", "2026-10-19T11:00:00.000Z", "2026-10-19T11:00:10.000Z"), None),
    (("running", "2026-10-19T11:58:00.000Z", None), None),                       # a normal in-flight turn
    (("waiting", "2026-10-19T11:30:00.000Z", None), "busy since"),               # limited / hung
    (("failed", "2026-10-19T11:00:00.000Z", "2026-10-19T11:30:00.000Z"), "failed at"),
    (("failed", "2026-10-19T09:00:00.000Z", "2026-10-19T09:00:05.000Z"), None),  # cooled down
])
def test_host_health(run, problem):
    con = db()
    add_host(con, "t", "mcp:host")
    if run:
        con.execute("insert into orchestration_v2_projection_runs values ('r', 'mcp:host', 1, ?, ?, ?)", run)
    (h,) = relay.hosts(con, AT)
    assert (h.problem is None) if problem is None else (problem in h.problem)


def test_unbound_and_deleted_hosts():
    con = db()
    add_host(con, "unbound", None, created="1")
    add_host(con, "gone", "mcp:gone", created="2")
    con.execute("update orchestration_v2_projection_threads set deleted_at = 'x'")
    unbound, gone = relay.hosts(con, AT)
    assert "not bound" in unbound.warning and unbound.problem is None and "deleted" in gone.problem


def test_pick_host_fails_over_on_capacity(monkeypatch):
    con = db()
    add_host(con, "claude", "mcp:a", "claudeAgent_x", "1")
    add_host(con, "codex", "mcp:b", "codex_y", "2")
    monkeypatch.setattr(relay, "capacity_problem", lambda h: "session exhausted" if h.instance == "claudeAgent_x" else None)
    assert relay.pick_host(con).task_id == "codex"
    assert relay.pick_host(con, via="codex_y").task_id == "codex"
    monkeypatch.setattr(relay, "capacity_problem", lambda h: "exhausted")
    with pytest.raises(SystemExit):
        relay.pick_host(con)


def request(con, kind="launch", rid="r1"):
    rec = {"rid": rid, "kind": kind, "host": "mcp:host", "posted_at": "2026-10-19T12:00:00.000Z", "delivery": "d1",
           "project_id": "p", "title": "⏰ job", "thread": "mcp:target"}
    return lambda: relay.request_status(con, rec)


def host_turn(con, status, reply=None, rid="r1"):
    con.execute("insert into orchestration_v2_projection_runs values ('run', 'mcp:host', 2, ?, '2026-10-19T12:00:01.000Z', null)", (status,))
    con.execute("insert into orchestration_v2_projection_messages values ('m', 'mcp:host', 'run', 'user', '2026-10-19T12:00:01.000Z', ?)",
                (json.dumps({"text": f"T3 relay request {rid}, sent by a local script"}),))
    if reply:
        con.execute("insert into orchestration_v2_projection_messages values ('a', 'mcp:host', 'run', 'assistant', '2026-10-19T12:00:05.000Z', ?)",
                    (json.dumps({"text": reply}),))


def test_status_launch_pending_ok_by_effect_not_reply():
    con = db()
    status = request(con)
    assert status()[0] == "pending"                                       # not yet delivered
    host_turn(con, "running")
    assert status() == ("pending", "host turn running")
    con.execute("update orchestration_v2_projection_runs set status = 'completed'")
    con.execute("insert into orchestration_v2_projection_threads values ('mcp:new', 'p', '⏰ job', '2026-10-19T12:00:04.000Z', null)")
    assert status() == ("ok", "mcp:new")                                  # whatever the host replied


def test_status_ignores_older_thread_with_same_title():
    con = db()
    con.execute("insert into orchestration_v2_projection_threads values ('mcp:old', 'p', '⏰ job', '2026-10-19T11:00:00.000Z', null)")
    host_turn(con, "completed", "relay r1: FAILED boom")
    state, detail = request(con)()
    assert state == "failed" and "FAILED boom" in detail


def test_status_send_matches_client_request_id():
    con = db()
    status = request(con, "send")
    con.execute("insert into orchestration_v2_projection_messages values "
                "('message:mcp:x:thread-send:relay-r1', 'mcp:target', 'rt', 'user', '2026-10-19T12:00:03.000Z', '{}')")
    assert status() == ("ok", "mcp:target")


def test_status_rejected_delivery_fails():
    con = db()
    con.execute("insert into scheduled_task_webhook_deliveries values ('d1', 'skipped', 'task paused')")
    assert request(con)()[0] == "failed"


def test_launch_records_request(posted):
    posted("launch", "--project", "/r", "--title", "⏰ T", "--model", "sol", "--", "go")
    rec = posted.sent["record"]
    assert rec["kind"] == "launch" and rec["title"] == "⏰ T" and rec["project_id"] == "proj-1"
    assert rec["host"] == "mcp:host" and rec["delivery"] == "d1" and rec["posted_at"].endswith("Z")


def test_status_unbound_host_finds_turn_in_any_thread():
    """Sol review P2: an unbound host runs each request in a fresh thread; record host is None."""
    con = db()
    con.execute("insert into orchestration_v2_projection_runs values ('run', 'mcp:fresh', 1, 'failed', '2026-10-19T12:00:01.000Z', null)")
    con.execute("insert into orchestration_v2_projection_messages values ('m', 'mcp:fresh', 'run', 'user', '2026-10-19T12:00:01.000Z', ?)",
                (json.dumps({"text": "T3 relay request r1, sent by a local script"}),))
    rec = {"rid": "r1", "kind": "launch", "host": None, "posted_at": "2026-10-19T12:00:00.000Z", "delivery": "d1",
           "project_id": "p", "title": "⏰ job"}
    assert relay.request_status(con, rec)[0] == "failed"


def test_lookup_error_is_pending_not_failed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(relay, "REQUESTS", tmp_path)
    (tmp_path / "r1.json").write_text(json.dumps({"rid": "r1"}))
    def locked():
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(relay, "store", locked)
    assert relay.wait_for("r1", 0) == 3 and capsys.readouterr().out.startswith("pending lookup error")


@pytest.mark.parametrize("flags, expected", [
    ([], ("opus", "astra")),
    (["--model", "openai"], ("openai",)),
    (["--model", "codex"], ("codex",)),
    (["--instance", "codex_test"], ("codex",)),
    (["--instance", "claude_test"], ("claude",)),
    (["--instance", "codex_test", "--model", "sol"], ("sol",)),
    (["--model", "gpt-6.1-sol"], ("gpt-6.1-sol",)),
])
def test_launch_defaults_and_explicit_choices(posted, monkeypatch, tmp_path, flags, expected):
    monkeypatch.setattr(relay, "HOME", tmp_path)
    (tmp_path / "settings.json").write_text(json.dumps({"providerInstances": {
        "codex_test": {"driver": "codex"}, "claude_test": {"driver": "claudeAgent"}}}))
    selected = []
    def pick(models, instance=None):
        selected.append((models, instance))
        return instance or "codex_a", "gpt-6-astra", "medium"
    monkeypatch.setattr(relay, "pick", pick)
    _, args = posted("launch", "--project", "/r", "--title", "x", *flags, "--", "task")
    instance = flags[flags.index("--instance") + 1] if "--instance" in flags else None
    assert selected == [(expected, instance)]
    assert args["modelSelection"]["options"] == [{"id": "reasoningEffort", "value": "medium"}]


def test_explicit_effort_wins(posted):
    _, args = posted("launch", "--project", "/r", "--title", "x", "--model", "sol", "--effort", "low", "--", "review")
    assert args["modelSelection"]["model"] == "gpt-6.1-sol"
    assert args["modelSelection"]["options"] == [{"id": "reasoningEffort", "value": "low"}]


def test_named_account_is_capacity_routed_without_fallback(monkeypatch):
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "--resolve":
            return subprocess.CompletedProcess(argv, 0, "gpt-6-astra", "")
        return subprocess.CompletedProcess(argv, 2, "", "account exhausted")
    monkeypatch.setattr(relay.subprocess, "run", run)
    with pytest.raises(SystemExit):
        relay.pick(("codex",), "codex_test")
    assert calls == [[str(relay.HERE / "t3-pick-instance"), "--resolve", "codex"],
                     [str(relay.HERE / "t3-pick-instance"), "gpt-6-astra", "codex_test"]]


def test_default_fallback_stops_at_astra(monkeypatch):
    calls = []
    def run(argv, **kwargs):
        calls.append(argv[1])
        return subprocess.CompletedProcess(argv, 2, "", "exhausted")
    monkeypatch.setattr(relay.subprocess, "run", run)
    with pytest.raises(SystemExit):
        relay.pick(relay.DEFAULT_MODELS)
    assert calls == ["opus", "astra"]


def test_unknown_instance_requires_explicit_model(monkeypatch, tmp_path):
    monkeypatch.setattr(relay, "HOME", tmp_path)
    (tmp_path / "settings.json").write_text("{}")
    with pytest.raises(SystemExit):
        relay.launch_models(None, "unknown")
    assert relay.launch_models("sol", "unknown") == ("sol",)


@pytest.mark.parametrize("model, resolved, instance", [
    ("gemini", "gemini-3.8-flash-high", "antigravity"),
    ("vendor/custom-model", "vendor/custom-model", "opencode_test"),
])
def test_explicit_other_provider_account_survives(monkeypatch, model, resolved, instance):
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        output = resolved if argv[1] == "--resolve" else f"inherited {resolved} -"
        return subprocess.CompletedProcess(argv, 0, output, "")
    monkeypatch.setattr(relay.subprocess, "run", run)
    assert relay.pick((model,), instance) == (instance, resolved, "-")
    assert calls[-1] == [str(relay.HERE / "t3-pick-instance"), resolved]
