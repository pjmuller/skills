"""Drives the compiled broker's test build (fake Keychain/enclave/hidden panel) against a fake `bw serve`."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

import pytest

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
        env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "BW_BROKER_TEST_BW": str(broker / "bw"), "BW_BROKER_TEST_TIMEOUT": "1",
               "BW_BROKER_TEST_STORE": str(tmp_path / "store.json"), "BW_BROKER_TEST_TOUCH": touch,
               "BW_BROKER_TEST_TYPE": json.dumps(typed or {}), **(extra_env or {})}
        request = {"op": op, "vaults": [vaults[n] for n in names], **fields}
        done = subprocess.run([str(broker / "bw-broker")], input=json.dumps(request).encode(), env=env,
                              capture_output=True, timeout=60)
        return json.loads(done.stdout), done.stderr.decode()

    def start(op, typed=None, names=("testa", "testb"), extra_env=None, **fields):
        """Like run, but returns the live process after its first answer (the pick flow keeps running)."""
        env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "BW_BROKER_TEST_BW": str(broker / "bw"), "BW_BROKER_TEST_TIMEOUT": "1",
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

    return {"run": run, "start": start, "pick": pick, "sockets": sockets, "configure": configure, "events": events, "locked": locked, "clip": clip, "store": tmp_path / "store.json"}


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
