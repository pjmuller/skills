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
