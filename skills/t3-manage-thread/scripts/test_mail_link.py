"""t3-mail-link pure logic: Gmail ref parsing, Chrome titles, new-inbound detection, link dedupe."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
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


def msg(mid, sender="bob@vendor.test", labels=("INBOX",)):
    return {"id": mid, "labelIds": list(labels), "payload": {"headers": [{"name": "From", "value": f"Bob <{sender}>"}]}}


def test_classify_new():
    messages = [msg("a"), msg("b", "Ann@Example.com", ("INBOX",)), msg("c", labels=("SENT",)),
                msg("d", labels=("DRAFT",)), msg("e")]
    assert ml.classify_new(messages, {"a"}, "ann@example.com") == (["e"], ["b", "c"])
    assert ml.baseline(messages) == ["a", "b", "c", "e"]


def test_upsert_dedupes_per_account_and_thread():
    state = {"links": []}
    assert ml.upsert(state, {"account": "a@x", "gmail_thread": "t1", "t3_thread": "one"}) is None
    assert ml.upsert(state, {"account": "b@x", "gmail_thread": "t1", "t3_thread": "two"}) is None
    old = ml.upsert(state, {"account": "a@x", "gmail_thread": "t1", "t3_thread": "three"})
    assert old["t3_thread"] == "one" and [l["t3_thread"] for l in state["links"]] == ["three", "two"]


def test_ping_text_is_shell_safe():
    link = {"subject": "Price `rm` $(x)", "account": "a@x", "gmail_thread": "t1", "config": "/c.json", "policy": None, "t3_thread": "id1"}
    text = ml.ping_text(link, Path("/tmp/m.md"), ["m1", "m2"])
    assert "`" not in text and "$(" not in text and "m2" in text and "UNTRUSTED" in text


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
    state = tmp_path / "userdata" / "mail-links.json"
    state.parent.mkdir(parents=True)
    state.write_text('{"links": [{"t3_thread": "a"}, {"t3_thread": "b"}, {"t3_thread": "a"}]}')
    assert ml.main(["list", "--thread-ids"]) == 0 and capsys.readouterr().out == "a\nb\n"


@pytest.fixture
def resolver(tmp_path, monkeypatch):
    """Offline Workspace reads; any T3 call, saved-mail or link-state write fails the test."""
    ws = Mock(config=SimpleNamespace(account="Ann@Example.com"))
    ws.whoami.return_value = {"email": "ANN@example.com"}
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path))
    monkeypatch.setenv("GWS_CONFIG", str(tmp_path / "workspace.json"))
    monkeypatch.setattr(ml, "workspace", lambda config: ws)
    monkeypatch.setitem(sys.modules, "gws_core", SimpleNamespace(ApiError=RuntimeError))
    for name in ("locked_state", "save_messages", "store", "t3_thread", "cmd_draft"):
        monkeypatch.setattr(ml, name, lambda *a, **kw: pytest.fail("resolve must not mutate or access T3"))
    monkeypatch.setattr(ml.subprocess, "run", lambda *a, **kw: pytest.fail("no subprocess in offline resolve"))
    state = tmp_path / "userdata/mail-links.json"
    state.parent.mkdir()
    state.write_text('{"links": [{"gmail_thread": "existing", "t3_thread": "keep"}]}')
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
        ("eeeeeeee-5", "linked"), ("bbbbbbbb-2", "marker"), ("aaaaaaaa-1", "id")]
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
