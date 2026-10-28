"""t3-relay: argument guard, footer source, the exact MCP call it makes, outcome records (no live T3)."""
import json
import sqlite3
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "t3-relay"
loader = SourceFileLoader("t3_relay", str(SCRIPT))
spec = spec_from_loader(loader.name, loader)
relay = module_from_spec(spec)
sys.modules[loader.name] = relay
loader.exec_module(relay)


def test_effort_without_model_or_instance_is_refused():
    out = subprocess.run([str(SCRIPT), "launch", "--project", "/tmp", "--title", "x", "--effort", "high", "--", "hi"],
                         capture_output=True, text=True)
    assert out.returncode == 2 and "needs --model or --instance" in out.stderr


def test_footer_comes_from_settle_thread_md():
    footer = relay.completion_footer()
    assert footer.startswith("---\nConditional self-settlement") and '"action":"settle"' in footer


class FakeMcp:
    def __init__(self, result=None, exc=None):
        self.calls, self.result, self.exc = [], result, exc

    def call(self, tool, args):
        self.calls.append((tool, args))
        if tool == "t3_project_list":
            return {"projects": [{"id": "proj-1", "workspaceRoot": "/r"}]}
        if self.exc:
            raise self.exc
        return self.result or {"threadId": "mcp:new"}


@pytest.fixture
def posted(monkeypatch, tmp_path):
    fake = FakeMcp()
    monkeypatch.setattr(relay, "REQUESTS", tmp_path)
    monkeypatch.setattr(relay, "HOME", tmp_path)
    monkeypatch.setattr(relay, "origin", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(relay, "connect", lambda base: fake)
    monkeypatch.setattr(relay, "project_id", lambda mcp, path: "proj-1")
    monkeypatch.setattr(relay, "pick", lambda models, instance=None: ("codex_a", "gpt-6.1-sol", "high"))

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["t3-relay", *argv])
        try:
            relay.main()
        except SystemExit as exc:
            run.code = exc.code
        tool, args = fake.calls[-1]
        run.record = json.loads(next(tmp_path.glob("*.json")).read_text())
        return tool, args
    run.fake, run.code = fake, None
    return run


def test_launch_args(posted, capsys):
    tool, args = posted("launch", "--project", "/r", "--title", "⏰ T", "--model", "sol", "--settle-when-done", "--", "Read", "x.md")
    assert tool == "t3_thread_launch"
    assert args["projectId"] == "proj-1" and args["title"] == "⏰ T"
    assert args["workspaceStrategy"] == {"type": "root"} and args["runtimeMode"] == "full-access"
    assert args["modelSelection"] == {"instanceId": "codex_a", "model": "gpt-6.1-sol",
                                      "options": [{"id": "reasoningEffort", "value": "high"}]}
    assert args["message"].startswith("Read x.md\n\n---\nConditional self-settlement")
    rid = posted.record["rid"]
    assert capsys.readouterr().out == f"accepted: relay {rid} via mcp (mcp:new)\n"   # callers parse this line
    assert posted.record["outcome"] == "ok" and posted.record["detail"] == "mcp:new"
    assert relay.wait_for(rid, 0) == 0


def test_send_is_idempotent_per_request(posted):
    tool, args = posted("send", "--thread", "mcp:abc", "--", 'quote " and {{body.x}}')
    assert tool == "t3_thread_send"
    assert args["threadId"] == "mcp:abc" and args["message"] == 'quote " and {{body.x}}'
    assert args["clientRequestId"] == f"relay-{posted.record['rid']}" and args["mode"] == "auto"


def test_lost_answer_is_accepted_but_unconfirmed(posted, capsys):
    posted.fake.exc = relay.Unknown("t3_thread_launch: TimeoutError")
    posted("launch", "--project", "/r", "--title", "⏰ T", "--model", "sol", "--", "go")
    assert posted.code is None and "outcome" not in posted.record          # async: exit 0, status decides
    assert capsys.readouterr().out.startswith("accepted: relay ")


def test_refusal_exits_1_without_accepted_line(posted, monkeypatch, capsys):
    def refuse(tool, args):
        relay.die("t3_thread_launch refused: runtime_mode_escalation_denied")
    monkeypatch.setattr(posted.fake, "call", refuse)
    monkeypatch.setattr(sys, "argv", ["t3-relay", "launch", "--project", "/r", "--title", "x", "--model", "sol", "--", "go"])
    with pytest.raises(SystemExit) as exc:
        relay.main()
    assert exc.value.code == 1 and "accepted" not in capsys.readouterr().out


def db():
    con = sqlite3.connect(":memory:")
    con.executescript("""
      create table orchestration_v2_projection_threads (thread_id, project_id, title, created_at, deleted_at);
      create table orchestration_v2_projection_messages (message_id, thread_id, run_id, role, created_at, payload_json);
    """)
    return con


AT = relay.datetime(2026, 10, 19, 12, 1, tzinfo=relay.timezone.utc)
LATE = relay.datetime(2026, 10, 19, 12, 30, tzinfo=relay.timezone.utc)


def lost(kind="launch"):
    return {"rid": "r1", "kind": kind, "posted_at": "2026-10-19T12:00:00.000Z", "detail": "TimeoutError",
            "project_id": "p", "title": "⏰ job", "thread": "mcp:target"}


def test_lost_launch_resolves_by_effect_then_gives_up():
    con = db()
    con.execute("insert into orchestration_v2_projection_threads values ('mcp:old', 'p', '⏰ job', '2026-10-19T11:00:00.000Z', null)")
    assert relay.request_status(con, lost(), AT)[0] == "pending"           # older same-title thread ignored
    assert relay.request_status(con, lost(), LATE)[0] == "failed"
    con.execute("insert into orchestration_v2_projection_threads values ('mcp:new', 'p', '⏰ job', '2026-10-19T12:00:01.000Z', null)")
    assert relay.request_status(con, lost(), LATE) == ("ok", "mcp:new")


def test_lost_send_matches_client_request_id():
    con = db()
    con.execute("insert into orchestration_v2_projection_messages values "
                "('message:mcp:client%3Ax:thread-send:relay-r1', 'mcp:target', 'rt', 'user', '2026-10-19T12:00:03.000Z', '{}')")
    assert relay.request_status(con, lost("send"), AT) == ("ok", "mcp:target")


def test_lookup_error_is_pending_not_failed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(relay, "REQUESTS", tmp_path)
    (tmp_path / "r1.json").write_text(json.dumps(lost()))
    def locked():
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(relay, "store", locked)
    assert relay.wait_for("r1", 0) == 3 and capsys.readouterr().out.startswith("pending lookup error")


def test_token_cached_until_close_to_expiry(monkeypatch, tmp_path):
    monkeypatch.setattr(relay, "TOKEN_FILE", tmp_path / "t.secret")
    minted = []
    monkeypatch.setattr(relay, "approve", lambda base: minted.append(base) or {"token": "new"})
    fresh = {"token": "old", "origin": "o", "expires_at": relay.stamp(relay.now() + relay.timedelta(days=20))}
    (tmp_path / "t.secret").write_text(json.dumps(fresh))
    assert relay.client_token("o")["token"] == "old" and not minted
    assert relay.client_token("other")["token"] == "new"                      # another server origin
    (tmp_path / "t.secret").write_text(json.dumps({**fresh, "expires_at": relay.stamp(relay.now() + relay.timedelta(days=1))}))
    assert relay.client_token("o")["token"] == "new" and len(minted) == 2


def test_truncated_answer_is_unknown_not_refused():
    """Sol review: T3 may have acted before the reply broke off; exit 1 would invite a duplicate retry."""
    mcp = relay.Mcp.__new__(relay.Mcp)
    def broken(*a, **k):
        raise relay.http.client.IncompleteRead(b"{")
    mcp._rpc = broken
    with pytest.raises(relay.Unknown):
        mcp.call("t3_thread_launch", {})


def test_concurrent_renewals_share_one_approval(monkeypatch, tmp_path):
    import threading
    monkeypatch.setattr(relay, "REQUESTS", tmp_path)
    monkeypatch.setattr(relay, "TOKEN_FILE", tmp_path / "mcp-client.secret")
    approvals = []
    def approve(base):
        approvals.append(base)
        relay.time.sleep(0.2)
        return relay.save_token({"token": f"t{len(approvals)}", "origin": base,
                                 "expires_at": relay.stamp(relay.now() + relay.timedelta(days=30))})
    monkeypatch.setattr(relay, "approve", approve)
    got = []
    workers = [threading.Thread(target=lambda: got.append(relay.client_token("o")["token"])) for _ in range(3)]
    for w in workers: w.start()
    for w in workers: w.join()
    assert approvals == ["o"] and got == ["t1"] * 3
    assert relay.client_token("o", reject="t1")["token"] == "t2"              # 401 → approve again


def test_lost_answer_wait_stays_within_budget(posted, monkeypatch):
    """Sol review: callers kill t3-relay just above --wait; the call time counts against it."""
    posted.fake.exc = relay.Unknown("t3_thread_launch: TimeoutError")
    clock = iter([100.0, 190.0])
    monkeypatch.setattr(relay.time, "monotonic", lambda: next(clock))
    budgets = []
    monkeypatch.setattr(relay, "wait_for", lambda rid, secs: budgets.append(secs) or 3)
    posted("launch", "--project", "/r", "--title", "x", "--model", "sol", "--wait", "120", "--", "go")
    assert budgets == [30.0] and posted.code == 3


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


def test_project_lookup_follows_pagination():
    """v0.5.6 read only the first page (20 of 146 projects): launches into later repos failed."""
    pages = {None: {"projects": [{"id": f"p{i}", "workspaceRoot": f"/x{i}"} for i in range(20)], "nextCursor": 20},
             20: {"projects": [{"id": "target", "workspaceRoot": "/r"}], "nextCursor": None}}
    class Paged:
        def call(self, tool, args):
            return pages[args.get("cursor")]
    assert relay.project_id(Paged(), "/r") == "target"
    with pytest.raises(SystemExit):
        relay.project_id(Paged(), "/elsewhere")


def test_launch_follows_user_default_runtime_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(relay, "HOME", tmp_path)
    assert relay.runtime_mode() == "full-access"
    (tmp_path / "settings.json").write_text('{"defaultRuntimeMode": "auto"}')
    assert relay.runtime_mode() == "auto"
    (tmp_path / "settings.json").write_text('{"defaultRuntimeMode": "bogus"}')
    assert relay.runtime_mode() == "full-access"


@pytest.mark.parametrize("status, changes, cleanup_error, should_settle", [
    ("completed", {}, None, True),
    ("failed", {}, None, False),
    ("completed", {"runCount": 2}, None, False),
    ("completed", {"activeRunId": "run:new"}, None, False),
    ("completed", {"pendingRequestCount": 1}, None, False),
    ("completed", {"snoozed": True}, None, False),
    ("completed", {"archived": True}, None, False),
    ("completed", {"settled": True}, None, False),
    ("completed", None, None, False),  # malformed thread reply after acceptance
    ("completed", {}, SystemExit(1), True),  # T3 rejects a raced user message
    ("completed", {}, relay.Unknown("answer lost"), True),
])
def test_probe_settlement_keeps_launch_accepted(posted, monkeypatch, capsys,
                                               status, changes, cleanup_error, should_settle):
    state = {"runCount": 1, "status": "completed", "activeRunId": None,
             "pendingRequestCount": 0, "settled": False, "snoozed": False, "archived": False, **(changes or {})}

    def call(tool, args):
        posted.fake.calls.append((tool, args))
        if tool == "t3_thread_launch":
            return {"threadId": "mcp:new"}
        if tool == "t3_thread_wait":
            assert 0 < args["timeoutMs"] <= 50_000
            return {"status": status, "timedOut": False}
        if tool == "t3_thread_read":
            return {"thread": None if changes is None else state}
        assert tool == "t3_thread_organize"
        assert args == {"action": "settle", "threadId": "mcp:new"}
        if cleanup_error:
            raise cleanup_error
        return {}

    monkeypatch.setattr(posted.fake, "call", call)
    posted("launch", "--project", "/r", "--title", "probe", "--model", "sol",
           "--settle-after-run", "90", "--", "ok")
    assert posted.code is None and posted.record["outcome"] == "ok"
    assert any(tool == "t3_thread_organize" for tool, _ in posted.fake.calls) == should_settle
    output = capsys.readouterr().out
    assert output.startswith("accepted: relay ")
    assert ("settled: mcp:new" in output) == (not cleanup_error and (should_settle or state["settled"]))


def test_probe_settlement_timeout_does_not_cancel_or_settle(monkeypatch):
    clock = iter([0, 0, 50, 90])
    monkeypatch.setattr(relay.time, "monotonic", lambda: next(clock))
    fake = FakeMcp(result={"status": "running", "timedOut": True})
    assert relay.settle_after_run(fake, "mcp:new", 90).startswith("left open:")
    assert fake.calls == [
        ("t3_thread_wait", {"threadId": "mcp:new", "timeoutMs": 50_000}),
        ("t3_thread_wait", {"threadId": "mcp:new", "timeoutMs": 40_000}),
    ]


def test_request_id_is_saved_before_the_call_and_never_resent(posted, monkeypatch, capsys):
    seen = []
    original = posted.fake.call

    def call(tool, args):
        if tool == "t3_thread_send":
            seen.append(json.loads((relay.REQUESTS / "wa-k1.json").read_text()))
        return original(tool, args)
    monkeypatch.setattr(posted.fake, "call", call)
    posted("send", "--thread", "mcp:r", "--request-id", "wa-k1", "--", "hello")
    assert "outcome" not in seen[0] and seen[0]["fingerprint"]            # crash here = resolvable by effect
    assert posted.fake.calls[-1][1]["clientRequestId"] == "relay-wa-k1"
    calls = len(posted.fake.calls)
    capsys.readouterr()
    posted("send", "--thread", "mcp:r", "--request-id", "wa-k1", "--wait", "5", "--", "hello")
    assert len(posted.fake.calls) == calls and posted.code == 0
    assert capsys.readouterr().out.splitlines() == [
        "accepted: relay wa-k1 via mcp (mcp:new) (already delivered, not re-sent)", "ok mcp:new"]
    posted("send", "--thread", "mcp:r", "--request-id", "wa-k1", "--", "other text")
    assert posted.code == 2 and len(posted.fake.calls) == calls


def test_request_id_pending_waits_and_refused_resends(posted, monkeypatch):
    posted.fake.exc = relay.Unknown("t3_thread_send: TimeoutError")
    posted("send", "--thread", "mcp:r", "--request-id", "k2", "--", "hi")
    monkeypatch.setattr(relay, "store", db)   # effect not visible yet, well within GIVE_UP
    calls = len(posted.fake.calls)
    posted("send", "--thread", "mcp:r", "--request-id", "k2", "--", "hi")
    assert posted.code == 3 and len(posted.fake.calls) == calls        # never re-sent while unknown
    record = relay.REQUESTS / "k2.json"
    record.write_text(json.dumps({**json.loads(record.read_text()), "outcome": "failed", "detail": "refused"}))
    posted.fake.exc = None
    posted("send", "--thread", "mcp:other", "--request-id", "k2", "--", "hi")   # failed: may go elsewhere
    assert len(posted.fake.calls) == calls + 1 and posted.record["outcome"] == "ok"


def test_refusal_marks_request_failed(posted, monkeypatch):
    monkeypatch.setattr(posted.fake, "call", lambda tool, args: relay.die("t3_thread_send refused: gone"))
    monkeypatch.setattr(sys, "argv", ["t3-relay", "send", "--thread", "mcp:x", "--request-id", "k3", "--", "hi"])
    with pytest.raises(SystemExit):
        relay.main()
    assert json.loads((relay.REQUESTS / "k3.json").read_text())["outcome"] == "failed"


def test_bad_request_id_is_usage_error():
    out = subprocess.run([str(SCRIPT), "send", "--thread", "x", "--request-id", "a b", "--", "hi"],
                         capture_output=True, text=True)
    assert out.returncode == 2 and "--request-id" in out.stderr


def pins_db(rows):
    con = sqlite3.connect(":memory:")
    con.execute("create table orchestration_v2_projection_threads (thread_id, payload_json, archived_at, deleted_at)")
    con.executemany("insert into orchestration_v2_projection_threads values (?,?,?,?)", rows)
    return con


def test_find_exact_open_roots_pinned_first(monkeypatch):
    listed = [
        {"threadId": "a", "title": "🧭 R", "status": "completed", "createdAt": "1", "parentThreadId": None},
        {"threadId": "b", "title": "🧭 R", "status": "idle", "createdAt": "2", "parentThreadId": None},
        {"threadId": "c", "title": "🧭 R old", "createdAt": "3"},                       # not exact
        {"threadId": "d", "title": "🧭 R", "createdAt": "4", "parentThreadId": "a"},    # child
        {"threadId": "e", "title": "🧭 R", "createdAt": "5", "settled": True},
        {"threadId": "f", "title": "🧭 R", "createdAt": "6"},                           # archived
    ]
    pages = [{"threads": listed[:3], "nextCursor": 3}, {"threads": listed[3:], "nextCursor": None}]
    fake = FakeMcp()
    fake.call = lambda tool, args: (fake.calls.append((tool, args)), pages[len(fake.calls) - 1])[1]
    monkeypatch.setattr(relay, "connect", lambda base: fake)
    monkeypatch.setattr(relay, "project_id", lambda mcp, path: "p")
    monkeypatch.setattr(relay, "store", lambda: pins_db([
        ("a", '{"pinnedAt": "2026-10-27T12:44:00Z"}', None, None), ("b", '{"pinnedAt": null}', None, None),
        ("f", '{"pinnedAt": "2026-10-28T00:00:00Z"}', "2026-10-28", None)]))
    found = relay.cmd_find("http://x", "/r", "🧭 R")
    assert [(t["threadId"], t["pinnedAt"]) for t in found] == [("a", "2026-10-27T12:44:00Z"), ("b", None)]
    assert fake.calls[0][1]["settled"] is False and fake.calls[1][1]["cursor"] == 3


def test_pin_state_schema_drift_is_unavailable_not_unpinned(monkeypatch):
    monkeypatch.setattr(relay, "store", lambda: pins_db([("a", '{"title": "x"}', None, None)]))
    with pytest.raises(SystemExit) as exc:
        relay.pin_state(["a"])
    assert exc.value.code == 1
