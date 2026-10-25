"""t3-mail-link: Chrome titles, new-inbound detection, link dedupe, read-only resolve. Ref parsing and the
multi-mailbox lookup are google-workspace-core's (its test_workspace_accounts.py)."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

loader = importlib.machinery.SourceFileLoader("mail_link", str(Path(__file__).with_name("t3-mail-link")))
spec = importlib.util.spec_from_loader("mail_link", loader)
ml = importlib.util.module_from_spec(spec)
loader.exec_module(ml)
ml.core()
from gws_core import ApiError  # noqa: E402  (the sibling core, as t3-mail-link loads it)
from gws_core.accounts import parse_ref  # noqa: E402


def not_found(*a, **kw):
    raise ApiError(404, "GET", a[1] if len(a) > 1 else "", "Requested entity was not found.")


def test_chrome_title():
    assert ml.parse_chrome_title("Offer - v2 - final? - ann@example.com - Example Mail") == (
        "Offer - v2 - final?", "ann@example.com")
    assert ml.parse_chrome_title("Inbox (12) - ann@example.com - Example Mail") is None
    assert ml.parse_chrome_title("Gmail") is None


def msg(mid, sender="bob@vendor.test", labels=("INBOX",), at=0):
    return {"id": mid, "labelIds": list(labels), "internalDate": str(at),
            "payload": {"headers": [{"name": "From", "value": f"Bob <{sender}>"}]}}


def test_classify_new():
    messages = [msg("a"), msg("b", "Ann@Example.com", ("INBOX",)), msg("c", labels=("SENT",)),
                msg("d", labels=("DRAFT",)), msg("e")]
    assert ml.classify_new(messages, {"a"}, "ann@example.com") == (["e"], ["b", "c"])
    timed = [msg("a", at=100), msg("b", at=200), msg("d", labels=("DRAFT",), at=50)]
    assert ml.baseline(timed, 150) == ["a"]  # mail after the claim still wakes


GMAIL = "19e875318442de06"


@pytest.mark.parametrize("command,output,expected", [
    ("gws gmail-draft --to x", f"draft created: r-1\nMail-ref: gmail:{GMAIL} Ann@Example.com\n",
     [("claim", GMAIL, "ann@example.com", None)]),
    ("t3-mail-link --config c claim X --for t1", f"Mail-ref: gmail:{GMAIL} a@x owner=t1\nnote", [("claim", GMAIL, "a@x", "t1")]),
    ("t3-mail-link release X", f"Mail-release: gmail:{GMAIL} a@x", [("release", GMAIL, "a@x", None)]),
    ("cat mail-link.md", f"Mail-ref: gmail:{GMAIL} a@x", []),                       # quoted docs: no claim
    ("gws gmail-draft", f"> Mail-ref: gmail:{GMAIL} a@x\n\"marker\": \"Mail-ref: gmail:{GMAIL} a@x\"", []),
])
def test_mail_events_only_from_claiming_commands_own_lines(command, output, expected):
    assert ml.mail_events(command, output) == expected


def test_top_thread_maps_children_to_their_parent():
    assert ml.top_thread("aa83df67-672f-4b2d-b972-a966c8291dbf") == "aa83df67-672f-4b2d-b972-a966c8291dbf"
    sub = ("thread:provider:claudeAgent:native-thread:provider-thread%3Aprovider%3AclaudeAgent%3Anative-thread%3Apending"
           "%253Arun%253Athread%253Amcp%25253A3fca46a2-4e91-4021-a9c4-b1d958a79e0d%253Aordinal%253A1%3Aa5c7a70989cea0a88")
    assert ml.top_thread(sub) == "mcp:3fca46a2-4e91-4021-a9c4-b1d958a79e0d"
    task = "thread:delegated-task:command%3Amcp%3Ab6678c96-9ecb-442f-a578-4aadfab12538%3Adelegate-task%3Ac811-e2-haiku"
    assert ml.top_thread(task) == "mcp:b6678c96-9ecb-442f-a578-4aadfab12538"


@pytest.mark.parametrize("headers,expected", [
    ({"Auto-Submitted": "auto-replied", "Subject": "Re: Offer"}, True),
    ({"Subject": "Automatisch antwoord: Offer"}, True),
    ({"Subject": "Out of Office: back Monday"}, True),
    ({"Auto-Submitted": "auto-generated", "Subject": "Delivery Status Notification (Failure)"}, False),  # bounce: triage
    ({"Subject": "Re: Offer"}, False),
])
def test_auto_reply(headers, expected):
    assert ml.auto_reply(headers) is expected


@pytest.mark.parametrize("stdout,expected", [
    ('{"wake": false, "reason": "thanks only"}', (False, "thanks only")),
    ('Sure:\n{"wake": true, "reason": "asks a new price"}', (True, "asks a new price")),
    ("garbage", (True, "no triage reason")),  # fail open
    ('{"wake": "no"}', (True, "no triage reason")),
])
def test_parse_verdict_fails_open(stdout, expected):
    assert ml.parse_verdict(stdout) == expected


def test_ping_text_is_shell_safe():
    case = {"subject": "Price `rm` $(x)", "account": "a@x", "gmail_thread": "t1", "owner": "id1"}
    text = ml.ping_text(case, Path("/tmp/m.md"), ["m1", "m2"], "new `price`", {"config": "/c.json", "policy": None})
    assert "`" not in text and "$(" not in text and "m2" in text and "UNTRUSTED" in text and "Triage" in text


def cand(tid, *subjects):
    return {"threadId": tid, "subjects": list(subjects), "date": "", "from": ""}


def test_unique_thread_subject_filter_and_fail_closed(capsys):
    hits = [cand("a", "Offer", "Re: Offer"), cand("b", "Other")]
    assert ml.unique_thread(hits, False, "RE: offer") == "a"
    with pytest.raises(SystemExit) as exc:  # older same-subject thread beyond the cap: never unique
        ml.unique_thread(hits, True, "Offer")
    assert exc.value.code == 3 and "more exist" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        ml.unique_thread([cand("a", "Offer"), cand("c", "Fwd: Offer")], False, "Offer")
    assert exc.value.code == 3


def test_draft_fingerprint_ignores_ids_and_whitespace():
    view = {"id": "m1", "headers": {"To": "a@x", "Subject": "Re: Offer", "Date": "d1"},
            "body": "Hi,\n\nfine.\n\nOn Mon wrote:\n> quoted", "attachments": []}
    same = {**view, "id": "m2", "headers": {**view["headers"], "Date": "d2"}, "body": "Hi,\nfine.\nOn Mon wrote:\n> quoted"}
    edited = {**view, "body": "Hi, fine, but 10% less.\nOn Mon wrote:\n> quoted"}
    assert ml.draft_fingerprint(view) == ml.draft_fingerprint(same) != ml.draft_fingerprint(edited)


def test_list_thread_ids_reads_state_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path))
    monkeypatch.setattr(ml, "t3_thread", lambda tid: pytest.fail("no T3 lookup"))
    assert ml.main(["list", "--thread-ids"]) == 0 and capsys.readouterr().out == ""  # no state file yet
    legacy = tmp_path / "userdata" / "mail-links.json"  # pre-claim registry: read as cases, not rewritten
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"links": [link(t, g) for t, g in (("a", "g1"), ("b", "g2"), ("a", "g3"))]}))
    assert ml.main(["list", "--thread-ids"]) == 0 and capsys.readouterr().out == "a\nb\n"
    assert legacy.exists() and not (legacy.parent / "mail-watch.json").exists()


def link(t3, gmail):
    return {"t3_thread": t3, "gmail_thread": gmail, "account": "ann@example.com", "config": "/c.json",
            "policy": None, "subject": "Deal", "seen": ["m1"], "linked_at": "2026-10-19T12:00:00"}


def test_legacy_registry_migrates_once(tmp_path, monkeypatch):
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path))
    legacy = tmp_path / "userdata" / "mail-links.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"links": [{**link("t1", GMAIL), "pending": {"rid": "r1", "inbound": ["m2"], "at": 1}}]}))
    with ml.locked_state() as state:
        case = state["cases"][f"ann@example.com:{GMAIL}"]
    assert case["owner"] == "t1" and case["seen"] == ["m1"] and case["pending"]["rid"] == "r1" and state["accounts"]["ann@example.com"]["config"] == "/c.json"
    assert not legacy.exists() and (tmp_path / "userdata/mail-links.json.migrated").exists()


@pytest.fixture
def t3db(tmp_path, monkeypatch):
    """A statev2.sqlite with T3's thread and turn-item tables (the columns the poller reads)."""
    import sqlite3
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path))
    (tmp_path / "userdata").mkdir()
    db = sqlite3.connect(tmp_path / "userdata/statev2.sqlite")
    db.execute("CREATE TABLE orchestration_v2_projection_threads (thread_id TEXT PRIMARY KEY, title TEXT, "
               "deleted_at TEXT, archived_at TEXT, payload_json TEXT DEFAULT '{}')")
    db.execute("CREATE TABLE orchestration_v2_projection_turn_items (turn_item_id TEXT PRIMARY KEY, thread_id TEXT, "
               "type TEXT, status TEXT, payload_json TEXT)")
    db.executemany("INSERT INTO orchestration_v2_projection_threads (thread_id, title, deleted_at, archived_at) "
                   "VALUES (?, ?, ?, ?)", [
        ("aaaaaaaa-0000-0000-0000-000000000001", "Offer case", None, None),
        ("mcp:bbbbbbbb-0000-0000-0000-000000000002", "Mail dispatch", None, None),
        ("cccccccc-0000-0000-0000-000000000003", "Old case", "2026-10-01", None),
        ("dddddddd-0000-0000-0000-000000000004", "Follow-up case", None, None)])
    db.commit()

    def add(thread, command, output, status="completed", at="2026-10-20T10:00:00.000Z"):
        rowid = db.execute("SELECT COUNT(*) FROM orchestration_v2_projection_turn_items").fetchone()[0] + 1
        payload = {"input": command, "output": output, "completedAt": at, "updatedAt": at}
        db.execute("INSERT INTO orchestration_v2_projection_turn_items VALUES (?, ?, 'command_execution', ?, ?)",
                   (f"i{rowid}", thread, status, json.dumps(payload)))
        db.commit()
        return rowid
    yield add
    db.close()


def test_scan_events_starts_at_the_end_and_holds_before_a_running_claim(t3db):
    t3db("aaaaaaaa-0000-0000-0000-000000000001", "gws gmail-draft", f"Mail-ref: gmail:{GMAIL} a@x")
    assert ml.scan_events(None) == ([], 1)  # first run: older text predates the markers
    t3db("aaaaaaaa-0000-0000-0000-000000000001", "ls", "Mail-ref: gmail:1111111111111111 a@x")  # not a claiming command
    running = t3db("aaaaaaaa-0000-0000-0000-000000000001", "gws gmail-send", "", status="running",
                   at=datetime.now(timezone.utc).isoformat())
    t3db("aaaaaaaa-0000-0000-0000-000000000001", "gws gmail-draft", f"Mail-ref: gmail:{GMAIL} a@x")
    events, cursor = ml.scan_events(1)
    assert events == [] and cursor == running - 1  # the later claim waits: order is kept
    old_running = t3db("aaaaaaaa-0000-0000-0000-000000000001", "gws gmail-send", "", status="running",
                       at="2026-01-01T00:00:00Z")
    events, cursor = ml.scan_events(running)  # a stale "running" row never pins the cursor
    assert [e["row"] for e in events] == [running + 1] and cursor == old_running


TASK = "thread:delegated-task:command%3Amcp%3Ab6678c96-9ecb-442f-a578-4aadfab12538%3Adelegate-task%3Ac811-e2-haiku"


def add_child(tmp_path, child, root):
    import sqlite3
    db = sqlite3.connect(tmp_path / "userdata/statev2.sqlite")
    db.execute("INSERT INTO orchestration_v2_projection_threads (thread_id, title, payload_json) VALUES (?, 'child', ?)",
               (child, json.dumps({"lineage": {"rootThreadId": root, "relationshipToParent": "subagent"}})))
    db.commit()
    db.close()


def test_delegated_child_claims_for_its_recorded_root(t3db, tmp_path):
    """A delegated-task id embeds a command id, not its parent: T3's lineage decides who owns the case."""
    add_child(tmp_path, TASK, "aaaaaaaa-0000-0000-0000-000000000001")
    assert ml.root_thread(TASK) == "aaaaaaaa-0000-0000-0000-000000000001"
    assert ml.root_thread("thread:delegated-task:gone") == "thread:delegated-task:gone"  # no lineage, no embedded id
    t3db(TASK, "gws gmail-draft --reply-to-message m1", f"Mail-ref: gmail:{GMAIL} a@x")
    events, _ = ml.scan_events(0)
    assert [e["owner"] for e in events] == ["aaaaaaaa-0000-0000-0000-000000000001"]


def test_recorded_claim_reads_t3_without_a_watch(t3db, tmp_path):
    add_child(tmp_path, TASK, "aaaaaaaa-0000-0000-0000-000000000001")
    assert ml.recorded_claim("a@x", GMAIL) is None
    t3db("dddddddd-0000-0000-0000-000000000004", "cat brief.md", f"Mail-ref: gmail:{GMAIL} a@x")  # quoted: no claim
    assert ml.recorded_claim("a@x", GMAIL) is None
    t3db(TASK, "gws gmail-send", f"Mail-ref: gmail:{GMAIL} a@x")
    t3db("dddddddd-0000-0000-0000-000000000004", "gws gmail-draft", f"Mail-ref: gmail:{GMAIL} other@x")  # other mailbox
    assert ml.recorded_claim("a@x", GMAIL) == "aaaaaaaa-0000-0000-0000-000000000001"
    t3db("x", "t3-mail-link claim g --for d", f"Mail-ref: gmail:{GMAIL} a@x owner=dddddddd-0000-0000-0000-000000000004")
    assert ml.recorded_claim("a@x", GMAIL) == "dddddddd-0000-0000-0000-000000000004"
    t3db("mcp:bbbbbbbb-0000-0000-0000-000000000002", "gws gmail-draft-update", f"Mail-ref: gmail:{GMAIL} a@x")
    assert ml.recorded_claim("a@x", GMAIL) == "dddddddd-0000-0000-0000-000000000004"  # routing thread never owns
    t3db("x", "t3-mail-link release g", f"Mail-release: gmail:{GMAIL} a@x")
    assert ml.recorded_claim("a@x", GMAIL) is None


def test_scan_events_canary_on_schema_change(t3db, tmp_path):
    import sqlite3
    t3db("x", "gws gmail-draft", f"Mail-ref: gmail:{GMAIL} a@x")
    db = sqlite3.connect(tmp_path / "userdata/statev2.sqlite")
    db.execute("UPDATE orchestration_v2_projection_turn_items SET payload_json = '{\"cmd\": \"Mail-ref: gmail:\"}'")
    db.commit()
    with pytest.raises(sqlite3.DatabaseError):
        ml.scan_events(0)


def test_apply_event_claims_hands_off_and_releases(t3db, monkeypatch, capsys):
    from types import SimpleNamespace as NS
    api_error = type("ApiError", (Exception,), {"__init__": lambda self, status: setattr(self, "status", status)})
    monkeypatch.setitem(sys.modules, "gws_core", NS(ApiError=api_error))
    monkeypatch.setattr(ml, "workspace", lambda config: None)

    def metadata(ws, gid):
        if gid != GMAIL:
            raise api_error(404)
        return {"messages": [msg("old", at=1000), {**msg("new", at=4_000_000_000_000)}]}
    monkeypatch.setattr(ml, "thread_metadata", metadata)
    state = {"accounts": {"a@x": {"config": "/c.json"}}, "cases": {}}
    key = f"a@x:{GMAIL}"

    def event(kind="claim", owner="aaaaaaaa-0000-0000-0000-000000000001", gmail=GMAIL, account="a@x"):
        return {"row": 9, "kind": kind, "gmail_thread": gmail, "account": account, "owner": owner,
                "at": "2026-10-20T10:00:00.000Z"}

    for ignored in (event(owner="mcp:bbbbbbbb-0000-0000-0000-000000000002"),  # legacy dispatch title never owns
                    event(owner="cccccccc-0000-0000-0000-000000000003"),      # deleted thread
                    event(account="other@x"),                                 # account not watched
                    event(gmail="1111111111111111")):                         # not a thread of this account
        assert ml.apply_event(state, ignored) and state["cases"] == {}
    assert ml.apply_event(state, event())
    assert state["cases"][key]["seen"] == ["old"]  # baseline at claim time: "new" still wakes
    state["cases"][key]["seen"] = ["old", "new"]
    monkeypatch.setattr(ml, "thread_metadata", lambda *a: pytest.fail("a re-claim keeps the seen set"))
    state["cases"][key]["pending"] = {"rid": "r1", "inbound": ["new"], "at": 0}
    assert ml.apply_event(state, event(owner="mcp:dddddddd-0000-0000-0000-000000000004"))  # hand-off, id form normalized
    assert "pending" not in state["cases"][key]  # the old owner's ping never marks mail seen for the new one
    assert state["cases"][key]["owner"] == "dddddddd-0000-0000-0000-000000000004"
    assert state["cases"][key]["seen"] == ["old", "new"]
    assert ml.apply_event(state, event("release")) and state["cases"] == {}


@pytest.fixture
def resolver(tmp_path, monkeypatch):
    """Offline Workspace reads; any T3 call, saved-mail or link-state write fails the test."""
    ws = Mock(config=SimpleNamespace(account="Ann@Example.com"))
    ws.whoami.return_value = {"email": "ANN@example.com"}
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path))
    monkeypatch.setenv("GWS_CONFIG", str(tmp_path / "workspace.json"))
    monkeypatch.setattr(ml, "workspace", lambda config: ws)
    for name in ("locked_state", "save_texts", "t3_thread", "cmd_draft"):
        monkeypatch.setattr(ml, name, lambda *a, **kw: pytest.fail("resolve must not mutate or access T3"))
    monkeypatch.setattr(ml.subprocess, "run", lambda *a, **kw: pytest.fail("no subprocess in offline resolve"))
    state = tmp_path / "userdata/mail-watch.json"
    state.parent.mkdir()
    state.write_text('{"cases": {"ann@example.com:existing": {"gmail_thread": "existing", "owner": "keep"}}}')
    saved = state.parent / "mail-links/existing/thread.md"
    saved.parent.mkdir(parents=True)
    saved.write_text("saved mail remains untouched")

    def snapshot():
        return {str(p.relative_to(tmp_path)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in tmp_path.rglob("*") if p.is_file()}

    before = snapshot()
    yield ws
    assert snapshot() == before


@pytest.mark.parametrize("ref", [
    "19e875318442de06",
    "https://mail.google.com/mail/u/0/?view=pt&permthid=thread-f:1866870901077892614",
])
def test_resolve_exact_reference(resolver, capsys, ref):
    resolver.api.side_effect = lambda *a, **kw: {"id": a[1].rsplit("/", 1)[-1]}
    assert ml.main(["resolve", ref]) == 0
    parsed = json.loads(capsys.readouterr().out)
    gmail_id = parse_ref(ref).threads[0]
    assert parsed == {"account": "ann@example.com", "gmail_thread": gmail_id,
                      "marker": f"Mail-ref: gmail:{gmail_id} ann@example.com"}
    resolver.whoami.assert_called_once_with()
    assert resolver.api.call_args.args[0] == "GET"
    resolver.gmail.get.assert_not_called()


def routed(routes):
    """ws.api stand-in: metadata-only GETs; ids not in ROUTES answer 404."""
    def api(method, url, **kw):
        assert method == "GET" and kw["params"] == {"format": "minimal"}
        key = url.rsplit("/users/me/", 1)[1]
        if key not in routes:
            not_found(method, url)
        return routes[key]
    return api


def test_resolve_message_and_draft_are_metadata_reads(resolver, capsys):
    resolver.api.side_effect = routed({"messages/19e875318442de06": {"threadId": "thread-from-message"}})
    assert ml.main(["resolve", "19e875318442de06"]) == 0  # bare id: thread 404 → message
    assert json.loads(capsys.readouterr().out)["gmail_thread"] == "thread-from-message"
    resolver.api.side_effect = routed({"drafts/r-12": {"message": {"threadId": "thread-from-draft"}}})
    assert ml.main(["resolve", "https://mail.google.com/mail/u/0/?permmsgid=msg-a:r-12"]) == 0
    assert json.loads(capsys.readouterr().out)["gmail_thread"] == "thread-from-draft"
    assert resolver.gmail.method_calls == []


def test_resolve_print_link_of_a_thread_you_started_uses_its_received_messages(resolver, capsys):
    m1, m2 = format(1800000000000000001, "x"), format(1800000000000000002, "x")
    resolver.api.side_effect = routed({f"messages/{m2}": {"threadId": "started-thread"}})
    url = ("https://mail.google.com/mail/u/0/?ik=x&view=pt&search=all&permthid=thread-a:r-7363"
           "&simpl=msg-f:1800000000000000001&simpl=msg-f:1800000000000000002")
    assert ml.main(["resolve", url]) == 0
    assert json.loads(capsys.readouterr().out)["gmail_thread"] == "started-thread"
    assert [c.args[1].rsplit("/", 1)[1] for c in resolver.api.call_args_list] == [m1, m2]  # no thread-a guess


def test_resolve_not_found_points_at_all_accounts(resolver):
    resolver.api.side_effect = not_found
    with pytest.raises(SystemExit, match="--all-accounts"):
        ml.main(["resolve", "msg-f:1800000000000000001"])


def test_all_accounts_resolves_in_the_holding_mailbox_without_config(resolver, monkeypatch, capsys):
    hit = SimpleNamespace(workspace=resolver, gmail_thread="pb-thread", checked=[
        {"account": "ann@example.com", "result": "not found"}, {"account": "ann@example.com", "result": "match"}],
        account=SimpleNamespace(config=SimpleNamespace(account="Ann@Example.com")))
    seen = {}
    monkeypatch.setattr("gws_core.accounts.load_inventory", lambda: ["inventory"])
    monkeypatch.setattr("gws_core.accounts.locate_any", lambda ref, accounts: seen.update(ref=ref) or hit)
    monkeypatch.setattr(ml, "workspace", lambda config: pytest.fail("--all-accounts never uses GWS_CONFIG"))
    assert ml.main(["resolve", "--all-accounts", "msg-f:1800000000000000001"]) == 0
    assert json.loads(capsys.readouterr().out)["gmail_thread"] == "pb-thread"
    assert seen["ref"].messages == (format(1800000000000000001, "x"),)


@pytest.mark.parametrize("argv", [["--config", "x.json", "resolve", "--all-accounts", "19e875318442de06"],
                                  ["resolve", "--all-accounts", "--search", "subject:offer"]])
def test_all_accounts_refuses_an_explicit_account_or_content_search(resolver, argv):
    with pytest.raises(SystemExit) as exc:
        ml.main(argv)
    assert exc.value.code == 2


def test_resolve_search_and_ambiguity(resolver, capsys):
    resolver.api.side_effect = [{"threads": [{"id": "one"}]}, {"messages": []}]
    assert ml.main(["resolve", "--search", "from:vendor.test subject:offer"]) == 0
    assert json.loads(capsys.readouterr().out)["gmail_thread"] == "one"
    assert resolver.api.call_args_list[0].kwargs["params"]["q"] == "from:vendor.test subject:offer"
    resolver.api.side_effect = [{"threads": [{"id": "one"}, {"id": "two"}]},
                                {"messages": []}, {"messages": []}]
    with pytest.raises(SystemExit) as exc:
        ml.main(["resolve", "--search", "subject:offer"])
    assert exc.value.code == 3 and capsys.readouterr().out == ""


@pytest.mark.parametrize("identity", [{"email": "other@example.com"}, {}])
def test_resolve_wrong_or_unknown_identity_stops_before_lookup(resolver, identity):
    resolver.whoami.return_value = identity
    with pytest.raises(SystemExit, match="nothing resolved"):
        ml.main(["resolve", "19e875318442de06"])
    resolver.api.assert_not_called()
    assert resolver.gmail.method_calls == []


def test_resolve_failed_identity_probe_stops_before_lookup(resolver):
    resolver.whoami.side_effect = RuntimeError("expired token")
    with pytest.raises(RuntimeError, match="expired token"):
        ml.main(["resolve", "19e875318442de06"])
    resolver.api.assert_not_called()
    assert resolver.gmail.method_calls == []


def test_resolve_explicit_wrapper_overrides_environment(resolver, monkeypatch, tmp_path):
    selected = Mock(return_value=resolver)
    monkeypatch.setattr(ml, "workspace", selected)
    resolver.api.return_value = {"id": "canonical"}
    assert ml.main(["--config", str(tmp_path / "explicit.json"), "resolve", "19e875318442de06"]) == 0
    selected.assert_called_once_with(str(tmp_path / "explicit.json"))


def test_resolve_browser_account_mismatch_stops_before_search(resolver, monkeypatch):
    monkeypatch.setattr(ml, "chrome_subject", lambda *a: ("Offer", "other@example.com"))
    with pytest.raises(SystemExit, match="that Gmail tab belongs to other@example.com"):
        ml.main(["resolve", "https://mail.google.com/mail/u/0/#inbox/FMfcgzQhWTsMxrbPlmQHFRGDvlgCtzdB"])
    resolver.api.assert_not_called()


@pytest.mark.parametrize("argv", [["resolve"], ["resolve", "19e875318442de06", "--search", "q"]])
def test_resolve_requires_one_reference_or_search(resolver, argv):
    with pytest.raises(SystemExit) as exc:
        ml.main(argv)
    assert exc.value.code == 2
    resolver.whoami.assert_not_called()


def test_id_terms_cover_hex_decimal_and_drafts():
    thread = {"id": "19e875318442de06", "messages": [{"id": "19e875318442de06"}, {"id": "19e8753184430000"}]}
    assert ml.id_terms(thread, ["r-42"]) == [
        "19e875318442de06", str(int("19e875318442de06", 16)),
        "19e8753184430000", str(int("19e8753184430000", 16)), "r-42", "42"]
    assert ml.id_terms({"id": "1a"}, ["r815"])[-2:] == ["r815", "815"]


def hit(tid, title="Offer follow-up"):
    return {"thread_id": tid, "short_id": tid.removeprefix("mcp:")[:8], "title": title, "project": "p",
            "updated_at": "2026-01-02T00:00:00Z", "link": f"[{title}](t3-thread://v1/{tid})"}


def test_classify_owners_ranks_and_excludes_intake():
    legacy = {**hit("thread:project:p1:dddddddd-4"), "short_id": "dddddddd"}
    hits = [hit("aaaaaaaa-1"), hit("bbbbbbbb-2"), hit("mcp:cccccccc-3", "Team dispatch"), legacy, hit("eeeeeeee-5"),
            hit("mcp:ffffffff-7", "🧭 PJ routing"), hit("gggggggg-8", "Fix Rails routing")]
    peeks = {"bbbbbbbb-2": {"prompts": [{"text": "Execution thread: perform the task here."}]}}
    greps = {"aaaaaaaa-1": (False, True), "bbbbbbbb-2": (True, True)}
    owners, excluded = ml.classify_owners(hits, peeks, greps, ["eeeeeeee-5"], ["dddd"], "id")
    assert [(o["thread_id"], o["evidence"]) for o in owners] == [
        ("eeeeeeee-5", "owner"), ("bbbbbbbb-2", "marker"), ("aaaaaaaa-1", "id"), ("gggggggg-8", "id")]
    assert owners[1]["execution"] and owners[1]["account_seen"] and not owners[0]["account_seen"]
    assert [(x["thread_id"], x["why"]) for x in excluded] == [
        ("mcp:cccccccc-3", "routing"), ("thread:project:p1:dddddddd-4", "excluded"), ("mcp:ffffffff-7", "routing")]


def test_find_is_read_only_and_falls_back_to_subject(resolver, monkeypatch, capsys):
    resolver.api.return_value = {"id": "19e875318442de06", "messages": [
        {"id": "19e875318442de06", "payload": {"headers": [{"name": "Subject", "value": "Re: Offer renewal 2027"}]}}]}
    calls = []

    def fake_find(*argv):
        calls.append(argv)
        if argv[0] == "search":
            return {"results": [hit("mcp:cccccccc-3", "🧭 PJ routing")] if "--all" not in argv else [hit("ffffffff-6")]}
        if argv[0] == "peek":
            return [{"thread_id": i, "prompts": []} for i in argv[1].split(",")]
        return {"snippets": []}

    monkeypatch.setattr(ml, "find_thread", fake_find)
    monkeypatch.setattr(ml, "recorded_claim", lambda account, gmail: None)

    assert ml.main(["find", "thread-f:1866870901077892614", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["owners"] == [] and [t["evidence"] for t in report["topic"]] == ["topic"] and report["history"] == []
    assert [x["why"] for x in report["excluded"]] == ["routing"]
    topic_search = next(c for c in calls if "--all" in c)
    assert topic_search[-3:] == ("offer", "renewal", "2027")
    assert all(c[1:3] == ("--backup", "on") or c[2:4] == ("--backup", "on") for c in calls if c[0] == "search")


def test_find_ranks_a_recorded_claim_as_owner_and_lists_children_as_history(resolver, monkeypatch, capsys):
    resolver.api.return_value = {"id": "19e875318442de06", "messages": [
        {"id": "19e875318442de06", "payload": {"headers": [{"name": "Subject", "value": "Offer"}]}}]}
    child = "thread:provider:claudeAgent:native-thread:x"
    mine = "thread:provider:claudeAgent:native-thread:mine"

    def fake_find(*argv):
        if argv[0] == "search":
            if "--subagents" in argv:
                return {"results": [hit("aaaaaaaa-1"), {**hit(child, "Review offer"), "backup": False},
                                    hit(mine, "My reviewer")]}
            return {"results": [hit("aaaaaaaa-1")]}
        if argv[0] == "peek":
            return [{"thread_id": i, "prompts": [], "short_id": i[:8], "title": "Case", "project": "p",
                     "updated_at": "2026-01-02T00:00:00Z", "link": None} for i in argv[1].split(",")]
        return {"snippets": []}

    monkeypatch.setattr(ml, "find_thread", fake_find)
    monkeypatch.setattr(ml, "recorded_claim", lambda account, gmail: "bbbbbbbb-2")
    monkeypatch.setattr(ml, "t3_lookup", lambda tid: ("mcp:" + tid, {"title": "Case"}))
    monkeypatch.setattr(ml, "root_thread", lambda tid, db=None: {child: "mcp:cccccccc-3", mine: "mcp:me"}[tid])
    assert ml.main(["find", "19e875318442de06", "--exclude", "me", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [(o["thread_id"], o["evidence"]) for o in report["owners"]] == [("mcp:bbbbbbbb-2", "owner"), ("aaaaaaaa-1", "id")]
    assert [(h["thread_id"], h["parent"]) for h in report["history"]] == [(child, "mcp:cccccccc-3")]


def test_marker_grep_uses_full_line(monkeypatch):
    greps = []
    monkeypatch.setattr(ml, "find_thread", lambda *argv: greps.append(argv) or (
        [{"thread_id": "t1", "prompts": []}] if argv[0] == "peek" else {"snippets": [{}] if "Mail-ref" in argv[3] else []}))
    _, _, seen = ml.inspect([hit("t1")], [], "ann@example.com", "19e8")
    assert seen == {"t1": (True, False)}
    assert ("grep", "t1", "-k", "Mail-ref: gmail:19e8 ann@example.com", "--limit", "1") in greps


def test_ping_marks_seen_only_once_it_landed(monkeypatch, tmp_path):
    """Accepted-but-unconfirmed pings are re-checked, never resent; a failed one is resent."""
    case = {"gmail_thread": "g1", "owner": "t1", "account": "ann@example.com", "seen": ["a"], "subject": "Deal"}
    account = {"config": "c", "policy": None}
    gmail = SimpleNamespace(get=lambda mid: msg(mid), view=lambda m, trim: {"headers": {}, "attachments": [], "body": "x"})
    monkeypatch.setattr(ml, "workspace", lambda config: SimpleNamespace(gmail=gmail))
    monkeypatch.setattr(ml, "thread_metadata", lambda ws, gid: {"messages": [msg("a"), msg("e")]})
    monkeypatch.setattr(ml, "t3_lookup", lambda tid: (tid, {"title": "Deal"}))
    monkeypatch.setattr(ml, "save_texts", lambda *a, **kw: tmp_path / "e.md")
    monkeypatch.setattr(ml, "triage", lambda subject, texts: (True, "asks a price"))
    calls, replies = [], []

    def fake_run(cmd, **kw):
        calls.append(cmd[1])
        code, out = replies.pop(0)
        return SimpleNamespace(args=cmd, returncode=code, stdout=out, stderr="")
    monkeypatch.setattr(ml.subprocess, "run", fake_run)

    replies[:] = [(3, "accepted: relay r1 via h (d)\npending host turn running\n")]
    assert ml.poll_case(case, account, False) is None and case["seen"] == ["a"] and case["pending"]["rid"] == "r1"
    replies[:] = [(3, "pending host turn running\n")]
    assert ml.poll_case(case, account, False) is None and calls[-1] == "status"     # waits, never resends
    replies[:] = [(0, "ok t1\n")]
    assert ml.poll_case(case, account, False) is None and case["seen"] == ["a", "e"] and "pending" not in case

    case["seen"] = ["a"]
    replies[:] = [(1, "accepted: relay r2 via h (d)\nfailed host turn error\n"), (0, "accepted: relay r3 via h (d)\nok t1\n")]
    assert ml.poll_case(case, account, False) == "t3" and case["seen"] == ["a"]
    assert ml.poll_case(case, account, False) is None and case["seen"] == ["a", "e"]
    replies[:] = [(1, "no usable relay host\n")]
    case["seen"] = ["a"]
    assert ml.poll_case(case, account, False) == "t3" and "pending" not in case


def test_triage_skip_marks_seen_without_waking(monkeypatch, tmp_path):
    case = {"gmail_thread": "g1", "owner": "t1", "account": "ann@example.com", "seen": ["a"], "subject": "Deal"}
    ooo = {**msg("o"), "payload": {"headers": [{"name": "From", "value": "b@v.test"},
                                               {"name": "Subject", "value": "Out of office"}]}}
    gmail = SimpleNamespace(get=lambda mid: ooo if mid == "o" else msg(mid),
                            view=lambda m, trim: {"headers": {}, "attachments": [], "body": "thanks!"})
    monkeypatch.setattr(ml, "workspace", lambda config: SimpleNamespace(gmail=gmail))
    monkeypatch.setattr(ml, "t3_lookup", lambda tid: (tid, {"title": "Deal"}))
    monkeypatch.setattr(ml, "save_texts", lambda *a, **kw: tmp_path / "s.md")
    monkeypatch.setattr(ml, "relay", lambda *a: pytest.fail("a skipped mail never pings"))
    monkeypatch.setattr(ml, "thread_metadata", lambda ws, gid: {"messages": [msg("a"), ooo]})
    monkeypatch.setattr(ml, "triage", lambda *a: pytest.fail("auto-replies skip the model"))
    assert ml.poll_case(case, {"config": "c"}, False) is None and case["seen"] == ["a", "o"]
    monkeypatch.setattr(ml, "thread_metadata", lambda ws, gid: {"messages": [msg("a"), ooo, msg("t")]})
    monkeypatch.setattr(ml, "triage", lambda subject, texts: (len(texts) == 1 or pytest.fail("OOO not sent")) and (False, "thanks only"))
    assert ml.poll_case(case, {"config": "c"}, False) is None and case["seen"] == ["a", "o", "t"]


def test_one_failing_case_keeps_the_others_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path))
    (tmp_path / "userdata").mkdir()
    cases = {k: {"account": "a@x", "gmail_thread": k, "owner": "t", "subject": "", "seen": [],
                 "claimed_at": datetime.now(timezone.utc).isoformat()} for k in ("ok", "boom")}
    (tmp_path / "userdata/mail-watch.json").write_text(json.dumps(
        {"cursor": 5, "accounts": {"a@x": {"config": "c"}}, "cases": cases}))
    monkeypatch.setattr(ml, "scan_events", lambda cursor: ([], cursor))
    monkeypatch.setattr(ml, "notify", lambda text: None)

    def poll_case(case, account, dry_run):
        if case["gmail_thread"] == "boom":
            raise RuntimeError("attachment fetch failed")
        case["seen"].append("woken")
    monkeypatch.setattr(ml, "poll_case", poll_case)
    assert ml.main(["poll"]) == 1
    saved = json.loads((tmp_path / "userdata/mail-watch.json").read_text())
    assert saved["cases"]["ok"]["seen"] == ["woken"]  # persisted: no second wake next run
