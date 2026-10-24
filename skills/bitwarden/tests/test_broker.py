"""Drives the compiled broker's test build (fake Keychain/enclave/hidden panel) against a fake `bw serve`."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bw_once  # noqa: E402  (the re-copy client must find the broker's socket)

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="the broker is a macOS Swift binary")
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HOST = "admin.example.com"
SECRET_A, SECRET_B = "fixture-secret-vault-a", "fixture-secret-vault-b"
MASTER = {"testa": "fixture-master-a", "testb": "fixture-master-b"}
ID_A, ID_B = "12345678-1234-1234-1234-123456789abc", "abcdef12-1234-1234-1234-123456789abc"


def login(item_id, secret, username, host=HOST, name="Example"):
    return {"id": item_id, "type": 1, "name": name, "notes": "private note",
            "login": {"username": username, "password": secret, "totp": "private-seed",
                      "uris": [{"uri": f"https://{host}/login"}]}}


FAKE_SERVE = r'''
import json, os, pathlib, socket, sys
root = pathlib.Path(os.environ["BITWARDENCLI_APPDATA_DIR"])
cfg = json.loads((root / "config.json").read_text())
statefile = root / "state"
state = json.loads(statefile.read_text()) if statefile.exists() else {"locked": True}
log = (root / "events").open("a")
log.write(json.dumps({"start": sys.argv[1:], "env": sorted(os.environ)}) + "\n"); log.flush()
if sys.argv[1:] != ["serve", "--hostname", "fd+connected://3"]: sys.exit(9)
sock = socket.socket(fileno=3)
buf = b""
while True:
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk: sys.exit(0)
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    lines = head.decode().split("\r\n")
    method, path, _ = lines[0].split(" ")
    headers = {l.split(":", 1)[0].lower(): l.split(":", 1)[1].strip() for l in lines[1:]}
    size = int(headers.get("content-length", "0"))
    while len(rest) < size: rest += sock.recv(65536)
    body, buf = rest[:size], rest[size:]
    data = json.loads(body) if body else {}
    log.write(json.dumps({"method": method, "path": path, "host": headers.get("host"), "keys": sorted(data),
                          "locked": state["locked"]}) + "\n"); log.flush()
    code, reply = 200, {"success": True}
    if headers.get("host") != "localhost:8087": code, reply = 403, {"success": False}
    elif path == "/status":
        status = "unauthenticated" if cfg.get("logged_out") else "locked" if state["locked"] else "unlocked"
        reply["data"] = {"object": "template", "template": {"status": status, "userEmail": cfg["email"]}}
    elif path == "/unlock":
        if data.get("password") == cfg["password"]:
            state["locked"] = False
            if cfg.get("hang_after_unlock"):  # Unlocked inside bw, but the answer never arrives in time.
                statefile.write_text(json.dumps(state)); import time; time.sleep(4)
        else: code, reply = 400, {"success": False, "message": "Invalid master password."}
    elif path == "/lock":
        if not cfg.get("fail_lock"): state["locked"] = True
    elif state["locked"]: code, reply = 400, {"success": False, "message": "Vault is locked."}
    elif path == "/list/object/items": reply["data"] = {"object": "list", "data": cfg["items"]}
    elif path.startswith("/object/totp/"): reply["data"] = {"object": "string", "data": "123456"}
    elif path != "/sync": code, reply = 404, {"success": False}
    statefile.write_text(json.dumps(state))
    out = json.dumps(reply).encode()
    sock.sendall(b"HTTP/1.1 %d X\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % (code, len(out)) + out)
'''


@pytest.fixture(scope="session")
def broker(tmp_path_factory):
    build = tmp_path_factory.mktemp("broker")
    subprocess.run(["xcrun", "swiftc", "-D", "BW_BROKER_TEST", str(SCRIPTS / "broker.swift"), "-o",
                    str(build / "bw-broker")], check=True, capture_output=True)
    (build / "bw").write_text(f"#!{sys.executable}\n" + FAKE_SERVE)
    (build / "bw").chmod(0o700)
    return build


@pytest.fixture
def world(broker, tmp_path):
    home = tmp_path / "home"
    sockets = Path(tempfile.mkdtemp(prefix="bwp", dir="/tmp"))  # AF_UNIX paths are capped at 104 bytes.
    vaults = {}
    for name, email, items in (("testa", "a@example.com", [login(ID_A, SECRET_A, "alice")]),
                               ("testb", "b@example.com", [])):
        appdata = tmp_path / name
        appdata.mkdir()
        (appdata / "config.json").write_text(json.dumps({"email": email, "password": MASTER[name], "items": items}))
        vaults[name] = {"name": name, "email": email, "appdata": str(appdata)}
    (broker / "clip").unlink(missing_ok=True)

    def configure(name, **values):
        path = Path(vaults[name]["appdata"]) / "config.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), **values}))

    def run(op, touch="ok", typed=None, names=("testa", "testb"), extra_env=None, **fields):
        env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "BW_BROKER_TEST_BW": str(broker / "bw"), "BW_BROKER_TEST_TIMEOUT": "2",
               "BW_BROKER_TEST_STORE": str(tmp_path / "store.json"), "BW_BROKER_TEST_TOUCH": touch,
               "BW_BROKER_TEST_TYPE": json.dumps(typed or {}), "BW_BROKER_TEST_SOCKDIR": str(sockets),
               "BW_BROKER_TEST_RECOPY_SECONDS": "0", **(extra_env or {})}
        request = {"op": op, "vaults": [vaults[n] for n in names], **fields}
        done = subprocess.run([str(broker / "bw-broker")], input=json.dumps(request).encode(), env=env,
                              capture_output=True, timeout=60)
        return json.loads(done.stdout), done.stderr.decode()

    def start(op, typed=None, names=("testa", "testb"), extra_env=None, **fields):
        """Like run, but returns the live process after its first answer (the pick flow keeps running)."""
        env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "BW_BROKER_TEST_BW": str(broker / "bw"), "BW_BROKER_TEST_TIMEOUT": "2",
               "BW_BROKER_TEST_STORE": str(tmp_path / "store.json"), "BW_BROKER_TEST_TOUCH": "ok",
               "BW_BROKER_TEST_TYPE": json.dumps(typed or {}), "BW_BROKER_TEST_SOCKDIR": str(sockets), **(extra_env or {})}
        child = subprocess.Popen([str(broker / "bw-broker")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=env)
        child.stdin.write(json.dumps({"op": op, "vaults": [vaults[n] for n in names], **fields}).encode())
        child.stdin.close()
        return child, json.loads(child.stdout.readline())

    def pick(token, item):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(sockets / f"pick-{token}.sock"))
        client.sendall(json.dumps({"id": item}).encode() + b"\n")
        answer = client.makefile().readline()
        client.close()
        return json.loads(answer)

    def events(name):
        path = Path(vaults[name]["appdata"]) / "events"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def locked(name):
        state = Path(vaults[name]["appdata"]) / "state"
        return not state.exists() or json.loads(state.read_text())["locked"]

    def clip():
        path = broker / "clip"
        return path.read_text() if path.exists() else None

    def unclip():
        (broker / "clip").unlink(missing_ok=True)

    return {"run": run, "start": start, "unclip": unclip, "pick": pick, "sockets": sockets, "configure": configure, "events": events, "locked": locked, "clip": clip, "store": tmp_path / "store.json"}


def enroll(world):
    result, _ = world["run"]("enroll", typed=MASTER)
    assert result == {"ok": True, "enrolled": ["testa", "testb"]}


def test_enroll_verifies_each_password_and_stores_phrase(world):
    enroll(world)
    stored = json.loads(world["store"].read_text())
    assert len(stored["phrase"].split()) == 3 and stored["vaults"] == [
        {"name": "testa", "email": "a@example.com"}, {"name": "testb", "email": "b@example.com"}]
    assert all(world["locked"](name) for name in MASTER)
    for name in MASTER:
        paths = [e.get("path") for e in world["events"](name)]
        assert "/unlock" in paths and paths[-2:] == ["/lock", "/status"]


def test_enroll_rejects_a_wrong_password_and_stores_nothing(world):
    result, _ = world["run"]("enroll", typed={**MASTER, "testb": "wrong"})
    assert result == {"ok": False, "error": "Bitwarden rejected the master password for testb"}
    assert not world["store"].exists() and all(world["locked"](name) for name in MASTER)


def test_copy_searches_all_vaults_shows_claim_and_facts_and_locks_before_delivery(world):
    enroll(world)
    world["configure"]("testa", items=[])
    world["configure"]("testb", items=[login(ID_B, SECRET_B, "bob")])
    result, panel = world["run"]("copy", host=HOST, field="password", thread="Invoice run", why="download October invoices")
    assert result["ok"] and result["vault"] == "testb" and result["username"] == "bob" and result["copied"] == "password"
    assert world["clip"]() == SECRET_B
    phrase = json.loads(world["store"].read_text())["phrase"]
    assert phrase in panel and "AGENT SAYS (unverified)" in panel and "Invoice run" in panel
    assert "download October invoices" in panel and HOST in panel and "testa, testb" in panel
    assert all(world["locked"](name) for name in MASTER)
    assert SECRET_B not in json.dumps(result) and SECRET_B not in panel and MASTER["testb"] not in panel


def test_several_logins_lock_first_then_the_agent_picks_one(world):
    enroll(world)
    world["configure"]("testb", items=[login(ID_B, SECRET_B, "bob")])
    child, answer = world["start"]("copy", host=HOST, field="password")
    candidates = answer["pick"]["candidates"]
    assert [(c["vault"], c["username"]) for c in candidates] == [("testa", "alice"), ("testb", "bob")]
    assert all(world["locked"](name) for name in MASTER) and world["clip"]() is None  # Locked before the pick.
    assert SECRET_A not in json.dumps(answer) and SECRET_B not in json.dumps(answer)
    assert world["pick"](answer["pick"]["token"], "00000000-0000-0000-0000-000000000000")["ok"] is False
    released = world["pick"](answer["pick"]["token"], ID_B)
    assert released["ok"] and released["vault"] == "testb" and world["clip"]() == SECRET_B
    assert child.wait(10) == 0 and "Agent picked Example (bob, testb)" in child.stderr.read().decode()


def test_nothing_released_after_the_front_end_stopped_waiting(world):
    enroll(world)
    result, _ = world["run"]("copy", host=HOST, field="password", extra_env={"BW_BROKER_TEST_ANSWER_SECONDS": "0"})
    assert result["ok"] is False and "nothing released" in result["error"]
    assert world["clip"]() is None and all(world["locked"](name) for name in MASTER)


def test_no_pick_in_time_releases_nothing(world):
    enroll(world)
    world["configure"]("testb", items=[login(ID_B, SECRET_B, "bob")])
    child, answer = world["start"]("copy", host=HOST, field="password", extra_env={"BW_BROKER_TEST_PICK_SECONDS": "1"})
    assert child.wait(10) == 1 and world["clip"]() is None and "pick" in answer


def test_username_still_selects_directly(world):
    enroll(world)
    world["configure"]("testb", items=[login(ID_B, SECRET_B, "bob")])
    result, _ = world["run"]("copy", host=HOST, field="password", username="ALICE")
    assert result["ok"] and result["vault"] == "testa" and world["clip"]() == SECRET_A
    result, _ = world["run"]("copy", host=HOST, field="password", username="nobody")
    assert result["ok"] is False and "testa/Example/alice" in result["error"]


def test_list_returns_metadata_only(world):
    enroll(world)
    world["configure"]("testb", items=[login(ID_B, SECRET_B, "bob", host="other.example.com")])
    result, _ = world["run"]("list", host=HOST)
    assert result["items"] == [{"vault": "testa", "id": ID_A, "name": "Example", "username": "alice", "host": HOST}]
    assert "private" not in json.dumps(result) and SECRET_A not in json.dumps(result)
    world["configure"]("testb", items=[login(ID_B, SECRET_B, "bob")])
    result, panel = world["run"]("list", host=HOST, username="BOB")
    assert [item["username"] for item in result["items"]] == ["bob"] and "with username bob" in panel


def test_keychain_prompt_after_a_rebuild_is_explained_before_the_request(world):
    enroll(world)
    assert "keychain_prompt" not in world["run"]("status")[0]
    rebuilt = {"BW_BROKER_TEST_KEYCHAIN_PROMPT": "1"}
    assert world["run"]("status", extra_env=rebuilt)[0]["keychain_prompt"] is True
    result, panel = world["run"]("copy", host=HOST, field="password", username="alice", extra_env=rebuilt)
    assert result["ok"] and panel.index("Always Allow") < panel.index("AGENT SAYS")


def recopy(request, thread, vaults=("testa", "testb")):
    return bw_once.via_recopy({"op": "copy", "host": HOST, "field": "password", "id": None, "username": None,
                               **request}, thread, [{"name": name} for name in vaults])


def test_same_thread_recopies_the_released_login_without_a_touch(world, monkeypatch):
    enroll(world)
    monkeypatch.setattr(bw_once, "cache_dir", lambda: world["sockets"])
    child, result = world["start"]("copy", host=HOST, field="password", username="alice", thread="Sign-in",
                                   extra_env={"BW_BROKER_TEST_RECOPY_SECONDS": "3"})
    assert result["ok"] and "recopy_until" in result and world["clip"]() == SECRET_A
    world["unclip"]()
    assert recopy({"id": ID_A}, "Other thread") is None
    assert recopy({"id": ID_A, "field": "username"}, "Sign-in") is None
    assert recopy({"id": ID_B}, "Sign-in") is None and recopy({}, "Sign-in") is None
    assert recopy({"id": ID_A}, "Sign-in", vaults=("testb",)) is None and world["clip"]() is None
    again = recopy({"username": "Alice"}, "Sign-in")
    assert again["ok"] and again["touch"] is False and again["id"] == ID_A and world["clip"]() == SECRET_A
    assert SECRET_A not in json.dumps(again) and all(world["locked"](name) for name in MASTER)
    assert child.wait(15) == 0 and not list(world["sockets"].glob("recopy-*.sock"))
    stderr = child.stderr.read().decode()
    assert stderr.count("touch:") == 1 and "Re-copies" in stderr and "re-copies end" in stderr
    assert recopy({"id": ID_A}, "Sign-in") is None  # Expired.


def recopy_client(world, thread="Sign-in"):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(bw_once.recopy_socket(HOST, "password", thread)))
    ask = json.dumps({"host": HOST, "field": "password", "thread": thread, "username": "alice",
                      "vaults": ["testa", "testb"]}).encode() + b"\n"
    return client, ask


def test_a_trickled_recopy_request_cannot_outlive_the_deadline(world, monkeypatch):
    enroll(world)
    monkeypatch.setattr(bw_once, "cache_dir", lambda: world["sockets"])
    child, _ = world["start"]("copy", host=HOST, field="password", username="alice", thread="Sign-in",
                              extra_env={"BW_BROKER_TEST_RECOPY_SECONDS": "2"})
    world["unclip"]()
    client, ask = recopy_client(world)
    import time
    client.sendall(ask[:10]); time.sleep(1.2); client.sendall(ask[10:20]); time.sleep(1.2)
    try:
        client.sendall(ask[20:])
        late = client.makefile().readline()
    except OSError:
        late = ""
    assert (not late or json.loads(late)["ok"] is False) and world["clip"]() is None and child.wait(15) == 0


def test_a_replaced_holder_never_overwrites_the_newer_copy(world, monkeypatch):
    enroll(world)
    monkeypatch.setattr(bw_once, "cache_dir", lambda: world["sockets"])
    old, _ = world["start"]("copy", host=HOST, field="password", username="alice", thread="Sign-in",
                            extra_env={"BW_BROKER_TEST_RECOPY_SECONDS": "10"})
    client, ask = recopy_client(world)
    client.sendall(ask[:10])  # Accepted by the old holder, request not finished yet.
    world["configure"]("testa", items=[login(ID_A, "changed-secret", "alice")])
    new, _ = world["start"]("copy", host=HOST, field="password", username="alice", thread="Sign-in",
                            extra_env={"BW_BROKER_TEST_RECOPY_SECONDS": "2"})
    assert world["clip"]() == "changed-secret"
    client.sendall(ask[10:])
    assert json.loads(client.makefile().readline())["ok"] is False and world["clip"]() == "changed-secret"
    assert old.wait(15) == 0 and new.wait(15) == 0


def test_picked_login_recopies_but_totp_and_threadless_copies_do_not(world, monkeypatch):
    enroll(world)
    monkeypatch.setattr(bw_once, "cache_dir", lambda: world["sockets"])
    world["configure"]("testb", items=[login(ID_B, SECRET_B, "bob")])
    child, answer = world["start"]("copy", host=HOST, field="password", thread="Sign-in",
                                   extra_env={"BW_BROKER_TEST_RECOPY_SECONDS": "2"})
    assert "recopy_until" in world["pick"](answer["pick"]["token"], ID_B)
    assert recopy({"id": ID_B}, "Sign-in")["vault"] == "testb" and recopy({"id": ID_A}, "Sign-in") is None
    assert child.wait(15) == 0
    for fields in ({"field": "totp", "username": "alice", "thread": "Sign-in"}, {"field": "password", "username": "alice"}):
        result, panel = world["run"]("copy", host=HOST, extra_env={"BW_BROKER_TEST_RECOPY_SECONDS": "60"}, **fields)
        assert result["ok"] and "recopy_until" not in result and "Re-copies" not in panel


def test_cancel_never_unlocks(world):
    enroll(world)
    before = {name: len(world["events"](name)) for name in MASTER}
    result, _ = world["run"]("copy", host=HOST, field="password", touch="cancel")
    assert result == {"ok": False, "error": "Request cancelled"} and world["clip"]() is None
    for name in MASTER:
        assert "/unlock" not in [e.get("path") for e in world["events"](name)[before[name]:]]
        assert world["locked"](name)


def test_changed_master_password_renews_that_vault_and_continues(world):
    enroll(world)
    world["configure"]("testa", password="new-master-a")
    result, panel = world["run"]("copy", host=HOST, field="password", typed={"testa": "new-master-a"})
    assert result["ok"] and world["clip"]() == SECRET_A
    assert "rejected the saved master password for testa" in panel
    result, _ = world["run"]("copy", host=HOST, field="password")  # Renewed: Touch ID only again.
    assert result["ok"]


def test_broken_seal_asks_all_passwords_once_and_continues(world):
    enroll(world)
    result, panel = world["run"]("copy", host=HOST, field="password", touch="broken-once", typed=MASTER)
    assert result["ok"] and world["clip"]() == SECRET_A
    assert "fingerprints changed" in panel and panel.count("Master password for") == 2
    assert all(world["locked"](name) for name in MASTER)


def test_lock_failure_releases_nothing(world):
    enroll(world)
    world["configure"]("testa", fail_lock=True)
    result, _ = world["run"]("copy", host=HOST, field="password")
    assert result["ok"] is False and "bw lock" in result["error"] and world["clip"]() is None


def test_bw_gets_a_fixed_environment(world):
    enroll(world)
    world["run"]("copy", host=HOST, field="password", extra_env={"NODE_OPTIONS": "--require /tmp/evil.js",
                                                                  "UNRELATED_SECRET": "x"})
    envs = [e["env"] for e in world["events"]("testa") if "env" in e]
    assert envs and all(set(env) <= {"PATH", "BW_NOINTERACTION", "HOME", "USER", "LOGNAME", "LANG", "TMPDIR",
                                     "BITWARDENCLI_APPDATA_DIR", "__CF_USER_TEXT_ENCODING",
                                     "LC_CTYPE"} for env in envs)  # LC_CTYPE: set by the fake's own Python.


def test_wrong_account_vault_is_reported_unavailable(world):
    enroll(world)
    world["configure"]("testb", email="someone-else@example.com")
    result, _ = world["run"]("copy", host=HOST, field="password")
    assert result["ok"] and result["vault"] == "testa"
    assert result["unavailable"] == [{"vault": "testb", "reason": "testb: CLI is signed in as another account"}]


@pytest.mark.parametrize("fields", [{"thread": "line\nbreak"}, {"why": "‮evil"}, {"host": "*.example.com"},
                                    {"field": "notes"}])
def test_request_validation(world, fields):
    request = {"host": HOST, "field": "password", **fields}
    result, _ = world["run"]("copy", **request)
    assert result["ok"] is False


def test_a_failed_lock_still_locks_every_other_vault(world):
    enroll(world)
    world["configure"]("testa", fail_lock=True)
    world["configure"]("testb", items=[login(ID_B, SECRET_B, "bob", host="other.example.com")])
    result, _ = world["run"]("copy", host=HOST, field="password")
    assert result["ok"] is False and world["clip"]() is None and world["locked"]("testb")


def test_lost_unlock_answer_during_setup_still_locks(world):
    world["configure"]("testa", hang_after_unlock=True)
    result, _ = world["run"]("enroll", typed=MASTER)
    assert result["ok"] is False and not world["store"].exists() and world["locked"]("testa")


def test_closing_the_panel_during_the_search_releases_nothing(world):
    enroll(world)
    result, _ = world["run"]("copy", host=HOST, field="password", extra_env={"BW_BROKER_TEST_CANCEL_AFTER_SEARCH": "1"})
    assert result == {"ok": False, "error": "Request cancelled"} and world["clip"]() is None
    assert all(world["locked"](name) for name in MASTER)


def test_phrase_is_new_only_before_the_first_save_then_stays(world):
    _, panel = world["run"]("enroll", typed=MASTER)
    phrase = json.loads(world["store"].read_text())["phrase"]
    assert "NEW phrase" in panel and phrase in panel
    _, panel = world["run"]("enroll", typed={"testa": MASTER["testa"]}, names=("testa",))
    assert "NEW phrase" not in panel and phrase in panel and json.loads(world["store"].read_text())["phrase"] == phrase
    _, panel = world["run"]("copy", host=HOST, field="password")
    assert phrase in panel


def test_unreadable_item_never_becomes_a_new_phrase(world):
    world["store"].write_text("not json")
    result, _ = world["run"]("enroll", typed=MASTER)
    assert result["ok"] is False and "nothing changed" in result["error"] and world["store"].read_text() == "not json"


def test_pick_window_discloses_agent_choice_and_late_or_totp_picks_fail(world):
    enroll(world)
    world["configure"]("testb", items=[login(ID_B, SECRET_B, "bob")])
    child, answer = world["start"]("copy", host=HOST, field="password", extra_env={"BW_BROKER_TEST_PICK_SECONDS": "1"})
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(world["sockets"] / f"pick-{answer['pick']['token']}.sock"))
    import time; time.sleep(1.5)  # Connected in time, but names the login too late.
    try:
        client.sendall(json.dumps({"id": ID_B}).encode() + b"\n")
        late = client.makefile().readline()
    except OSError:
        late = ""  # The broker already hung up: also a refusal.
    assert child.wait(10) == 1 and world["clip"]() is None and (not late or json.loads(late)["ok"] is False)
    assert not list(world["sockets"].glob("pick-*.sock"))  # Socket removed on every exit.
    assert "the agent picks one" in child.stderr.read().decode()
    result, _ = world["run"]("copy", host=HOST, field="totp")
    assert result["ok"] is False and "pass --username" in result["error"]
