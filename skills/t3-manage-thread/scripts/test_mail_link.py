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
    for name in ("locked_state", "save_messages", "store", "t3_thread", "own_thread", "cmd_draft"):
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
    assert parsed == {"account": "ann@example.com", "gmail_thread": ml.parse_gmail_ref(ref)[1]}
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
