"""One fixed vault operation per human Terminal unlock, or a time-boxed session holder.

The session key never leaves this process: a holder started in the human Terminal serves
exact-host list/copy requests over a private Unix socket and locks the CLI at expiry."""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import termios
import time
from urllib.parse import urlsplit
from urllib.request import urlopen
import uuid

AUTH_SECONDS = 180
TTL_DEFAULT_MINUTES = 60
TTL_MAX_MINUTES = 240
FILE_LIMIT = 50 * 1024 * 1024
TEXT_LIMIT = 600  # Conservative UTF-8 pilot cap, below the encrypted-text limit.
SEND_DAYS_DEFAULT, SEND_DAYS_MAX = 7, 31  # Bitwarden deletes a Send at most 31 days out
ROOT = Path(__file__).resolve().parent


class Failure(Exception):
    pass


@contextmanager
def shield_cleanup():
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM, signal.SIGALRM})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def clean_env():
    return {key: value for key, value in os.environ.items() if key in
            {"HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "TMPDIR"}}


def reject_injection():
    if any(key.startswith("BW_") or key.startswith("BITWARDENCLI_")
           for key in os.environ):
        raise Failure("Remove Bitwarden environment overrides; no session/password injection allowed")


def host(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9.-]+", value):
        raise Failure("Use an exact DNS host without scheme, port, path or wildcard")
    value = value.lower()
    if len(value) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                               for label in value.split(".")):
        raise Failure("Invalid DNS host")
    return value


def item_id(value):
    try:
        if str(uuid.UUID(value)) != value.lower():
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Failure("Use an exact item UUID") from None
    return value.lower()


def vault_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9-]{1,32}", value):
        raise Failure("Invalid vault name")
    return value


def vault_config(name=None):
    """Named CLI contexts (one Bitwarden account each) from ~/.config/bw-once/vaults.json:
    {"work": {"email": "a@x.eu", "default": true}, "dentai": {"email": "b@y.eu", "appdata": "~/…", "server": "https://…"}}.
    `appdata` = separate CLI data dir (omit = bw's default); no file = one unnamed context without email check."""
    path = Path.home() / ".config" / "bw-once" / "vaults.json"
    if not path.is_file():
        if name not in (None, "default"):
            raise Failure(f"No vaults configured in {path}; omit --vault")
        return {"name": "default"}
    try:
        vaults = json.loads(path.read_text())
    except (OSError, ValueError):
        raise Failure("Invalid vaults.json") from None
    if not isinstance(vaults, dict) or not vaults or not all(isinstance(v, dict) for v in vaults.values()):
        raise Failure("Invalid vaults.json")
    if name is None:
        defaults = [key for key, entry in vaults.items() if entry.get("default") is True]
        if len(defaults) != 1:
            raise Failure("Choose --vault " + "|".join(sorted(vaults)))
        name = defaults[0]
    entry = vaults.get(name)
    if entry is None or not isinstance(entry.get("email"), str) or "@" not in entry["email"]:
        raise Failure("Unknown vault; choose --vault " + "|".join(sorted(vaults)))
    config = {"name": vault_name(name), "email": entry["email"].lower()}
    if entry.get("appdata"):
        appdata = str(entry["appdata"])
        appdata = Path.home() / appdata[2:] if appdata.startswith("~/") else Path(appdata)
        if not appdata.is_absolute():
            raise Failure("Vault appdata must be absolute or start with ~/")
        config["appdata"] = str(appdata.resolve())
    if entry.get("server"):
        url = urlsplit(entry["server"])
        if url.scheme != "https" or not url.hostname or url.path not in ("", "/") or url.query or url.username:
            raise Failure("Vault server must be an https origin")
        config["server"] = f"https://{url.hostname}" + (f":{url.port}" if url.port else "")
    return config


def reason_text(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise Failure("Reason must be 1-200 characters without control characters")
    return value


def validate(request):
    op = request.get("op") if isinstance(request, dict) else None
    if op == "session-start":
        request = {"reason": None, **request}
    if op in ("send-text", "send-file"):
        request = {"days": SEND_DAYS_DEFAULT, **request}
    allowed = {"list": {"op", "host"}, "copy": {"op", "host", "id", "field"},
               "send-text": {"op", "input_file", "name", "views", "days"},
               "send-file": {"op", "input_file", "name", "views", "days"},
               "session-start": {"op", "ttl", "hosts", "reason"}, "session-stop": {"op"}, "session-status": {"op"},
               "login": {"op"}}
    if op not in allowed or set(request) != allowed[op] | {"vault"}:
        raise Failure("Invalid request")
    request = dict(request)
    request["vault"] = vault_name(request["vault"])
    if op == "session-start":
        if type(request["ttl"]) is not int or not 1 <= request["ttl"] <= TTL_MAX_MINUTES:
            raise Failure(f"Session ttl must be 1-{TTL_MAX_MINUTES} minutes")
        if not isinstance(request["hosts"], list):
            raise Failure("Session hosts must be a list")
        request["hosts"] = sorted({host(value) for value in request["hosts"]})
        if not request["hosts"]:
            raise Failure("Name the exact hosts (--host); an unscoped session would serve any login")
        request["reason"] = reason_text(request["reason"])
    if op in ("list", "copy"):
        request["host"] = host(request["host"])
    if op == "copy":
        request["id"] = item_id(request["id"])
        if request["field"] not in ("username", "password", "totp"):
            raise Failure("Unsupported credential field")
    if op.startswith("send-"):
        name = request["name"]
        if not isinstance(name, str) or not name or len(name) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise Failure("Send name must be 1-200 characters without control characters")
        if type(request["views"]) is not int or not 1 <= request["views"] <= 100:
            raise Failure("Views must be an integer from 1 to 100")
        if type(request["days"]) is not int or not 1 <= request["days"] <= SEND_DAYS_MAX:
            raise Failure(f"Days must be an integer from 1 to {SEND_DAYS_MAX}")
        if not isinstance(request["input_file"], str):
            raise Failure("Invalid input file")
        request["input_file"] = str(Path(request["input_file"]).expanduser().resolve())
    return request


class Vault:
    def __init__(self, name=None):
        self.binary = shutil.which("bw")
        if not self.binary:
            raise Failure("Bitwarden CLI is missing")
        self.config = vault_config(name)
        self.env = clean_env()
        if "appdata" in self.config:
            appdata = Path(self.config["appdata"])
            appdata.mkdir(mode=0o700, parents=True, exist_ok=True)
            if appdata.is_symlink() or appdata.stat().st_uid != os.getuid():
                raise Failure("Unsafe vault data directory")
            self.env["BITWARDENCLI_APPDATA_DIR"] = str(appdata)
        self.session = None

    def call(self, *args, data=None, unlock=False):
        env = dict(self.env, BW_NOINTERACTION="true")
        if self.session:
            env["BW_SESSION"] = self.session
        if unlock:
            env.pop("BW_NOINTERACTION")
        terminal = termios.tcgetattr(sys.stdin.fileno()) if unlock and sys.stdin.isatty() else None
        try:
            result = subprocess.run([self.binary, *args], input=data,
                                    stdin=None if unlock or data is not None else subprocess.DEVNULL,
                                    stdout=subprocess.PIPE,
                                    stderr=None if unlock else subprocess.DEVNULL,
                                    env=env, timeout=AUTH_SECONDS if unlock else 60)
        except subprocess.TimeoutExpired:
            raise Failure("Bitwarden operation timed out") from None
        finally:
            if terminal is not None:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, terminal)
        if result.returncode:
            raise Failure("Bitwarden operation failed; inspect manually while locked")
        return result.stdout

    def json(self, *args, **kwargs):
        try:
            return json.loads(self.call(*args, **kwargs))
        except (ValueError, UnicodeError):
            raise Failure("Invalid Bitwarden response") from None

    def locked(self):
        status = self.json("status")
        state = status.get("status")
        if state == "unauthenticated":
            raise Failure("CLI is logged out (bw drops the login when its refresh token expired, e.g. months "
                          f"without sync); run `bw-once --vault {self.config['name']} login`, then retry")
        if state != "locked":
            raise Failure("CLI must be logged in and locked; login manually first")
        expected = self.config.get("email")
        if expected and str(status.get("userEmail") or "").lower() != expected:
            raise Failure(f"Vault '{self.config['name']}' CLI context is signed in as another account")

    def relock(self):
        with shield_cleanup():
            try:
                self.call("lock")
                self.locked()  # Keep the former session for this verification.
            except Failure as error:
                if "logged out" in str(error):
                    raise Failure(f"Nothing to lock: {error}") from None
                if "another account" in str(error):
                    raise
                raise Failure("CLI lock verification failed; result withheld, lock manually now") from None
            except Exception:
                raise Failure("CLI lock verification failed; result withheld, lock manually now") from None
            finally:
                self.session = None


def cache_dir():
    cache = Path.home() / ".cache" / "bw-once"
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    if cache.is_symlink() or cache.stat().st_uid != os.getuid():
        raise Failure("Unsafe helper lock directory")
    os.chmod(cache, 0o700)
    return cache


def session_socket(vault):
    return cache_dir() / f"session-{vault_name(vault)}.sock"


@contextmanager
def mutex(vault):
    cache = cache_dir()
    fd = os.open(cache / f"lock-{vault_name(vault)}", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Failure("Another bw-once request is running") from None
        yield
    finally:
        os.close(fd)


@contextmanager
def snapshot(request):
    if not request["op"].startswith("send-"):
        yield None
        return
    source = Path(request["input_file"])
    limit = TEXT_LIMIT if request["op"] == "send-text" else FILE_LIMIT
    try:
        fd = os.open(source, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise Failure("Send input must be a regular file")
            content = stream.read(limit + 1)
    except OSError:
        raise Failure("Cannot read Send input") from None
    if not content or len(content) > limit:
        raise Failure(f"Send input must be 1-{limit} bytes")
    until = (datetime.now(timezone.utc) + timedelta(days=request["days"])).isoformat()
    payload = {"name": request["name"], "type": 0, "disabled": False,
               "hideEmail": True, "maxAccessCount": request["views"],
               "deletionDate": until, "expirationDate": until}
    if request["op"] == "send-text":
        try:
            payload["text"] = {"text": content.decode("utf-8"), "hidden": True}
        except UnicodeError:
            raise Failure("Text Send input must be UTF-8") from None
        yield payload
    else:
        with tempfile.TemporaryDirectory(prefix="bw-once-payload-") as directory:
            frozen = Path(directory) / source.name
            fd = os.open(frozen, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
            payload["type"] = 1
            payload["file"] = {"fileName": str(frozen)}
            payload["_review"] = {"file": source.name, "bytes": len(content),
                                  "sha256": hashlib.sha256(content).hexdigest()}
            yield payload


def confirm(request, payload, account=None):
    print(f"Bitwarden request for vault '{request['vault']}' ({account or 'default CLI account'}); "
          "master password or Touch ID follows:", flush=True)
    print(json.dumps(request, ensure_ascii=True), flush=True)
    if payload:
        review = {key: payload[key] for key in ("name", "maxAccessCount", "deletionDate", "expirationDate")}
        review.update(payload.get("_review", {"exact_text": payload.get("text", {}).get("text")}))
        print(json.dumps(review, ensure_ascii=True), flush=True)
    return input("Continue? [y/N] ").strip().lower() == "y"


def matching(item, expected):
    if not isinstance(item, dict) or item.get("type") != 1 or not isinstance(item.get("login"), dict):
        return False
    for uri in item["login"].get("uris") or []:
        try:
            value = uri.get("uri") or ""
            parsed = urlsplit(value if "://" in value or value.startswith("//") else "//" + value)
            if parsed.scheme in ("", "https", "http") and parsed.hostname == expected:
                return True
        except (ValueError, AttributeError):
            continue
    return False


def operate(vault, request, payload):
    op = request["op"]
    if op == "list":
        items = vault.json("list", "items", "--url", "https://" + request["host"])
        if not isinstance(items, list):
            raise Failure("Invalid item list")
        return {"items": [{"id": item_id(item.get("id")), "name": item.get("name"),
                           "username": item["login"].get("username"), "host": request["host"]}
                          for item in items if matching(item, request["host"])]}, None
    if op == "copy":
        item = vault.json("get", "item", request["id"])
        if not matching(item, request["host"]) or str(item.get("id") or "").lower() != request["id"]:
            raise Failure("Item ID, login type or exact host does not match")
        if request["field"] == "totp":
            secret = vault.call("get", "totp", request["id"]).decode().strip()
            if not re.fullmatch(r"[0-9]{6,8}", secret):
                raise Failure("No valid generated TOTP code")
        else:
            secret = item["login"].get(request["field"])
        if not isinstance(secret, str) or not secret or "\x00" in secret:
            raise Failure("Requested field is missing or unsupported")
        return {"copied": request["field"], "id": request["id"], "host": request["host"],
                "clear_after_seconds": 30}, secret
    encoded = base64.b64encode(json.dumps({k: v for k, v in payload.items() if k != "_review"}).encode())
    created = vault.json("send", "--fullObject", "create", data=encoded)
    if not isinstance(created, dict) or not isinstance(created.get("accessUrl"), str):
        raise Failure("Invalid Send result; creation may have succeeded, check manually before retrying")
    url = urlsplit(created["accessUrl"])
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise Failure("Invalid Send URL; check manually before retrying")
    return {"id": item_id(created.get("id")), "url": created["accessUrl"],
            "expiry": created.get("expirationDate"), "deletion": created.get("deletionDate"),
            "views": created.get("maxAccessCount")}, None


def clipboard(secret):
    helper = ROOT / "clipboard"
    if sys.platform != "darwin" or not helper.is_file():
        raise Failure("macOS clipboard helper missing; run installer first")
    child = subprocess.Popen([str(helper)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=clean_env(), start_new_session=True)
    try:
        child.stdin.write(secret.encode("utf-8"))
        child.stdin.close()
        if not select.select([child.stdout], [], [], 5)[0] or child.stdout.readline() != b"ready\n":
            raise Failure("Clipboard delivery failed")
    except (BrokenPipeError, OSError):
        raise Failure("Clipboard delivery failed") from None
    finally:
        child.stdout.close()
    # Child owns the bounded 30-second timer; it has never inherited BW_SESSION.


def same_vault(vault, request):
    if vault.config["name"] != request["vault"]:
        raise Failure("Request vault does not match the CLI context")


def login_transaction(vault, request, ask=confirm):
    """First login of a CLI context in the human Terminal (master password + 2FA there), then lock."""
    request = validate(request)
    same_vault(vault, request)
    email = vault.config.get("email")
    if not email:
        raise Failure("Login needs a configured vault with an email")
    with mutex(request["vault"]):
        if vault.json("status").get("status") != "unauthenticated":
            raise Failure("This vault's CLI context is already logged in")
        if not ask(request, None, email):
            raise Failure("Request cancelled")
        if "server" in vault.config:
            vault.call("config", "server", vault.config["server"])
        try:
            key = vault.call("login", email, "--raw", unlock=True).decode().strip()
            vault.session = key if re.fullmatch(r"[A-Za-z0-9+/=]+", key) else None
        finally:
            vault.relock()
        vault.locked()
    return {"vault": request["vault"], "status": "locked"}


def transaction(vault, request, ask=confirm, deliver=clipboard):
    request = validate(request)
    same_vault(vault, request)
    with mutex(request["vault"]):
        if request["op"] == "copy" and deliver is clipboard and not (ROOT / "clipboard").is_file():
            raise Failure("Clipboard helper missing; run installer first")
        vault.relock()
        try:
            if request["op"] in ("list", "copy"):
                vault.call("sync")
                vault.locked()
            with snapshot(request) as payload:
                if not ask(request, payload, vault.config.get("email")):
                    raise Failure("Request cancelled")
                key = vault.call("unlock", "--raw", unlock=True).decode().strip()
                if not key or not re.fullmatch(r"[A-Za-z0-9+/=]+", key):
                    raise Failure("Unlock did not return a session")
                vault.session = key
                result, secret = operate(vault, request, payload)
        finally:
            vault.relock()
        if secret is not None:
            deliver(secret)
        return result


class Stop(Exception):
    pass


def read_line(connection, limit=65536):
    data = b""
    while not data.endswith(b"\n") and len(data) < limit:
        chunk = connection.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


class Session:
    """Holds one unlocked session in memory; serves list/copy until the deadline, then locks."""

    def __init__(self, vault, request, deliver=clipboard):
        self.bw, self.deliver = vault, deliver
        self.hosts = set(request["hosts"])
        self.vault, self.reason = request["vault"], request["reason"]
        self.deadline = time.monotonic() + request["ttl"] * 60
        self.expires = datetime.now(timezone.utc) + timedelta(minutes=request["ttl"])

    def status(self):
        return {"active": True, "expires_at": self.expires.isoformat(timespec="seconds"),
                "remaining_seconds": max(0, int(self.deadline - time.monotonic())), "hosts": sorted(self.hosts),
                "vault": self.vault, "reason": self.reason}

    def handle(self, request):
        request = validate(request)
        if request["vault"] != self.vault:
            raise Failure("Request vault does not match this session")
        if request["op"] == "session-status":
            return self.status()
        if request["op"] == "session-stop":
            raise Stop()
        if request["op"] not in ("list", "copy"):
            raise Failure("A session serves list and copy only; Sends need their own Terminal request")
        if self.hosts and request["host"] not in self.hosts:
            raise Failure("Host is outside this session's allowlist")
        if time.monotonic() >= self.deadline:
            raise Failure("Session expired")
        result, secret = operate(self.bw, request, None)
        if secret is not None:
            self.deliver(secret)
        return {"via": "session", **result}


def serve_session(vault, request, announce=lambda status: None, deliver=clipboard, audit=lambda line: None):
    path = session_socket(request["vault"])
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    previous = os.umask(0o177)
    try:
        server.bind(str(path))
    finally:
        os.umask(previous)
    server.listen(4)
    session = Session(vault, request, deliver)
    announce(session.status())
    try:
        while session.deadline > time.monotonic():
            if not select.select([server], [], [], min(5.0, session.deadline - time.monotonic()))[0]:
                continue
            connection, _ = server.accept()
            with connection:
                connection.settimeout(5)
                incoming = None
                try:
                    incoming = json.loads(read_line(connection, 4096))
                    result = {"ok": True, **session.handle(incoming)}
                except Stop:
                    connection.sendall(b'{"ok": true, "active": false}\n')
                    audit({"op": "session-stop"})
                    break
                except Failure as error:
                    result = {"ok": False, "error": str(error)}
                except Exception:
                    result = {"ok": False, "error": "Request failed"}
                connection.settimeout(90)
                try:
                    connection.sendall(json.dumps(result).encode() + b"\n")
                except OSError:
                    pass
                if isinstance(incoming, dict) and incoming.get("op") in ("list", "copy"):
                    audit({key: incoming.get(key) for key in ("op", "vault", "host", "id", "field") if key in incoming}
                          | {"ok": result["ok"]})
    finally:
        server.close()
        try:
            path.unlink()
        except OSError:
            pass


def session_transaction(vault, request, ask=confirm, announce=lambda status: None, deliver=clipboard,
                        audit=lambda line: None):
    request = validate(request)
    same_vault(vault, request)
    with mutex(request["vault"]):
        vault.relock()
        try:
            vault.call("sync")
            vault.locked()
            if not ask(request, None, vault.config.get("email")):
                raise Failure("Request cancelled")
            key = vault.call("unlock", "--raw", unlock=True).decode().strip()
            if not key or not re.fullmatch(r"[A-Za-z0-9+/=]+", key):
                raise Failure("Unlock did not return a session")
            vault.session = key
            serve_session(vault, request, announce, deliver, audit)
        finally:
            vault.relock()
    return {"active": False}


def via_session(request):
    """Ask a running holder; None when there is none (caller falls back to the Terminal flow)."""
    path = session_socket(request["vault"])
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(120)
    try:
        client.connect(str(path))
    except OSError:
        client.close()
        return None
    with client:
        client.sendall(json.dumps(request).encode() + b"\n")
        try:
            return json.loads(read_line(client))
        except ValueError:
            raise Failure("Invalid session helper response") from None


APPLE_SCRIPT = '''on run argv
tell application "Terminal"
activate
do script (item 1 of argv)
end tell
end run'''


def worker_command(directory):
    command = ["/usr/bin/env", "-i", *(f"{key}={value}" for key, value in clean_env().items()),
               "TERM_PROGRAM=Apple_Terminal", sys.executable, "-I", str(ROOT / "bw_once.py"),
               "--worker", str(directory)]
    return "exec " + shlex.join(command)


def terminal_command(directory):
    return "exec " + shlex.join(["/bin/sh", str(Path(directory) / "run.sh")])


def private_launcher(directory):
    # Terminal's canonical input truncates long commands; the shell reads this file instead.
    path = Path(directory) / "run.sh"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700)
    with os.fdopen(fd, "w") as stream:
        stream.write("#!/bin/sh\n" + worker_command(directory) + "\n")


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)


def ttl_minutes(value):
    match = re.fullmatch(r"(\d+)([mh]?)", str(value).strip())
    if not match:
        raise Failure("ttl must look like 60m or 1h")
    return int(match.group(1)) * (60 if match.group(2) == "h" else 1)


def result_ok(status, expected):
    return not expected or str(status.get("userEmail") or "").lower() == expected


def touch_id_flag(vault):
    """bw >= 2026.10 unlocks via Desktop Touch ID only when the server enables `biometrics-sdk-ipc`."""
    try:
        server = urlsplit(vault.call("config", "server").decode().strip())
        if server.scheme != "https" or not server.hostname:
            return None
        with urlopen(f"https://{server.hostname}/api/config", timeout=5) as response:
            return json.loads(response.read(1_000_000)).get("featureStates", {}).get("biometrics-sdk-ipc")
    except Exception:
        return None


def interrupted(*_):
    raise Failure("Request interrupted or timed out")


def worker(directory):
    if sys.platform != "darwin" or os.environ.get("TERM_PROGRAM") != "Apple_Terminal" or not all(
            stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        raise Failure("Authentication requires a real human macOS Terminal; agent PTYs are unsupported")
    directory = Path(directory)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise Failure("Unsafe request directory")
    private_json(directory / "worker.json", {"pid": os.getpid()})
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
        signal.signal(sig, interrupted)
    signal.alarm(AUTH_SECONDS)
    try:
        request = json.loads((directory / "request.json").read_text())
        if isinstance(request, dict) and request.get("op") == "session-start":
            def announce(status):
                signal.alarm(0)
                publish(directory, {"ok": True, **status})
                print(f"Session on vault '{status['vault']}' active until {status['expires_at']} for hosts "
                      f"{status['hosts'] or 'any'}. "
                      "Each request is logged below; Ctrl-C or `bw-once session stop` locks earlier.", flush=True)
            result = {"ok": True, **session_transaction(Vault(request["vault"]), request, announce=announce,
                                                        audit=lambda line: print(json.dumps(line), flush=True))}
        elif isinstance(request, dict) and request.get("op") == "login":
            result = {"ok": True, **login_transaction(Vault(request["vault"]), request)}
        else:
            result = {"ok": True, **transaction(Vault(request.get("vault")), request)}
    except Failure as error:
        result = {"ok": False, "error": str(error)}
    except Exception:
        result = {"ok": False, "error": "Request failed; CLI result withheld"}
    finally:
        signal.alarm(0)
    if (directory / "result.json").is_file():
        print("Session ended, CLI locked. Close this Terminal window.", flush=True)
        return
    if not publish(directory, result):
        print("Result channel closed; CLI cleanup finished. Close this Terminal window.", flush=True)
        return
    print("Request finished. Close this Terminal window.", flush=True)


def publish(directory, result):
    try:
        private_json(directory / "result.tmp", result)
        os.rename(directory / "result.tmp", directory / "result.json")
        return True
    except OSError:
        return False


def launch(request):
    if sys.platform != "darwin" or not shutil.which("osascript"):
        raise Failure("A real macOS Terminal is required; no noninteractive fallback")
    request = validate(request)
    vault = Vault(request["vault"])  # Fail before opening a Terminal: wrong account, logged out, already unlocked.
    if request["op"] == "login":
        if vault.json("status").get("status") != "unauthenticated":
            raise Failure("This vault's CLI context is already logged in")
    else:
        vault.locked()
    with tempfile.TemporaryDirectory(prefix="bw-once-request-") as directory:
        path = Path(directory)
        private_json(path / "request.json", request)
        private_launcher(directory)
        try:
            started = subprocess.run(["osascript", "-e", APPLE_SCRIPT, terminal_command(directory)],
                                     env=clean_env(), stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, timeout=15)
            if started.returncode:
                raise Failure("Cannot open human Terminal")
            deadline = time.monotonic() + AUTH_SECONDS + 20
            while time.monotonic() < deadline:
                if (path / "result.json").is_file():
                    return json.loads((path / "result.json").read_text())
                time.sleep(0.2)
            raise Failure("Human Terminal request timed out")
        finally:
            if request["op"] != "session-start" and (path / "worker.json").is_file() and not (path / "result.json").is_file():
                try:
                    os.kill(json.loads((path / "worker.json").read_text())["pid"], signal.SIGTERM)
                    end = time.monotonic() + 10
                    while time.monotonic() < end and not (path / "result.json").is_file():
                        time.sleep(0.2)
                except (OSError, ValueError, KeyError):
                    pass


def main():
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--vault", help="named CLI context from ~/.config/bw-once/vaults.json (default: its default)")
    commands = parser.add_subparsers(dest="op")
    commands.add_parser("status")
    commands.add_parser("doctor")
    commands.add_parser("login", help="first login of a vault's CLI context in a human Terminal")
    commands.add_parser("list").add_argument("--host", required=True)
    copy = commands.add_parser("copy")
    copy.add_argument("--id", required=True)
    copy.add_argument("--host", required=True)
    copy.add_argument("--field", required=True, choices=("username", "password", "totp"))
    for op in ("send-text", "send-file"):
        send = commands.add_parser(op)
        send.add_argument("--input-file", required=True)
        send.add_argument("--name", required=True)
        send.add_argument("--views", type=int, default=1)
        send.add_argument("--days", type=int, default=SEND_DAYS_DEFAULT, help=f"expiry/deletion, 1-{SEND_DAYS_MAX}")
    session = commands.add_parser("session").add_subparsers(dest="action")
    start = session.add_parser("start")
    start.add_argument("--ttl", default=f"{TTL_DEFAULT_MINUTES}m", help="minutes, e.g. 60m or 1h")
    start.add_argument("--host", action="append", default=[], dest="hosts", help="restrict to exact hosts")
    start.add_argument("--reason", help="one line shown to the human in the Terminal and in session status")
    session.add_parser("stop")
    session.add_parser("status")
    args = vars(parser.parse_args())
    if args["op"] == "session":
        action = args.pop("action")
        if not action:
            parser.error("Choose session start|stop|status")
        args["op"] = f"session-{action}"
    try:
        reject_injection()
        directory = args.pop("worker")
        if directory:
            worker(directory)
            return
        args["vault"] = vault_config(args["vault"])["name"]
        if args["op"] in ("status", "doctor"):
            vault = Vault(args["vault"])
            status = vault.json("status")
            state = status.get("status")
            version = vault.call("--version").decode().strip()
            if not re.fullmatch(r"\d+\.\d+\.\d+(?:[\w.-]*)", version):
                raise Failure("Invalid CLI version response")
            expected = vault.config.get("email")
            result = {"ok": True, "vault": args["vault"],
                      "status": state if state in ("locked", "unlocked", "unauthenticated") else "unknown",
                      "account_matches": None if not expected or state == "unauthenticated"
                      else str(status.get("userEmail") or "").lower() == expected,
                      "bw_version": version, "touch_id_flag": touch_id_flag(vault),
                      "ready": state == "locked" and sys.platform == "darwin" and result_ok(status, expected),
                      "clipboard_ready": (ROOT / "clipboard").is_file(),
                      "session": via_session({"op": "session-status", "vault": args["vault"]}) or {"active": False}}
        elif args["op"] == "session-start":
            args["ttl"] = ttl_minutes(args["ttl"])
            result = launch(args)
        elif args["op"] in ("session-stop", "session-status"):
            result = via_session(args) or {"ok": True, "active": False}
        elif args["op"] in ("list", "copy"):
            result = via_session(args) or launch(args)
        elif args["op"]:
            result = launch(args)
        else:
            parser.error("Choose a command")
    except Failure as error:
        result = {"ok": False, "error": str(error)}
    except (Exception, KeyboardInterrupt):
        result = {"ok": False, "error": "Request failed or interrupted; result withheld"}
    print(json.dumps(result))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
