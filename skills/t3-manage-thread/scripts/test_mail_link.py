"""t3-mail-link pure logic: Gmail ref parsing, Chrome titles, new-inbound detection, link dedupe."""
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


@pytest.mark.parametrize("ref, expected", [
    ("19e875318442de06", ("hex", "19e875318442de06")),
    ("https://mail.google.com/mail/u/0/#all/19E875318442DE06", ("hex", "19e875318442de06")),
    ("thread-f:1866870901077892614", ("hex", format(1866870901077892614, "x"))),
    ("msg-f:1866870901077892614", ("hex", format(1866870901077892614, "x"))),
    ("1866870901077892614", ("hex", format(1866870901077892614, "x"))),
    ("https://mail.google.com/mail/u/0/?ik=abc123&view=om&permmsgid=msg-f:1866870901077892614",
     ("hex", format(1866870901077892614, "x"))),
    ("https://mail.google.com/mail/u/0/?ik=abc123&view=om&permmsgid=msg-a:r-8150541756871935074",
     ("draft", "r-8150541756871935074")),
    ("https://mail.google.com/mail/u/0/?ik=abc123&view=pt&search=all&permthid=thread-f%3A1866870901077892614&simpl=msg-f%3A1",
     ("hex", format(1866870901077892614, "x"))),
    ("https://mail.google.com/mail/u/0/#inbox/FMfcgzQhWTsMxrbPlmQHFRGDvlgCtzdB",
     ("web", "FMfcgzQhWTsMxrbPlmQHFRGDvlgCtzdB")),
    ("https://mail.google.com/mail/u/1/#label/Clients%2FAcme/FMfcgzQgMCgKhphcthGsbxmQxBCTXKMQ",
     ("web", "FMfcgzQgMCgKhphcthGsbxmQxBCTXKMQ")),
])
def test_parse_gmail_ref(ref, expected):
    assert ml.parse_gmail_ref(ref) == expected


def test_parse_gmail_ref_rejects_garbage():
    with pytest.raises(SystemExit):
        ml.parse_gmail_ref("https://mail.google.com/mail/u/0/#inbox")


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
               "deleted_at TEXT, archived_at TEXT)")
    db.execute("CREATE TABLE orchestration_v2_projection_turn_items (turn_item_id TEXT PRIMARY KEY, thread_id TEXT, "
               "type TEXT, status TEXT, payload_json TEXT)")
    db.executemany("INSERT INTO orchestration_v2_projection_threads VALUES (?, ?, ?, ?)", [
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

    for ignored in (event(owner="mcp:bbbbbbbb-0000-0000-0000-000000000002"),  # dispatch never owns
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
    monkeypatch.setitem(sys.modules, "gws_core", SimpleNamespace(ApiError=RuntimeError))
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
    gmail_id = ml.parse_gmail_ref(ref)[1]
    assert parsed == {"account": "ann@example.com", "gmail_thread": gmail_id,
                      "marker": f"Mail-ref: gmail:{gmail_id} ann@example.com"}
    resolver.whoami.assert_called_once_with()
    assert resolver.api.call_args.args[0] == "GET"
    resolver.gmail.get.assert_not_called()


def test_resolve_message_and_draft_are_reads(resolver, capsys):
    resolver.api.side_effect = RuntimeError("message id is not a thread id")
    resolver.gmail.get.return_value = {"threadId": "thread-from-message"}
    assert ml.main(["resolve", "19e875318442de06"]) == 0
    assert json.loads(capsys.readouterr().out)["gmail_thread"] == "thread-from-message"
    resolver.gmail.get.assert_called_once_with("19e875318442de06")
    resolver.gmail.get_draft.return_value = {"message": {"threadId": "thread-from-draft"}}
    assert ml.main(["resolve", "https://mail.google.com/mail/u/0/?permmsgid=msg-a:r-12"]) == 0
    assert json.loads(capsys.readouterr().out)["gmail_thread"] == "thread-from-draft"
    resolver.gmail.get_draft.assert_called_once_with("r-12")
    assert {call[0] for call in resolver.gmail.method_calls} == {"get", "get_draft"}


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
    hits = [hit("aaaaaaaa-1"), hit("bbbbbbbb-2"), hit("mcp:cccccccc-3", "Team dispatch"), legacy, hit("eeeeeeee-5")]
    peeks = {"bbbbbbbb-2": {"prompts": [{"text": "Execution thread: perform the task here."}]}}
    greps = {"aaaaaaaa-1": (False, True), "bbbbbbbb-2": (True, True)}
    owners, excluded = ml.classify_owners(hits, peeks, greps, ["eeeeeeee-5"], ["dddd"], "id")
    assert [(o["thread_id"], o["evidence"]) for o in owners] == [
        ("eeeeeeee-5", "owner"), ("bbbbbbbb-2", "marker"), ("aaaaaaaa-1", "id")]
    assert owners[1]["execution"] and owners[1]["account_seen"] and not owners[0]["account_seen"]
    assert [(x["thread_id"], x["why"]) for x in excluded] == [("mcp:cccccccc-3", "dispatcher"), ("thread:project:p1:dddddddd-4", "excluded")]


def test_find_is_read_only_and_falls_back_to_subject(resolver, monkeypatch, capsys):
    resolver.api.return_value = {"id": "19e875318442de06", "messages": [
        {"id": "19e875318442de06", "payload": {"headers": [{"name": "Subject", "value": "Re: Offer renewal 2027"}]}}]}
    calls = []

    def fake_find(*argv):
        calls.append(argv)
        if argv[0] == "search":
            return {"results": [hit("mcp:cccccccc-3", "PJ dispatch")] if "--all" not in argv else [hit("ffffffff-6")]}
        if argv[0] == "peek":
            return [{"thread_id": i, "prompts": []} for i in argv[1].split(",")]
        return {"snippets": []}

    monkeypatch.setattr(ml, "find_thread", fake_find)

    assert ml.main(["find", "thread-f:1866870901077892614", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["owners"] == [] and [t["evidence"] for t in report["topic"]] == ["topic"]
    assert [x["why"] for x in report["excluded"]] == ["dispatcher"]
    topic_search = next(c for c in calls if "--all" in c)
    assert topic_search[-3:] == ("offer", "renewal", "2027")
    assert all(c[1:3] == ("--backup", "on") or c[2:4] == ("--backup", "on") for c in calls if c[0] == "search")


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
