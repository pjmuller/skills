"""t3-mail-link pure logic: Gmail ref parsing, Chrome titles, new-inbound detection, link dedupe."""
import importlib.machinery
import importlib.util
from pathlib import Path

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
