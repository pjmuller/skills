import base64
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("bw_once", SCRIPTS / "bw_once.py")
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)
macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="clipboard helper and broker are macOS-only")
ID = "12345678-1234-1234-1234-123456789abc"
SECRET = "fixture-password-never-output"
SESSION = "fixtureSessionKey123=="
ITEM = {"id": ID, "name": "Example", "type": 1, "notes": "private note", "fields": ["private field"],
        "login": {"username": "user", "password": SECRET, "totp": "private-seed",
                  "uris": [{"uri": "https://admin.example.com/login?key=private-query"}]}}

FAKE = r'''
import base64,json,os,pathlib,signal,sys,time
root=pathlib.Path(__file__).parent
config=json.loads((root/'config').read_text())
state=json.loads((root/'state').read_text()) if (root/'state').exists() else {'locked':False,'locks':0}
args=sys.argv[1:]
with (root/'events').open('a') as stream:
 stream.write(json.dumps({'args':args,'session':bool(os.environ.get('BW_SESSION')),'locked':state['locked'],
  'noninteractive':os.environ.get('BW_NOINTERACTION'),'leaked':os.environ.get('UNRELATED_SECRET'),
  'appdata':os.environ.get('BITWARDENCLI_APPDATA_DIR')})+'\n')
if args[0]=='lock':
 state['locks']+=1
 if config.get('fail_lock')==state['locks']:
  print(config['secret'],file=sys.stderr);sys.exit(1)
 state['locked']=True
 if config.get('cleanup_signal') and state['locks']==2:os.kill(os.getppid(),config['cleanup_signal'])
elif args[0]=='unlock':
 if config.get('deny') or state.get('refused',0)<config.get('deny_times',0):
  state['refused']=state.get('refused',0)+1;(root/'state').write_text(json.dumps(state))
  print(config['secret']);sys.exit(1)
 state['locked']=False
 print(config['session'])
elif args[0]=='status':
 print(json.dumps({'status':'unauthenticated' if config.get('logged_out') and not state.get('logged_in') else 'locked' if state['locked'] else 'unlocked','userId':'private-user','userEmail':config.get('email')}))
elif args[0]=='login':
 state['logged_in']=True;state['locked']=False;print(config['session'])
elif args[:2]==['config','server'] and len(args)==3:state['server']=args[2]
elif args[0]=='--version':print('2026.9.1')
elif args[0]=='sync':
 if not state['locked'] or os.environ.get('BW_SESSION'):sys.exit(5)
 if config.get('fail_sync'):print(config['secret']);sys.exit(1)
else:
 if state['locked'] or os.environ.get('BW_SESSION')!=config['session']:sys.exit(3)
 if config.get('delay'):time.sleep(config['delay'])
 if config.get('bad_json'):print(config['secret'])
 elif args[0]=='list':print(json.dumps(config.get('filtered_items',config['items']) if len(args)>2 else config['items']))
 elif args[:2]==['get','item']:print(json.dumps(config['item']))
 elif args[:2]==['get','totp']:print(config.get('totp','123456'))
 elif args==['send','--fullObject','create']:
  data=json.loads(base64.b64decode(sys.stdin.buffer.read()))
  (root/'send_payload').write_text(json.dumps(data))
  if config.get('fail_send'):print(config['secret'],file=sys.stderr);sys.exit(1)
  if data.get('file'):(root/'sent_bytes').write_bytes(pathlib.Path(data['file']['fileName']).read_bytes())
  print(json.dumps({'id':config['item']['id'],'accessUrl':'https://send.bitwarden.com/#fake/link',
   'key':'private-send-key','text':{'text':'private-send-text'},'expirationDate':data['expirationDate'],
   'deletionDate':data['deletionDate'],'maxAccessCount':data['maxAccessCount']}))
 else:sys.exit(4)
(root/'state').write_text(json.dumps(state))
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    directory = tmp_path / "fake"
    directory.mkdir()
    executable = directory / "bw"
    executable.write_text(f"#!{sys.executable}\n" + FAKE)
    executable.chmod(0o700)
    config = {"item": ITEM, "items": [ITEM], "secret": SECRET, "session": SESSION}
    (directory / "config").write_text(json.dumps(config))
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ["PATH"])
    monkeypatch.setattr(bw.Path, "home", classmethod(lambda _: tmp_path / "home"))
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-reach-child")

    def update(**values):
        config.update(values)
        (directory / "config").write_text(json.dumps(config))

    def events():
        return [json.loads(line) for line in (directory / "events").read_text().splitlines()]

    return directory, update, events


def request(op="copy", **values):
    return {"op": op, "vault": "default", "host": "admin.example.com", **({"id": ID, "field": "password"} if op == "copy" else {}), **values}


def test_fresh_unlock_lock_before_delivery_and_no_environment_or_result_leaks(fake, capsys):
    directory, _, events = fake
    delivered = []

    def deliver(secret):
        assert json.loads((directory / "state").read_text())["locked"]
        assert events()[-1]["args"] == ["status"]
        assert events()[-1]["session"]  # Verify locked even with the former key.
        delivered.append(secret)

    for _ in range(2):
        result = bw.transaction(bw.Vault(), request(), ask=lambda *_: True, deliver=deliver)
        assert result["copied"] == "password"
        assert SECRET not in json.dumps(result) and SESSION not in json.dumps(result)
    assert delivered == [SECRET, SECRET]
    assert sum(event["args"][0] == "unlock" for event in events()) == 2
    assert all(not event["leaked"] and SESSION not in str(event["args"]) for event in events())
    assert all(event["noninteractive"] is None for event in events() if event["args"][0] == "unlock")
    assert all(event["noninteractive"] == "true" for event in events() if event["args"][0] != "unlock")
    assert SECRET not in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["cancel", "deny", "initial-lock", "final-lock", "bad-json", "interrupt", "timeout"])
def test_no_delivery_on_failure_and_cleanup(fake, monkeypatch, mode, capsys):
    directory, update, events = fake
    if mode == "deny": update(deny=True)
    if mode == "initial-lock": update(fail_lock=1)
    if mode == "final-lock": update(fail_lock=2)
    if mode == "bad-json": update(bad_json=True)
    if mode == "timeout": update(delay=0.3)
    original = subprocess.run

    def run(args, **kwargs):
        if args[1:3] == ["get", "item"]:
            if mode == "interrupt": raise KeyboardInterrupt()
            if mode == "timeout": kwargs["timeout"] = 0.08
        return original(args, **kwargs)

    monkeypatch.setattr(bw.subprocess, "run", run)
    delivered = []
    with pytest.raises((bw.Failure, KeyboardInterrupt)):
        bw.transaction(bw.Vault(), request(), ask=lambda *_: mode != "cancel", deliver=delivered.append)
    assert delivered == []
    if mode not in ("initial-lock", "final-lock"):
        assert json.loads((directory / "state").read_text())["locked"]
        assert events()[-1]["args"] == ["status"]
    if mode in ("cancel", "initial-lock"):
        assert not any(event["args"][0] == "unlock" for event in events())
    assert SECRET not in capsys.readouterr().out


def test_matching_metadata_allowlist(fake):
    _, update, _ = fake
    wrong = {**ITEM, "login": {**ITEM["login"], "uris": [{"uri": "https://eviladmin.other.com"},
              {"uri": "https://admin.example.com.evil.test"}, {"uri": "https://admin.example.com@evil.test"}]}}
    update(items=[wrong, ITEM, {**ITEM, "type": 2}])
    result = bw.transaction(bw.Vault(), request("list"), ask=lambda *_: True)
    assert result == {"items": [{"id": ID, "name": "Example", "username": "user", "host": "admin.example.com", "matched_uri_host": "admin.example.com", "match_rule": "base_domain"}]}
    assert not any(secret in json.dumps(result) for secret in (SECRET, "private", "https", "totp", "fields"))


@pytest.mark.parametrize("change", [{"id": None}, {"id": "abcdef12-1234-1234-1234-123456789abc"}, {"type": 2},
                                   {"login": {**ITEM["login"], "uris": [{"uri": "https://wrong.other.com"}]}},
                                   {"login": {**ITEM["login"], "password": None}}])
def test_item_id_type_host_and_missing_field_rejected(fake, change):
    directory, update, _ = fake
    update(item={**ITEM, **change})
    with pytest.raises(bw.Failure):
        bw.transaction(bw.Vault(), request(), ask=lambda *_: True, deliver=lambda _: pytest.fail("delivered"))
    assert json.loads((directory / "state").read_text())["locked"]


OTHER = {**ITEM, "id": "abcdef12-1234-1234-1234-123456789abc", "login": {**ITEM["login"], "username": None}}


def test_copy_without_id_picks_by_username_in_one_unlock(fake):
    _, update, events = fake
    update(items=[OTHER, ITEM])
    delivered = []
    result = bw.transaction(bw.Vault(), request(id=None, username="USER"), ask=lambda *_: True,
                            deliver=delivered.append)
    assert delivered == [SECRET]
    assert result == {"copied": "password", "id": ID, "name": "Example", "username": "user",
                      "host": "admin.example.com", "clear_after_seconds": 30, "matched_uri_host": "admin.example.com", "match_rule": "base_domain"}
    assert sum(event["args"][0] == "unlock" for event in events()) == 1


@pytest.mark.parametrize("rule", [2, 3, 4, 5, 99])
def test_restrictive_rule_is_never_weakened_to_host(fake, rule):
    directory, update, _ = fake
    restricted = {**ITEM, "login": {**ITEM["login"], "uris": [{"uri": "https://admin.example.com/admin", "match": rule}]}}
    update(items=[restricted], item=restricted)
    with pytest.raises(bw.Failure):
        bw.transaction(bw.Vault(), request(id=None), ask=lambda *_: True,
                       deliver=lambda _: pytest.fail("delivered"))
    assert json.loads((directory / "state").read_text())["locked"]


@pytest.mark.parametrize("values", [{"id": None}, {"id": None, "username": "nobody"}, {"username": "nobody"}])
def test_ambiguous_missing_or_mismatched_username_never_delivers(fake, values):
    directory, update, _ = fake
    update(items=[OTHER, ITEM])
    with pytest.raises(bw.Failure):
        bw.transaction(bw.Vault(), request(**values), ask=lambda *_: True, deliver=lambda _: pytest.fail("delivered"))
    assert json.loads((directory / "state").read_text())["locked"]


@macos_only
def test_clear_only_reports_helper_verdict(monkeypatch, tmp_path):
    helper = tmp_path / "clipboard"
    helper.write_text("#!/bin/sh\n[ \"$1\" = --clear-if-ours ] && echo cleared\n")
    helper.chmod(0o700)
    monkeypatch.setattr(bw, "ROOT", tmp_path)
    assert bw.clear_clipboard() == {"ok": True, "cleared": True}
    helper.write_text("#!/bin/sh\necho surprise\n")
    with pytest.raises(bw.Failure):
        bw.clear_clipboard()


def test_unlock_deadline_restarts_at_human_approval(monkeypatch):
    alarms = []
    monkeypatch.setattr(bw.signal, "alarm", alarms.append)
    monkeypatch.setattr(bw, "confirm", lambda *_: alarms.append("asked") or True)
    assert bw.timed_confirm(request(), None) is True
    assert alarms == ["asked", bw.UNLOCK_SECONDS]
    # The launcher waits for every phase plus cleanup, inside a 10-minute agent tool call (osascript gets 15 s).
    assert 15 + bw.WAIT_SECONDS + bw.UNLOCK_SECONDS + bw.OPERATION_SECONDS + 20 < 600


def send_request(tmp_path, text="fixture send text"):
    source = tmp_path / "message.txt"
    source.write_text(text)
    return {"op": "send-text", "vault": "default", "input_file": str(source), "name": "Details", "views": 1}


def unlocks(events):
    return sum(event["args"][0] == "unlock" for event in events())


def sends(events):
    return sum(event["args"][:2] == ["send", "--fullObject"] for event in events())


def test_refused_unlock_is_retried_by_the_human_and_the_send_runs_once(fake, tmp_path):
    directory, update, events = fake
    update(deny_times=2)
    asked = []
    result = bw.transaction(bw.Vault(), send_request(tmp_path), ask=lambda *_: True,
                            again=lambda attempt, email: asked.append(attempt) or True)
    assert result["url"].startswith("https://") and asked == [1, 2]
    assert unlocks(events) == 3 and sends(events) == 1
    assert json.loads((directory / "state").read_text())["locked"]
    calls = [event["args"][0] for event in events()]
    assert calls[calls.index("unlock") + 1] == "status"  # Re-checked locked + account before the retry.


@pytest.mark.parametrize("again,attempts,message", [(lambda *_: True, bw.UNLOCK_ATTEMPTS, "refused"),
                                                    (lambda *_: False, 1, "Cancelled"), (None, 1, "refused")])
def test_refused_unlock_stops_at_the_limit_or_cancel_and_is_safe_to_ask_again(fake, tmp_path, capsys, again, attempts, message):
    directory, update, events = fake
    update(deny=True)
    with pytest.raises(bw.Failure, match=message) as caught:
        bw.transaction(bw.Vault(), send_request(tmp_path), ask=lambda *_: True, again=again)
    assert caught.value.details == {"stage": "unlock", "retry_safe": True, "attempts": attempts}
    assert "Cryptography error" in str(caught.value) and "wrong" not in str(caught.value)
    assert unlocks(events) == attempts and sends(events) == 0
    assert json.loads((directory / "state").read_text())["locked"]
    assert SECRET not in str(caught.value) + capsys.readouterr().out


def test_failed_send_create_is_never_retried_and_says_so(fake, tmp_path, capsys):
    directory, update, events = fake
    update(fail_send=True)
    with pytest.raises(bw.Failure) as caught:
        bw.transaction(bw.Vault(), send_request(tmp_path), ask=lambda *_: True, again=lambda *_: True)
    assert caught.value.details == {"stage": "operation", "retry_safe": False}
    assert unlocks(events) == 1 and sends(events) == 1
    assert json.loads((directory / "state").read_text())["locked"]
    assert SECRET not in str(caught.value) + capsys.readouterr().out


def test_read_only_operation_failure_and_lock_failure_report_retry_safety(fake):
    directory, update, _ = fake
    update(item={**ITEM, "type": 2})
    with pytest.raises(bw.Failure) as caught:
        bw.transaction(bw.Vault(), request(), ask=lambda *_: True, deliver=lambda _: pytest.fail("delivered"))
    assert caught.value.details == {"stage": "operation", "retry_safe": True}
    (directory / "state").unlink()  # Lock counter restarts: the second lock (after the operation) fails.
    update(item=ITEM, fail_lock=2)
    with pytest.raises(bw.Failure) as caught:
        bw.transaction(bw.Vault(), request(), ask=lambda *_: True, deliver=lambda _: pytest.fail("delivered"))
    assert caught.value.details == {"stage": "lock", "retry_safe": False}


def test_retry_prompt_names_the_account_and_eof_cancels(monkeypatch, capsys):
    answers = iter(["", EOFError()])

    def getpass(prompt):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(bw.getpass, "getpass", getpass)
    assert bw.unlock_again(1, "a@example.com") is True
    assert bw.unlock_again(2, "a@example.com") is False
    out = capsys.readouterr().out
    assert "a@example.com" in out and "Mac login" in out and "Cryptography error" in out and "cancelled" in out


@pytest.mark.parametrize("answer,approved", [("", True), ("Y", True), ("n", False), (SECRET, False)])
def test_confirm_reads_hidden_and_discards_early_password(fake, monkeypatch, capsys, answer, approved):
    monkeypatch.setattr(bw.getpass, "getpass", lambda prompt: answer)
    assert bw.confirm(request(), None) is approved
    assert SECRET not in capsys.readouterr().out


def test_totp_generates_code_not_seed(fake):
    _, _, events = fake
    delivered = []
    bw.transaction(bw.Vault(), request(field="totp"), ask=lambda *_: True, deliver=delivered.append)
    assert delivered == ["123456"]
    assert ["get", "totp", ID] in [event["args"] for event in events()]


def test_sync_locked_before_human_approval_and_unlock(fake):
    _, _, events = fake

    def ask(*_):
        assert [event["args"] for event in events()] == [["lock"], ["status"], ["sync"], ["status"]]
        synced = next(event for event in events() if event["args"] == ["sync"])
        assert synced["locked"] and not synced["session"]
        return True

    bw.transaction(bw.Vault(), request("list"), ask=ask)


def test_failed_sync_never_unlocks_or_asks(fake):
    directory, update, events = fake
    update(fail_sync=True)
    with pytest.raises(bw.Failure):
        bw.transaction(bw.Vault(), request("list"), ask=lambda *_: pytest.fail("asked after sync failure"))
    assert not any(event["args"][0] == "unlock" for event in events())
    assert json.loads((directory / "state").read_text())["locked"]


SIGNAL_CHILD = r'''
import importlib.util, json, pathlib, signal, sys
spec = importlib.util.spec_from_file_location("bw_once", sys.argv[1])
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)
bw.Path.home = classmethod(lambda _: pathlib.Path(sys.argv[2]))
sig = int(sys.argv[3])
signal.signal(sig, bw.interrupted)
mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
vault = bw.Vault()
try:
    bw.transaction(vault, json.loads(sys.argv[4]), ask=lambda *_: True,
                   deliver=lambda _: sys.exit("released despite interruption"))
except bw.Failure as error:
    print(json.dumps({"error": str(error), "session": vault.session,
                      "mask_restored": signal.pthread_sigmask(signal.SIG_BLOCK, set()) == mask}))
'''


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGALRM])
def test_signal_during_final_lock_is_deferred_until_verification_and_session_clear(fake, tmp_path, sig):
    # Own single-threaded process: masks are per thread, and pytest-xdist worker threads take the signal unmasked.
    directory, update, events = fake
    update(cleanup_signal=int(sig))
    child = subprocess.run([sys.executable, "-c", SIGNAL_CHILD, str(SCRIPTS / "bw_once.py"), str(tmp_path / "home"),
                            str(int(sig)), json.dumps(request())], capture_output=True, text=True, timeout=60)
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    assert result["error"].startswith(("Cancelled with Ctrl-C", "Stopped", "Timed out"))
    assert result["session"] is None and result["mask_restored"]
    assert events()[-1]["args"] == ["status"] and events()[-1]["session"]
    assert json.loads((directory / "state").read_text())["locked"]


@pytest.mark.parametrize("uri", ["admin.example.com", "admin.example.com/login?key=fixture",
                                 "admin.example.com:443/login", "//admin.example.com/login", "https://ADMIN.example.com"])
def test_scheme_less_and_http_hosts_match_exactly(uri):
    assert bw.matching({**ITEM, "login": {"uris": [{"uri": uri}]}}, "admin.example.com")


@pytest.mark.parametrize("uri", ["admin.example.com.evil.test", "admin.example.com@evil.test",
                                 "eviladmin.other.com", "javascript://admin.example.com", "/admin.example.com"])
def test_scheme_less_near_matches_rejected(uri):
    assert not bw.matching({**ITEM, "login": {"uris": [{"uri": uri}]}}, "admin.example.com")


@pytest.mark.parametrize("op", ["send-text", "send-file"])
def test_send_snapshot_stdin_and_minimal_result(fake, tmp_path, op):
    directory, _, events = fake
    original = b"frozen fixture content"
    source = tmp_path / 'a;$(touch PWNED) "document".txt'
    source.write_bytes(original)

    def ask(request, payload, *_):
        source.write_bytes(b"changed after review")
        if op == "send-file":
            assert Path(payload["file"]["fileName"]).stat().st_mode & 0o777 == 0o600
            assert payload["_review"]["bytes"] == len(original)
        else:
            assert payload["text"]["text"] == original.decode()
        return True

    result = bw.transaction(bw.Vault(), {"op": op, "vault": "default", "input_file": str(source), "name": "Example", "views": 1}, ask=ask)
    payload = json.loads((directory / "send_payload").read_text())
    assert payload["maxAccessCount"] == 1
    assert payload["expirationDate"] == payload["deletionDate"]
    assert set(result) == {"id", "url", "expiry", "deletion", "views"}
    assert not any(value in json.dumps(result) for value in ("private-send", original.decode(), SESSION))
    assert next(event["args"] for event in events() if event["args"][0] == "send") == ["send", "--fullObject", "create"]
    if op == "send-file":
        assert (directory / "sent_bytes").read_bytes() == original
        assert not Path(payload["file"]["fileName"]).exists()
    else:
        assert payload["text"]["text"] == original.decode()


@pytest.mark.parametrize("content", [b"x" * 601, b"\xff", b""])
def test_send_bad_size_or_encoding_never_unlocks(fake, tmp_path, content):
    _, _, events = fake
    source = tmp_path / "input"
    source.write_bytes(content)
    with pytest.raises(bw.Failure):
        bw.transaction(bw.Vault(), {"op": "send-text", "vault": "default", "input_file": str(source), "name": "Example", "views": 1})
    assert not any(event["args"][0] == "unlock" for event in events())


def test_fifo_rejected_without_blocking(fake, tmp_path):
    source = tmp_path / "fifo"
    os.mkfifo(source)
    with pytest.raises(bw.Failure, match="regular file"):
        bw.transaction(bw.Vault(), {"op": "send-file", "vault": "default", "input_file": str(source), "name": "Example", "views": 1})


def test_injection_rejected_and_quoting_preserves_only_arguments(monkeypatch, tmp_path):
    monkeypatch.setenv("BW_SESSION", "do-not-use")
    with pytest.raises(bw.Failure): bw.reject_injection()
    assert "BW_SESSION" not in bw.clean_env()
    filename = str(tmp_path / "quote'$(touch PWNED);\nfile")
    words = shlex.split(bw.worker_command(filename))
    assert words[-1] == filename
    assert words[:3] == ["exec", "/usr/bin/env", "-i"]
    assert "BW_SESSION=do-not-use" not in words
    assert words[-4:] == ["-I", str(SCRIPTS / "bw_once.py"), "--worker", filename]
    assert shlex.split(bw.terminal_command(filename)) == ["exec", "/bin/sh", str(Path(filename) / "run.sh")]


def test_terminal_command_short_with_long_path_and_private_sanitized_script(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/" + "long-path-component/" * 200)
    monkeypatch.setenv("BW_SESSION", "must-not-inherit-session")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-inherit-secret")
    bw.private_launcher(tmp_path)
    script = tmp_path / "run.sh"
    assert script.stat().st_mode & 0o777 == 0o700
    assert len(bw.terminal_command(tmp_path)) < 512
    content = script.read_text()
    assert len(content) > 3000 and "must-not-inherit" not in content and "BW_SESSION" not in content
    assert shlex.split(content.splitlines()[1])[-1] == str(tmp_path)
    result = subprocess.run(["/bin/sh", str(script)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "real human macOS Terminal" in json.loads(result.stdout)["error"]


def test_status_is_read_only_and_safe(fake):
    directory, _, events = fake
    env = {key: value for key, value in os.environ.items() if not key.startswith(("BW_", "BITWARDENCLI_"))}
    output = subprocess.run([sys.executable, str(SCRIPTS / "bw_once.py"), "doctor"], env=env,
                            capture_output=True, text=True, check=True).stdout
    assert "private-user" not in output and SECRET not in output
    assert [event["args"] for event in events()] == [["status"], ["--version"], ["config", "server"]]
    assert not json.loads((directory / "state").read_text())["locked"]


def test_result_file_permissions_and_no_overwrite(tmp_path):
    target = tmp_path / "result"
    bw.private_json(target, {"ok": True})
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): bw.private_json(target, {"ok": False})


def test_mutex_refuses_contention(fake):
    with bw.mutex("default"):
        with pytest.raises(bw.Failure, match="Another"):
            with bw.mutex("default"): pytest.fail("concurrent request accepted")


@macos_only
def test_installer_copy_link_and_help_without_vault_access(fake, tmp_path):
    directory, _, _ = fake
    for name, text in {"uname": "echo Darwin", "xcrun": 'while [ "$1" != -o ]; do shift; done; shift; printf "#!/bin/sh\\nexit 0\\n" > "$1"',
                       "uv": "shift 3\nexec " + shlex.quote(sys.executable) + ' "$@"'}.items():
        script = directory / name
        script.write_text("#!/bin/sh\n" + text + "\n")
        script.chmod(0o700)
    installer = str(SCRIPTS / "install")
    prefix = tmp_path / "install"
    environment = {**os.environ, "BW_ONCE_SKIP_CLI_DOWNLOAD": "1"}
    subprocess.run([installer, "--prefix", str(prefix)], check=True, capture_output=True, env=environment)
    subprocess.run([installer, "--prefix", str(prefix)], check=True, capture_output=True, env=environment)
    subprocess.run([installer, "--check", "--prefix", str(prefix)], check=True, capture_output=True, env=environment)
    command = prefix / "bin/bw-once"
    assert command.is_symlink()
    result = subprocess.run([str(command), "--help"], env=dict(os.environ, UV_PYTHON=sys.executable), capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    assert not (directory / "events").exists()


def start_session(fake, monkeypatch, request_values=None, ttl_seconds=None, deliver=None):
    import threading
    directory, _, events = fake
    short_dir = Path(tempfile.mkdtemp(prefix="bwo-", dir="/tmp"))  # macOS AF_UNIX paths max 104 bytes
    monkeypatch.setattr(bw, "session_socket", lambda _vault: short_dir / "s.sock")
    if ttl_seconds is not None:
        original_init = bw.Session.__init__

        def short(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.deadline = bw.time.monotonic() + ttl_seconds
        monkeypatch.setattr(bw.Session, "__init__", short)
    ready, announced, outcome = threading.Event(), {}, {}

    def announce(status):
        announced.update(status)
        ready.set()

    def run():
        try:
            outcome["result"] = bw.session_transaction(bw.Vault(), {"op": "session-start", "vault": "default", "ttl": 1,
                                                                  "hosts": ["admin.example.com"], **(request_values or {})}, ask=lambda *_: True,
                                                       announce=announce, deliver=deliver or (lambda _: None),
                                                       audit=outcome.setdefault("audit", []).append)
        except Exception as error:  # pragma: no cover - surfaced by the test
            outcome["error"] = error
        finally:
            ready.set()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(5)
    assert "error" not in outcome, repr(outcome.get("error"))
    return thread, announced, outcome


def test_session_serves_list_and_copy_without_new_unlock_then_locks_on_stop(fake, monkeypatch, capsys):
    directory, _, events = fake
    delivered = []
    thread, announced, outcome = start_session(fake, monkeypatch, deliver=delivered.append)
    assert announced["active"] and announced["hosts"] == ["admin.example.com"] and 0 < announced["remaining_seconds"] <= 60
    assert bw.via_session({"op": "session-status", "vault": "default"})["active"]
    listed = bw.via_session(request("list"))
    assert listed == {"ok": True, "via": "session", "items": [{"id": ID, "name": "Example", "username": "user",
                                                               "host": "admin.example.com", "matched_uri_host": "admin.example.com", "match_rule": "base_domain"}]}
    copied = bw.via_session(request())
    assert copied["ok"] and copied["copied"] == "password" and SECRET not in json.dumps(copied)
    assert delivered == [SECRET]
    assert not json.loads((directory / "state").read_text())["locked"]  # unlocked while the holder lives
    assert bw.via_session({"op": "send-text", "vault": "default", "input_file": "/x", "name": "n", "views": 1})["ok"] is False
    assert bw.via_session({"op": "session-stop", "vault": "default"}) == {"ok": True, "active": False, "locked": True}
    assert json.loads((directory / "state").read_text())["locked"]  # locked before the acknowledgement
    thread.join(5)
    assert outcome.get("result") == {"active": False} and "error" not in outcome
    assert json.loads((directory / "state").read_text())["locked"]
    assert events()[-1]["args"] == ["status"]
    assert sum(event["args"][0] == "unlock" for event in events()) == 1
    assert [line["op"] for line in outcome["audit"]] == ["list", "copy", "session-stop"]
    assert bw.via_session({"op": "session-status", "vault": "default"}) is None and not bw.session_socket("default").exists()
    assert SECRET not in capsys.readouterr().out and SECRET not in json.dumps(outcome["audit"])


def test_session_host_allowlist_and_expiry_lock(fake, monkeypatch):
    directory, _, events = fake
    thread, announced, outcome = start_session(fake, monkeypatch, {"hosts": ["other.example.com"]}, ttl_seconds=1.0)
    assert announced["hosts"] == ["other.example.com"]
    denied = bw.via_session(request())
    assert denied["ok"] is False and "allowlist" in denied["error"]
    assert not any(event["args"][:2] == ["get", "item"] for event in events())
    thread.join(5)
    assert not thread.is_alive() and outcome.get("result") == {"active": False}
    assert json.loads((directory / "state").read_text())["locked"]
    assert bw.via_session(request("list")) is None  # client falls back to the Terminal flow


def test_session_start_request_validation():
    with pytest.raises(bw.Failure):
        bw.validate({"op": "session-start", "vault": "default", "ttl": 0, "hosts": ["a.example.com"]})
    with pytest.raises(bw.Failure, match="exact hosts"):
        bw.validate({"op": "session-start", "vault": "default", "ttl": 60, "hosts": []})
    with pytest.raises(bw.Failure):
        bw.validate({"op": "session-start", "vault": "default", "ttl": bw.TTL_MAX_MINUTES + 1, "hosts": []})
    with pytest.raises(bw.Failure):
        bw.validate({"op": "session-start", "vault": "default", "ttl": 60, "hosts": ["*.example.com"]})
    assert bw.validate({"op": "session-start", "vault": "default", "ttl": 60, "hosts": ["B.example.com", "a.example.com"]})["hosts"] == [
        "a.example.com", "b.example.com"]
    assert bw.ttl_minutes("1h") == 60 and bw.ttl_minutes("45m") == 45 and bw.ttl_minutes("30") == 30
    with pytest.raises(bw.Failure):
        bw.ttl_minutes("1d")


def test_logged_out_cli_is_reported_as_login_needed_not_lock_failure(fake):
    _, update, events = fake
    update(logged_out=True)
    with pytest.raises(bw.Failure, match="--vault default login"):
        bw.transaction(bw.Vault(), request("list"), ask=lambda *_: pytest.fail("asked while logged out"))
    assert not any(event["args"][0] == "unlock" for event in events())


def write_vaults(tmp_path, vaults):
    path = tmp_path / "home" / ".config" / "bw-once" / "vaults.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vaults))


VAULTS = {"work": {"email": "work@example.com", "default": True},
          "dentai": {"email": "dentai@example.com", "appdata": "~/bw-dentai", "server": "https://vault.example.eu"}}


def test_vault_config_resolves_default_and_rejects_unknown(fake, tmp_path):
    assert bw.vault_config() == {"name": "default"}
    with pytest.raises(bw.Failure, match="No vaults configured"):
        bw.vault_config("dentai")
    write_vaults(tmp_path, VAULTS)
    assert bw.vault_config() == {"name": "work", "email": "work@example.com", "default_match": "base_domain"}
    assert bw.vault_config("dentai")["appdata"] == str(tmp_path / "home" / "bw-dentai")
    with pytest.raises(bw.Failure, match="choose --vault dentai|work"):
        bw.vault_config("personal")
    write_vaults(tmp_path, {**VAULTS, "dentai": {**VAULTS["dentai"], "server": "https://vault.example.com:8443/"}})
    assert bw.vault_config("dentai")["server"] == "https://vault.example.com:8443"
    write_vaults(tmp_path, {**VAULTS, "dentai": {**VAULTS["dentai"], "server": "http://evil.example"}})
    with pytest.raises(bw.Failure, match="https origin"):
        bw.vault_config("dentai")


def test_vault_uses_its_own_data_dir_and_refuses_another_account(fake, tmp_path):
    _, update, events = fake
    write_vaults(tmp_path, VAULTS)
    update(email="work@example.com")
    with pytest.raises(bw.Failure, match="another account"):
        bw.transaction(bw.Vault("dentai"), {**request("list"), "vault": "dentai"},
                       ask=lambda *_: pytest.fail("asked for the wrong account"))
    assert {event["appdata"] for event in events()} == {str(tmp_path / "home" / "bw-dentai")}
    assert not any(event["args"][0] == "unlock" for event in events())
    with pytest.raises(bw.Failure, match="does not match"):
        bw.transaction(bw.Vault("work"), {**request("list"), "vault": "dentai"}, ask=lambda *_: True)


def test_login_configures_server_logs_in_and_locks(fake, tmp_path):
    directory, update, events = fake
    write_vaults(tmp_path, VAULTS)
    update(logged_out=True, email="dentai@example.com")
    shown = []
    result = bw.login_transaction(bw.Vault("dentai"), {"op": "login", "vault": "dentai"},
                                  ask=lambda request, payload, account: shown.append(account) or True)
    assert result == {"vault": "dentai", "status": "locked"} and shown == ["dentai@example.com"]
    args = [event["args"] for event in events()]
    assert ["config", "server", "https://vault.example.eu"] in args
    login = args.index(["login", "dentai@example.com", "--raw"])
    assert ["lock"] in args[login:] and args[-1] == ["status"]
    assert json.loads((directory / "state").read_text())["locked"]
    with pytest.raises(bw.Failure, match="already logged in"):
        bw.login_transaction(bw.Vault("dentai"), {"op": "login", "vault": "dentai"}, ask=lambda *_: True)


def test_session_refuses_other_vault_and_reports_reason(fake):
    session = bw.Session(bw.Vault(), {"op": "session-start", "vault": "default", "ttl": 1, "hosts": ["admin.example.com"],
                                      "reason": "thread X: Sentry login"}, deliver=lambda _: None)
    assert session.status()["reason"] == "thread X: Sentry login" and session.status()["vault"] == "default"
    for other in (request("list"), {"op": "session-stop"}, {"op": "session-status"}):
        with pytest.raises(bw.Failure, match="does not match this session"):
            session.handle({**other, "vault": "other"})
    with pytest.raises(bw.Failure, match="Reason"):
        bw.validate({"op": "session-start", "vault": "default", "ttl": 1, "hosts": ["a.example.com"], "reason": "a\nb"})


def test_send_days_default_and_bounds(tmp_path):
    base = {"op": "send-text", "vault": "default", "input_file": str(tmp_path / "m.txt"), "name": "n", "views": 1}
    assert bw.validate(base)["days"] == bw.SEND_DAYS_DEFAULT
    assert bw.validate({**base, "days": 14})["days"] == 14
    for days in (0, bw.SEND_DAYS_MAX + 1, "14"):
        with pytest.raises(bw.Failure):
            bw.validate({**base, "days": days})


BROKER = """#!/bin/sh
cat > "$(dirname "$0")/broker-request.json"
cat "$(dirname "$0")/broker-reply.json"
"""


@pytest.fixture
def front(fake, monkeypatch, tmp_path):
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    (helpers / "bw-broker").write_text(BROKER)
    (helpers / "bw-broker").chmod(0o700)
    monkeypatch.setattr(bw, "ROOT", helpers)
    config = tmp_path / "home" / ".config" / "bw-once"
    config.mkdir(parents=True)
    (config / "vaults.json").write_text(json.dumps({"work": {"email": "a@example.com", "default": True},
                                                    "other": {"email": "b@example.com", "appdata": "/tmp/x"}}))
    launched = []
    monkeypatch.setattr(bw, "launch", lambda args: launched.append(args) or {"ok": True, "via": "terminal"})

    def run(*argv, enrolled=True, vaults=("other", "work")):
        (helpers / "broker-reply.json").write_text(json.dumps({"ok": True, "enrolled": enrolled, "vaults": list(vaults),
                                                               "copied": "password"}))
        monkeypatch.setattr(sys, "argv", ["bw-once", *argv])
        try:
            bw.main()
        except SystemExit:
            pass
        sent = helpers / "broker-request.json"
        return json.loads(sent.read_text()) if sent.exists() else None

    return run, launched


@macos_only
def test_enrolled_copy_goes_to_the_broker_with_claim_and_every_vault(front):
    run, launched = front
    sent = run("copy", "--host", "admin.example.com", "--username", "user", "--field", "password",
               "--thread", "Invoice run", "--why", "download invoices")
    assert sent == {"op": "copy", "host": "admin.example.com", "username": "user", "field": "password",
                    "thread": "Invoice run", "why": "download invoices", "to": "clipboard",
                    "vaults": [{"name": "other", "email": "b@example.com", "appdata": os.path.realpath("/tmp/x"), "default_match": "base_domain"},
                               {"name": "work", "email": "a@example.com", "default_match": "base_domain"}]}
    assert launched == []


def test_pick_answer_gets_fill_js_with_the_selector():
    answer = bw.with_fill_js({"ok": True, "copied": "totp", "fill_url": "http://127.0.0.1:5/t"}, None)
    assert "fill_url" not in answer and "one-time-code" in answer["fill_js"]
    assert '"#otp"' in bw.with_fill_js({"copied": "totp", "fill_url": "http://127.0.0.1:5/t"}, "#otp")["fill_js"]


def test_fill_js_fetches_into_the_field_and_returns_only_the_length():
    script = bw.fill_js("http://127.0.0.1:5/tok", "#pass'word")
    assert '"http://127.0.0.1:5/tok"' in script and '"#pass\'word"' in script
    assert "length: field.value.length" in script and "return value" not in script and "{ok: true, length" in script


@macos_only
def test_explicit_vault_restricts_the_broker_search(front):
    run, _ = front
    sent = run("--vault", "work", "list", "--host", "admin.example.com", "--username", "user")
    assert sent["vaults"] == [{"name": "work", "email": "a@example.com", "default_match": "base_domain"}] and sent["op"] == "list"
    assert sent["username"] == "user"


def test_not_enrolled_falls_back_to_the_terminal_without_claim_fields(front):
    run, launched = front
    run("copy", "--host", "admin.example.com", "--field", "password", "--why", "x", enrolled=False)
    assert len(launched) == 1 and "why" not in launched[0] and "thread" not in launched[0]


@macos_only
def test_enrolled_text_send_goes_to_the_broker_with_its_frozen_text_and_one_vault(front, tmp_path):
    run, launched = front
    source = tmp_path / "message.txt"
    source.write_text("fixture send text")
    sent = run("--vault", "other", "send-text", "--input-file", str(source), "--name", "Details", "--views", "2",
               "--thread", "Hand-over", "--why", "share access")
    assert sent == {"op": "send-text", "vaults": [{"name": "other", "email": "b@example.com",
                                                   "appdata": os.path.realpath("/tmp/x"), "default_match": "base_domain"}],
                    "name": "Details", "views": 2, "days": bw.SEND_DAYS_DEFAULT, "text": "fixture send text",
                    "thread": "Hand-over", "why": "share access"}
    assert launched == []


@macos_only
def test_file_send_and_unenrolled_vault_use_the_terminal(front, tmp_path):
    run, launched = front
    source = tmp_path / "message.txt"
    source.write_text("fixture send text")
    run("send-file", "--input-file", str(source), "--name", "Doc")
    run("send-text", "--input-file", str(source), "--name", "Doc", "--why", "x", vaults=("other",))
    assert [entry["op"] for entry in launched] == ["send-file", "send-text"]
    assert "why" not in launched[1] and launched[1]["vault"] == "work"


MATCHING_CASES = json.loads((Path(__file__).parent / "matching_cases.json").read_text())


@pytest.mark.parametrize("case", MATCHING_CASES)
def test_matching_contract(case):
    item = {"type": case.get("type", 1), "login": {"uris": [{"uri": case["uri"], "match": case["rule"]}]}}
    assert bw.matching(item, case["host"], case["default"]) == case["yes"]


def test_never_applies_only_to_its_uri():
    assert bw.matching({"type": 1, "login": {"uris": [
        {"uri": "https://accounts.google.com", "match": 5}, {"uri": "https://google.com", "match": 0}]}},
        "accounts.google.com")


def test_configured_default_restricts_both_frontend_and_broker_request(fake, tmp_path):
    fake[1](email="work@example.com")
    write_vaults(tmp_path, {"work": {"email": "work@example.com", "default": True, "default_match": "never"}})
    assert bw.vault_config()["default_match"] == "never"
    assert bw.broker_vaults()[0]["default_match"] == "never"
    with pytest.raises(bw.Failure):
        bw.transaction(bw.Vault(), {**request(), "vault": "work"}, ask=lambda *_: True,
                       deliver=lambda _: pytest.fail("delivered"))
    write_vaults(tmp_path, {"work": {"email": "work@example.com", "default": True, "default_match": "typo"}})
    with pytest.raises(bw.Failure, match="default_match"):
        bw.vault_config()


def test_changed_uri_rule_between_list_and_get_cannot_release(fake):
    directory, update, _ = fake
    update(item={**ITEM, "login": {**ITEM["login"], "uris": [{"uri": "https://admin.example.com", "match": 5}]}})
    with pytest.raises(bw.Failure):
        bw.transaction(bw.Vault(), request(id=None), ask=lambda *_: True,
                       deliver=lambda _: pytest.fail("delivered"))
    assert json.loads((directory / "state").read_text())["locked"]


def test_legacy_session_cannot_serve_copy_but_can_be_stopped(fake, monkeypatch):
    import socket
    import threading
    with tempfile.TemporaryDirectory(prefix="bwlegacy", dir="/tmp") as directory:
        monkeypatch.setattr(bw, "cache_dir", lambda: Path(directory))
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(Path(directory) / "session-default.sock"))
        server.listen(1)
        server.settimeout(5)
        received = []
        def serve():
            with server:
                connection, _ = server.accept()
                with connection:
                    received.append(json.loads(bw.read_line(connection)))
                    connection.sendall(b'{"ok":true,"locked":true}\n')
        thread = threading.Thread(target=serve)
        thread.start()
        assert bw.via_session(request()) is None
        assert bw.via_session({"op": "session-stop", "vault": "default"})["locked"]
        thread.join(5)
        assert received == [{"op": "session-stop", "vault": "default"}]


@pytest.mark.parametrize("contents", [None, "com\n"])
def test_missing_or_incomplete_psl_is_actionable_and_never_delivers(fake, monkeypatch, tmp_path, contents):
    directory, _, _ = fake
    vault = bw.Vault()
    if contents is not None:
        (tmp_path / "public_suffix_list.dat").write_text(contents)
    monkeypatch.setattr(bw, "ROOT", tmp_path)
    bw.suffix_rules.cache_clear()
    try:
        with pytest.raises(bw.Failure, match="Public Suffix List.*rerun installer"):
            bw.transaction(vault, request(id=None), ask=lambda *_: True,
                           deliver=lambda _: pytest.fail("delivered"))
        assert json.loads((directory / "state").read_text())["locked"]
    finally:
        bw.suffix_rules.cache_clear()


@macos_only
def test_interrupted_wait_for_a_touch_id_send_is_never_retry_safe(monkeypatch, tmp_path):
    (tmp_path / "bw-broker").write_text("#!/bin/sh\ncat >/dev/null\nsleep 2\n")
    (tmp_path / "bw-broker").chmod(0o700)
    monkeypatch.setattr(bw, "ROOT", tmp_path)

    def interrupted(*_):
        raise bw.Failure("Cancelled with Ctrl-C")
    monkeypatch.setattr(bw.select, "select", interrupted)
    with pytest.raises(bw.Failure, match="may exist") as caught:
        bw.broker({"op": "send-text", "vaults": []})
    assert caught.value.details == {"stage": "unknown", "retry_safe": False}
    with pytest.raises(bw.Failure, match="Ctrl-C") as caught:
        bw.broker({"op": "copy", "vaults": []})
    assert caught.value.details == {}


@macos_only
@pytest.mark.parametrize("op,safe", [("send-text", False), ("copy", True)])
def test_interrupted_terminal_wait_flags_a_possible_send(fake, monkeypatch, tmp_path, op, safe):
    directory, _, _ = fake
    (directory / "state").write_text(json.dumps({"locked": True, "locks": 0}))  # Launch checks locked first.

    def interrupted(_request):
        raise bw.Failure("Cancelled with Ctrl-C")  # E.g. during the worker cleanup wait.
    monkeypatch.setattr(bw, "wait_for_terminal", interrupted)
    with pytest.raises(bw.Failure) as caught:
        bw.launch(send_request(tmp_path) if op == "send-text" else request())
    assert caught.value.details == {"stage": "unknown", "retry_safe": safe}
