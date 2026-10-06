import base64
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("bw_once", SCRIPTS / "bw_once.py")
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)
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
  'noninteractive':os.environ.get('BW_NOINTERACTION'),'leaked':os.environ.get('UNRELATED_SECRET')})+'\n')
if args[0]=='lock':
 state['locks']+=1
 if config.get('fail_lock')==state['locks']:
  print(config['secret'],file=sys.stderr);sys.exit(1)
 state['locked']=True
 if config.get('cleanup_signal') and state['locks']==2:os.kill(os.getppid(),config['cleanup_signal'])
elif args[0]=='unlock':
 if config.get('deny'):
  print(config['secret']);sys.exit(1)
 state['locked']=False
 print(config['session'])
elif args[0]=='status':
 print(json.dumps({'status':'locked' if state['locked'] else 'unlocked','userId':'private-user'}))
elif args[0]=='--version':print('2026.9.1')
elif args[0]=='sync':
 if not state['locked'] or os.environ.get('BW_SESSION'):sys.exit(5)
 if config.get('fail_sync'):print(config['secret']);sys.exit(1)
else:
 if state['locked'] or os.environ.get('BW_SESSION')!=config['session']:sys.exit(3)
 if config.get('delay'):time.sleep(config['delay'])
 if config.get('bad_json'):print(config['secret'])
 elif args[0]=='list':print(json.dumps(config['items']))
 elif args[:2]==['get','item']:print(json.dumps(config['item']))
 elif args[:2]==['get','totp']:print(config.get('totp','123456'))
 elif args==['send','--fullObject','create']:
  data=json.loads(base64.b64decode(sys.stdin.buffer.read()))
  (root/'send_payload').write_text(json.dumps(data))
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
    return {"op": op, "host": "admin.example.com", **({"id": ID, "field": "password"} if op == "copy" else {}), **values}


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


def test_exact_host_metadata_allowlist(fake):
    _, update, _ = fake
    wrong = {**ITEM, "login": {**ITEM["login"], "uris": [{"uri": "https://eviladmin.example.com"},
              {"uri": "https://admin.example.com.evil.test"}, {"uri": "https://admin.example.com@evil.test"}]}}
    update(items=[wrong, ITEM, {**ITEM, "type": 2}])
    result = bw.transaction(bw.Vault(), request("list"), ask=lambda *_: True)
    assert result == {"items": [{"id": ID, "name": "Example", "username": "user", "host": "admin.example.com"}]}
    assert not any(secret in json.dumps(result) for secret in (SECRET, "private", "https", "totp", "fields"))


@pytest.mark.parametrize("change", [{"id": None}, {"id": "abcdef12-1234-1234-1234-123456789abc"}, {"type": 2},
                                   {"login": {**ITEM["login"], "uris": [{"uri": "https://wrong.example.com"}]}},
                                   {"login": {**ITEM["login"], "password": None}}])
def test_item_id_type_host_and_missing_field_rejected(fake, change):
    directory, update, _ = fake
    update(item={**ITEM, **change})
    with pytest.raises(bw.Failure):
        bw.transaction(bw.Vault(), request(), ask=lambda *_: True, deliver=lambda _: pytest.fail("delivered"))
    assert json.loads((directory / "state").read_text())["locked"]


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


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGALRM])
def test_signal_during_final_lock_is_deferred_until_verification_and_session_clear(fake, sig):
    directory, update, events = fake
    update(cleanup_signal=int(sig))
    previous_handler = signal.signal(sig, bw.interrupted)
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    vault = bw.Vault()
    try:
        with pytest.raises(bw.Failure, match="interrupted"):
            bw.transaction(vault, request(), ask=lambda *_: True,
                           deliver=lambda _: pytest.fail("released despite interruption"))
        assert vault.session is None
        assert events()[-1]["args"] == ["status"] and events()[-1]["session"]
        assert json.loads((directory / "state").read_text())["locked"]
        assert signal.pthread_sigmask(signal.SIG_BLOCK, set()) == previous_mask
    finally:
        signal.signal(sig, previous_handler)


@pytest.mark.parametrize("uri", ["admin.example.com", "admin.example.com/login?key=fixture",
                                 "admin.example.com:443/login", "//admin.example.com/login", "https://ADMIN.example.com"])
def test_scheme_less_and_http_hosts_match_exactly(uri):
    assert bw.matching({**ITEM, "login": {"uris": [{"uri": uri}]}}, "admin.example.com")


@pytest.mark.parametrize("uri", ["admin.example.com.evil.test", "admin.example.com@evil.test",
                                 "eviladmin.example.com", "javascript://admin.example.com", "/admin.example.com"])
def test_scheme_less_near_matches_rejected(uri):
    assert not bw.matching({**ITEM, "login": {"uris": [{"uri": uri}]}}, "admin.example.com")


@pytest.mark.parametrize("op", ["send-text", "send-file"])
def test_send_snapshot_stdin_and_minimal_result(fake, tmp_path, op):
    directory, _, events = fake
    original = b"frozen fixture content"
    source = tmp_path / 'a;$(touch PWNED) "document".txt'
    source.write_bytes(original)

    def ask(request, payload):
        source.write_bytes(b"changed after review")
        if op == "send-file":
            assert Path(payload["file"]["fileName"]).stat().st_mode & 0o777 == 0o600
            assert payload["_review"]["bytes"] == len(original)
        else:
            assert payload["text"]["text"] == original.decode()
        return True

    result = bw.transaction(bw.Vault(), {"op": op, "input_file": str(source), "name": "Example", "views": 1}, ask=ask)
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
        bw.transaction(bw.Vault(), {"op": "send-text", "input_file": str(source), "name": "Example", "views": 1})
    assert not any(event["args"][0] == "unlock" for event in events())


def test_fifo_rejected_without_blocking(fake, tmp_path):
    source = tmp_path / "fifo"
    os.mkfifo(source)
    with pytest.raises(bw.Failure, match="regular file"):
        bw.transaction(bw.Vault(), {"op": "send-file", "input_file": str(source), "name": "Example", "views": 1})


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
    assert [event["args"] for event in events()] == [["status"], ["--version"]]
    assert not json.loads((directory / "state").read_text())["locked"]


def test_result_file_permissions_and_no_overwrite(tmp_path):
    target = tmp_path / "result"
    bw.private_json(target, {"ok": True})
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): bw.private_json(target, {"ok": False})


def test_mutex_refuses_contention(fake):
    with bw.mutex():
        with pytest.raises(bw.Failure, match="Another"):
            with bw.mutex(): pytest.fail("concurrent request accepted")


def test_installer_copy_link_and_help_without_vault_access(fake, tmp_path):
    directory, _, _ = fake
    for name, text in {"uname": "echo Darwin", "xcrun": 'printf "#!/bin/sh\\nexit 0\\n" > "$4"',
                       "uv": "shift 3\nexec " + shlex.quote(sys.executable) + ' "$@"'}.items():
        script = directory / name
        script.write_text("#!/bin/sh\n" + text + "\n")
        script.chmod(0o700)
    installer = str(SCRIPTS / "install")
    prefix = tmp_path / "install"
    subprocess.run([installer, "--prefix", str(prefix)], check=True, capture_output=True)
    subprocess.run([installer, "--prefix", str(prefix)], check=True, capture_output=True)
    subprocess.run([installer, "--check", "--prefix", str(prefix)], check=True, capture_output=True)
    command = prefix / "bin/bw-once"
    assert command.is_symlink()
    result = subprocess.run([str(command), "--help"], env=dict(os.environ, UV_PYTHON=sys.executable), capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    assert not (directory / "events").exists()
