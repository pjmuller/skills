"""Account inventory, Gmail reference parsing and the read-only multi-mailbox lookup (synthetic ids)."""

import json

import pytest

from gws_core import ApiError, ConfigError, WorkspaceError
from gws_core.accounts import GmailRef, MailNotFound, discover, load_inventory, locate, locate_any, parse_ref

T = 1866870901077892614  # synthetic decimal ids
M1, M2 = 1800000000000000001, 1800000000000000002


@pytest.mark.parametrize("ref, expected", [
    ("19e875318442de06", GmailRef(threads=("19e875318442de06",), messages=("19e875318442de06",))),
    ("gmail:19e875318442de06 ann@example.com", GmailRef(threads=("19e875318442de06",), messages=("19e875318442de06",))),
    ("https://mail.google.com/mail/u/0/#all/19E875318442DE06", GmailRef(threads=("19e875318442de06",))),
    (f"thread-f:{T}", GmailRef(threads=(format(T, "x"),))),
    (f"msg-f:{T}", GmailRef(messages=(format(T, "x"),))),
    (str(T), GmailRef(threads=(format(T, "x"),), messages=(format(T, "x"),))),
    (f"https://mail.google.com/mail/u/0/?ik=x&view=om&permmsgid=msg-f:{T}", GmailRef(messages=(format(T, "x"),))),
    ("https://mail.google.com/mail/u/0/?ik=x&view=om&permmsgid=msg-a:r-815", GmailRef(drafts=("r-815",))),
    (f"https://mail.google.com/mail/u/0/?view=pt&permthid=thread-f%3A{T}&simpl=msg-f%3A{M1}",
     GmailRef(threads=(format(T, "x"),), messages=(format(M1, "x"),))),
    # Print all of a thread you started: thread-a is no API id; the received copies in simpl= are.
    (f"https://mail.google.com/mail/u/1/?ik=x&view=pt&search=all&permthid=thread-a:r-7363&simpl=msg-f:{M1}"
     f"&simpl=msg-f:{M2}", GmailRef(messages=(format(M1, "x"), format(M2, "x")), ignored=("thread-a:r-7363",))),
    ("https://mail.google.com/mail/u/0/#inbox/FMfcgzQhWTsMxrbPlmQHFRGDvlgCtzdB",
     GmailRef(web="FMfcgzQhWTsMxrbPlmQHFRGDvlgCtzdB")),
])
def test_parse_ref(ref, expected):
    assert parse_ref(ref) == expected


@pytest.mark.parametrize("ref, message", [
    ("https://mail.google.com/mail/u/0/#inbox", "not a Gmail URL"),
    ("https://mail.google.com/mail/u/0/?view=pt&permthid=thread-a:r-7363", "never guessed"),
    ("", "not a Gmail URL"),
])
def test_parse_ref_refuses(ref, message):
    with pytest.raises(WorkspaceError, match=message):
        parse_ref(ref)


class Mailbox:
    """Workspace stand-in: Gmail profile + ids it holds; every call recorded."""

    def __init__(self, account, held=(), *, profile=None, fail=None):
        self.account, self.held, self.fail, self.calls, self.closed = account, dict(held), fail, [], False
        self.gmail = self
        self._profile = profile or account

    def profile(self):
        self.calls.append("profile")
        return {"emailAddress": self._profile}

    def api(self, method, url, **kw):
        self.calls.append((method, url.rsplit("/users/me/", 1)[1], kw.get("params")))
        assert method == "GET" and kw.get("params") == {"format": "minimal"}  # metadata only, never content
        if self.fail:
            raise ApiError(self.fail, method, url, "denied")
        kind, ident = url.rsplit("/", 2)[-2:]
        if ident not in self.held:
            raise ApiError(404, method, url, "Requested entity was not found.")
        thread = self.held[ident]
        return {"threads": {"id": thread}, "messages": {"threadId": thread},
                "drafts": {"message": {"threadId": thread}}}[kind]

    def close(self):
        self.closed = True


def test_locate_tries_candidates_in_order_and_separates_absent_from_errors():
    ref = parse_ref(f"https://x/?view=pt&permthid=thread-a:r-1&simpl=msg-f:{M1}&simpl=msg-f:{M2}")
    box = Mailbox("a@example.com", {format(M2, "x"): "t2"})
    assert locate(box, ref) == "t2"
    assert [c[1] for c in box.calls] == [f"messages/{format(M1, 'x')}", f"messages/{format(M2, 'x')}"]
    with pytest.raises(MailNotFound):
        locate(Mailbox("a@example.com"), ref)
    with pytest.raises(ApiError):  # 403 is unknown, never "not found"
        locate(Mailbox("a@example.com", fail=403), ref)


@pytest.fixture
def inventory(tmp_path, write_config):
    counter = iter(range(100))

    def build(*entries):
        rows = []
        for account, scopes, lookup in entries:
            path = write_config(account=account, scopes=scopes)
            target = tmp_path / f"w{next(counter)}" / "workspace.json"
            target.parent.mkdir()
            path.rename(target)
            rows.append({"config": str(target), "gmail_lookup": lookup})
        inv = tmp_path / "accounts.json"
        inv.write_text(json.dumps({"accounts": rows}))
        return load_inventory(inv)
    return build


READ = ["https://www.googleapis.com/auth/gmail.readonly"]


def test_locate_any_loops_until_the_mailbox_that_holds_it(inventory):
    accounts = inventory(("a@example.com", READ, True), ("b@example.com", READ, False),
                         ("c@example.com", ["https://www.googleapis.com/auth/gmail.compose"], True),
                         ("d@example.com", READ, True), ("e@example.com", READ, True))
    boxes = {"a@example.com": Mailbox("a@example.com"), "b@example.com": Mailbox("b@example.com", {"abc": "t"}),
             "d@example.com": Mailbox("d@example.com", {format(M1, "x"): "thread-d"}),
             "e@example.com": Mailbox("e@example.com")}
    hit = locate_any(parse_ref(f"msg-f:{M1}"), accounts, connect=lambda cfg: boxes[cfg.account])
    assert (hit.account.config.account, hit.gmail_thread, hit.workspace) == ("d@example.com", "thread-d",
                                                                           boxes["d@example.com"])
    assert [c["result"] for c in hit.checked] == ["not found", "skipped: no Gmail read scope configured", "match"]
    assert boxes["b@example.com"].calls == []  # no gmail_lookup permission: never touched
    assert boxes["e@example.com"].calls == []  # stops at the match
    assert boxes["a@example.com"].closed and not boxes["d@example.com"].closed
    assert boxes["d@example.com"].calls[0] == "profile"  # identity before any lookup


def test_locate_any_wrong_identity_and_errors_are_unknown_not_absent(inventory):
    accounts = inventory(("a@example.com", READ, True), ("b@example.com", READ, True))
    boxes = {"a@example.com": Mailbox("a@example.com", {"x": "t"}, profile="other@example.com"),
             "b@example.com": Mailbox("b@example.com")}
    with pytest.raises(WorkspaceError, match="unknown elsewhere") as exc:
        locate_any(parse_ref("19e875318442de06"), accounts, connect=lambda cfg: boxes[cfg.account])
    assert not isinstance(exc.value, MailNotFound)
    assert boxes["a@example.com"].calls == ["profile"]  # mismatched identity: no lookup at all


def test_locate_any_skipped_mailboxes_are_unknown_not_absent(inventory):
    accounts = inventory(("a@example.com", ["https://www.googleapis.com/auth/gmail.compose"], True))
    with pytest.raises(WorkspaceError, match="unknown elsewhere") as exc:
        locate_any(parse_ref("19e875318442de06"), accounts, connect=lambda cfg: pytest.fail("no read scope"))
    assert not isinstance(exc.value, MailNotFound)


def test_accounts_cli_refuses_an_explicit_account(write_config):
    from gws_core.cli import main
    with pytest.raises(SystemExit, match="takes no --config"):
        main(["--config", str(write_config()), "accounts", "locate", "19e875318442de06"])


def test_locate_any_all_absent_and_no_lookup_entries(inventory):
    accounts = inventory(("a@example.com", READ, True))
    with pytest.raises(MailNotFound, match="not in any lookup mailbox"):
        locate_any(parse_ref("19e875318442de06"), accounts, connect=lambda cfg: Mailbox(cfg.account))
    with pytest.raises(ConfigError, match="gmail_lookup"):
        locate_any(parse_ref("19e875318442de06"), inventory(("a@example.com", READ, False)),
                   connect=lambda cfg: pytest.fail("no permission, no connection"))


def test_inventory_keeps_broken_entries_and_rejects_unknown_keys(tmp_path):
    inv = tmp_path / "accounts.json"
    inv.write_text(json.dumps({"accounts": [{"config": "missing/workspace.json", "gmail_lookup": "yes"}]}))
    [broken] = load_inventory(inv)
    assert broken.config_path == tmp_path / "missing/workspace.json" and broken.error and not broken.gmail_lookup
    inv.write_text(json.dumps({"accounts": [{"config": "x", "token": "nope"}]}))
    with pytest.raises(ConfigError, match="allowed keys"):
        load_inventory(inv)
    with pytest.raises(ConfigError, match="no account inventory"):
        load_inventory(tmp_path / "absent.json")


def test_discover_reads_wrapper_configs_only(tmp_path, write_config):
    config = write_config(scopes=READ)
    (tmp_path / "repo/.agents/skills/mail").mkdir(parents=True)
    config.rename(tmp_path / "repo/.agents/skills/mail/workspace.json")
    (tmp_path / "repo/templates").mkdir()
    (tmp_path / "repo/templates/workspace.json").write_text('{"account": "x@example.com"}')
    (tmp_path / "other").mkdir()
    (tmp_path / "other/workspace.json").write_text('{"folders": []}')  # an editor's workspace file
    rows = discover([tmp_path])
    assert rows == [{"account": "team@example.com", "config": str(tmp_path / "repo/.agents/skills/mail/workspace.json"),
                     "gmail_read": True}]
