"""One fixed vault operation per human Terminal unlock, or a time-boxed session holder.

The session key never leaves this process: a holder started in the human Terminal serves
destination-scoped list/copy requests over a private Unix socket and locks the CLI at expiry."""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import getpass
from functools import lru_cache
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

WAIT_SECONDS = 360  # Vault still locked: time for the human to reach the Terminal and approve.
AUTH_SECONDS = 180  # From approval: unlock, operation, lock. Launcher waits both + 20 s, under a 10-minute tool call.
TTL_DEFAULT_MINUTES = 60
TTL_MAX_MINUTES = 240
FILE_LIMIT = 50 * 1024 * 1024
TEXT_LIMIT = 600  # Conservative UTF-8 pilot cap, below the encrypted-text limit.
BROKER_SECONDS = 330  # The broker releases nothing once 300 s passed since its start (renewal panels included).
SEND_DAYS_DEFAULT, SEND_DAYS_MAX = 7, 31  # Bitwarden deletes a Send at most 31 days out
ROOT = Path(__file__).resolve().parent
DEFAULT_MATCHES = {"base_domain": 0, "host": 1, "exact": 3, "never": 5}


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
    default_match = entry.get("default_match", "base_domain")
    if not isinstance(default_match, str) or default_match not in DEFAULT_MATCHES:
        raise Failure("Invalid default_match; use base_domain, host, exact or never")
    config["default_match"] = default_match
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
    if op == "copy":
        request = {"id": None, "username": None, **request}
    if op == "list":
        request = {"username": None, **request}
    allowed = {"list": {"op", "host", "username"}, "copy": {"op", "host", "id", "username", "field"},
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
    if op in ("list", "copy"):
        if request["username"] is not None and (not isinstance(request["username"], str) or not request["username"]
                                                or len(request["username"]) > 254
                                                or any(ord(c) < 32 or ord(c) == 127 for c in request["username"])):
            raise Failure("Username must be 1-254 characters without control characters")
    if op == "copy":
        if request["id"] is not None:
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
        # The installer's verified copy of Bitwarden's signed CLI (the broker checks the signature); else PATH.
        self.binary = str(ROOT / "bw") if (ROOT / "bw").is_file() else shutil.which("bw")
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
            step = args[0] if args[0] in ("unlock", "login", "sync", "list", "get", "send", "lock", "status", "config") else "operation"
            hint = " (wrong master password or cancelled?)" if step in ("unlock", "login") else "; inspect manually while locked"
            raise Failure(f"bw {step} failed{hint}")
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

    def unlock(self, request):
        """Official interactive `bw unlock` in the human Terminal (Touch ID requests go to the broker instead)."""
        key = self.call("unlock", "--raw", unlock=True)
        key = key.decode().strip()
        if not key or not re.fullmatch(r"[A-Za-z0-9+/=]+", key):
            raise Failure("Unlock did not return a session")
        self.session = key

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
    return cache_dir() / f"session-v2-{vault_name(vault)}.sock"


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
    print(f"\aBitwarden request for vault '{request['vault']}' ({account or 'default CLI account'}):", flush=True)
    print(json.dumps(request, ensure_ascii=True), flush=True)
    if request["op"] in ("list", "copy", "session-start"):
        print("Vault default: " + vault_config(request["vault"]).get("default_match", "base_domain"), flush=True)
        print("Matching: Base domain (public suffix aware) unless a per-URI or configured vault default restricts it. "
              "Host only on destination port 443; Exact/StartsWith/Regex/Never excluded. "
              "Browser defaults/equivalent domains are not imported.", flush=True)
    if payload:
        review = {key: payload[key] for key in ("name", "maxAccessCount", "deletionDate", "expirationDate")}
        review.update(payload.get("_review", {"exact_text": payload.get("text", {}).get("text")}))
        print(json.dumps(review, ensure_ascii=True), flush=True)
    # Return approves: the master password typed next is the real consent. Read without echo, so a password
    # typed here too early is neither shown nor used. Touch ID replaces bw's password prompt only once Bitwarden
    # enables `biometrics-sdk-ipc` for the account's server (`bw-once doctor` → touch_id_flag).
    answer = getpass.getpass("Press Return to continue, n = cancel (no password here): ")
    if answer.strip().lower() in ("", "y", "yes"):
        return True
    if answer.strip().lower() not in ("n", "no"):
        print("Unexpected input discarded unseen; request cancelled.", flush=True)
    return False


@lru_cache(maxsize=1)
def suffix_rules():
    # Offline ICANN + PRIVATE snapshot, also embedded in the signed broker at build time.
    try:
        lines = (ROOT / "public_suffix_list.dat").read_text().splitlines()
        if "// ===END ICANN DOMAINS===" not in lines or "// ===END PRIVATE DOMAINS===" not in lines:
            raise Failure("Public Suffix List incomplete; rerun installer")
        return {line.encode("idna").decode("ascii") for line in lines if line and not line.startswith("//")}
    except (OSError, UnicodeError):
        raise Failure("Public Suffix List missing or invalid; rerun installer") from None


def base_domain(value):
    labels = value.split(".")
    rules = suffix_rules()
    # Unknown/local suffixes and bare public suffixes cannot establish a registrable domain.
    size = 0
    for i in range(len(labels)):
        suffix = ".".join(labels[i:])
        if "!" + suffix in rules:
            size = len(labels) - i - 1
            break
        if suffix in rules:
            size = max(size, len(labels) - i)
        if i > 0 and "*." + suffix in rules:
            size = max(size, len(labels) - i + 1)
    return ".".join(labels[-size - 1:]) if size and len(labels) > size else None


def match_scope(item, expected, default_match="base_domain"):
    if not isinstance(item, dict) or type(item.get("type")) is not int or item.get("type") != 1 or not isinstance(item.get("login"), dict):
        return None
    uris = item["login"].get("uris")
    if not isinstance(uris, list):
        return None
    for uri in uris:
        if not isinstance(uri, dict):
            continue
        rule = uri.get("match")
        if rule is None:
            rule = DEFAULT_MATCHES[default_match]
        # Host-only requests cannot establish Exact/StartsWith/Regex constraints. Never stays never.
        if type(rule) is not int or rule not in (0, 1):
            continue
        domain = base_domain(expected) if rule == 0 else None  # Missing PSL is an operation error, not a URI miss.
        try:
            value = uri.get("uri")
            if not isinstance(value, str) or not value or any(ord(c) < 33 or ord(c) > 126 for c in value) or "\\" in value:
                continue
            parsed = urlsplit(value if "://" in value or value.startswith("//") else "//" + value)
            if parsed.scheme not in ("", "https", "http") or parsed.username is not None or parsed.password is not None:
                continue
            saved = host(parsed.hostname)
            port = parsed.port  # Reject malformed ports even for Base domain.
            if (rule == 0 and domain is not None and domain == base_domain(saved)) or (
                    rule == 1 and saved == expected and port in (None, 443)):
                return {"matched_uri_host": saved, "match_rule": "base_domain" if rule == 0 else "host"}
        except (ValueError, AttributeError, Failure):
            continue
    return None


def matching(item, expected, default_match="base_domain"):
    return match_scope(item, expected, default_match) is not None


def matched_items(vault, expected):
    # Unfiltered: apply the same per-URI policy here and on the subsequent get-item check.
    items = vault.json("list", "items")
    if not isinstance(items, list):
        raise Failure("Invalid item list")
    found = []
    for item in items:
        scope = match_scope(item, expected, vault.config.get("default_match", "base_domain"))
        if scope:
            found.append({"id": item_id(item.get("id")), "name": item.get("name"),
                          "username": item["login"].get("username"), "host": expected, **scope})
    return found


def pick(vault, request):
    """Without --id, one URI-matching login (narrowed by --username) in the same unlock as the copy."""
    if request["id"]:
        return request["id"]
    found = [item for item in matched_items(vault, request["host"])
             if request["username"] is None or str(item["username"] or "").lower() == request["username"].lower()]
    if not found:
        raise Failure("No login matches the destination and URI rules; Exact/StartsWith/Regex require a full URL and are excluded; Never is excluded. "
                      "This does not establish that the account is absent from the vault")
    if len(found) != 1:
        raise Failure(f"{len(found)} logins match; pass --username or --id (from `list`)")
    return found[0]["id"]


def operate(vault, request, payload):
    op = request["op"]
    if op == "list":
        return {"items": [item for item in matched_items(vault, request["host"]) if request["username"] is None
                          or str(item["username"] or "").lower() == request["username"].lower()]}, None
    if op == "copy":
        request = {**request, "id": pick(vault, request)}
        item = vault.json("get", "item", request["id"])
        scope = match_scope(item, request["host"], vault.config.get("default_match", "base_domain"))
        if not scope or str(item.get("id") or "").lower() != request["id"]:
            raise Failure("Item ID, login type or URI rule does not match")
        if request["username"] is not None and str(item["login"].get("username") or "").lower() != request["username"].lower():
            raise Failure("Item username does not match")
        if request["field"] == "totp":
            secret = vault.call("get", "totp", request["id"]).decode().strip()
            if not re.fullmatch(r"[0-9]{6,8}", secret):
                raise Failure("No valid generated TOTP code")
        else:
            secret = item["login"].get(request["field"])
        if not isinstance(secret, str) or not secret or "\x00" in secret:
            raise Failure("Requested field is missing or unsupported")
        return {"copied": request["field"], "id": request["id"], "name": item.get("name"),
                "username": item["login"].get("username"), "host": request["host"],
                "clear_after_seconds": 30, **scope}, secret
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


def clear_clipboard():
    """Right after the paste: drop our clipboard write now instead of at the 30-second timer."""
    helper = ROOT / "clipboard"
    if sys.platform != "darwin" or not helper.is_file():
        raise Failure("macOS clipboard helper missing; run installer first")
    try:
        done = subprocess.run([str(helper), "--clear-if-ours"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=clean_env(), timeout=5)
    except subprocess.TimeoutExpired:
        raise Failure("Clipboard clear timed out") from None
    if done.returncode or done.stdout not in (b"cleared\n", b"not-ours\n"):
        raise Failure("Clipboard clear failed")
    return {"ok": True, "cleared": done.stdout == b"cleared\n"}


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
                vault.unlock(request)
                result, secret = operate(vault, request, payload)
        finally:
            vault.relock()
        if secret is not None:
            deliver(secret)
        return result


def broker(request):
    """The compiled Touch ID broker (scripts/broker.swift): panel, Touch ID, Bitwarden, filter, lock, clipboard."""
    helper = ROOT / "bw-broker"
    if sys.platform != "darwin" or not helper.is_file():
        raise Failure("Touch ID broker missing; run installer first")
    # The first stdout line is the answer; with several matching logins the broker keeps running after it,
    # waiting for `bw-once pick`, so read that line instead of waiting for the process to exit.
    child = subprocess.Popen([str(helper)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env=clean_env(), start_new_session=True)
    try:
        child.stdin.write(json.dumps(request).encode())
        child.stdin.close()
        if not select.select([child.stdout], [], [], BROKER_SECONDS)[0]:
            raise ValueError
        result = json.loads(child.stdout.readline())
        if "pick" not in result and "recopy_until" not in result:  # Else it keeps running (pick / re-copies).
            child.wait(10)
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise Failure("Touch ID broker failed; nothing released") from None
    finally:
        child.stdout.close()


def submit_pick(token, item):
    """Name the login after a copy answered with `pick` (several logins match); the broker releases it."""
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise Failure("Use the pick token from the copy result")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(15)
    try:
        client.connect(str(cache_dir() / f"pick-{token}.sock"))
    except OSError:
        client.close()
        raise Failure("No pick waiting (expired after 60 s, cancelled, or already picked); ask again") from None
    with client:
        client.sendall(json.dumps({"id": item_id(item)}).encode() + b"\n")
        try:
            return json.loads(read_line(client))
        except ValueError:
            raise Failure("Invalid pick answer") from None


def recopy_socket(host_name, field, thread):
    """Same name as the broker's `recopyKey`: host, field and thread hashed to fit an AF_UNIX path."""
    key = hashlib.sha256("\n".join((host_name, field, thread)).encode()).hexdigest()[:32]
    return cache_dir() / f"recopy-v2-{key}.sock"


def via_recopy(request, thread, vaults, to="clipboard"):
    """The same thread re-copying the login the broker released minutes ago: no new touch. None → normal flow."""
    if request["op"] != "copy" or request["field"] == "totp" or not thread or not (request.get("id") or request.get("username")):
        return None
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(10)
    try:
        client.connect(str(recopy_socket(host(request["host"]), request["field"], thread)))
    except OSError:
        client.close()
        return None
    with client:
        client.sendall(json.dumps({"host": host(request["host"]), "field": request["field"], "thread": thread,
                                   "id": request.get("id") and item_id(request["id"]), "username": request.get("username"),
                                   "vaults": [vault["name"] for vault in vaults], "to": to}).encode() + b"\n")
        try:
            answer = json.loads(read_line(client))
        except (OSError, ValueError):
            return None
    return answer if answer.get("ok") else None


FILL_SELECTORS = {"password": "input[type=password]", "username": "input[autocomplete~=username], input[type=email]",
                  "totp": "input[autocomplete=one-time-code]"}


def fill_js(url, selector):
    """For `preview_evaluate` in the login tab: fetch the one-time value straight into the field; returns its length only."""
    return ("(async () => { const field = document.querySelector(%s); if (!field) return {ok: false, error: 'no field'};"
            " const answer = await fetch(%s, {cache: 'no-store', credentials: 'omit'}).catch(() => null);"
            " if (!answer || !answer.ok) return {ok: false, error: 'fetch blocked (page CSP?) or expired'};"
            " const value = await answer.text(); field.focus();"
            " Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(field, value);"
            " field.dispatchEvent(new Event('input', {bubbles: true})); field.dispatchEvent(new Event('change', {bubbles: true}));"
            " return {ok: true, length: field.value.length}; })()") % (json.dumps(selector), json.dumps(url))


def with_fill_js(result, selector=None):
    """A page delivery's one-time URL → the `preview_evaluate` snippet (copy and pick answers alike)."""
    if result.get("fill_url"):
        result["fill_js"] = fill_js(result.pop("fill_url"), selector or FILL_SELECTORS[result.get("copied", "password")])
    return result


def broker_vaults(name=None):
    """An explicit --vault → that one; otherwise every configured vault (the broker searches all enrolled ones)."""
    path = Path.home() / ".config" / "bw-once" / "vaults.json"
    names = [name] if name else sorted(json.loads(path.read_text())) if path.is_file() else []
    vaults = []
    for entry in names:
        config = vault_config(entry)
        if config.get("email"):
            vaults.append({key: config[key] for key in ("name", "email", "appdata", "default_match") if key in config})
    return vaults


def broker_enrolled(vaults):
    return bool(vaults) and sys.platform == "darwin" and (ROOT / "bw-broker").is_file() and \
        broker({"op": "status", "vaults": vaults}).get("enrolled") is True


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
                    try:
                        vault.relock()  # Acknowledge only a verified lock.
                        reply = {"ok": True, "active": False, "locked": True}
                    except Failure as error:
                        reply = {"ok": False, "active": False, "error": str(error)}
                    connection.sendall(json.dumps(reply).encode() + b"\n")
                    audit({"op": "session-stop", "ok": reply["ok"]})
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
                    audit({key: incoming.get(key) for key in ("op", "vault", "host", "id", "username", "field")
                           if incoming.get(key) is not None}
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
            vault.unlock(request)
            serve_session(vault, request, announce, deliver, audit)
        finally:
            vault.relock()
    return {"active": False}


def via_session(request):
    """Ask a running holder; None when there is none (caller falls back to the Terminal flow)."""
    path = session_socket(request["vault"])
    if not path.exists() and request["op"] in ("session-status", "session-stop"):
        path = cache_dir() / f"session-{vault_name(request['vault'])}.sock"  # Legacy holders: inspect/stop only.
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


def timed_confirm(*args):
    """The human may take WAIT_SECONDS to show up (vault locked); unlocking gets AUTH_SECONDS from approval."""
    approved = confirm(*args)
    signal.alarm(AUTH_SECONDS)
    return approved


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
    signal.alarm(WAIT_SECONDS)
    try:
        request = json.loads((directory / "request.json").read_text())
        if isinstance(request, dict) and request.get("op") == "session-start":
            def announce(status):
                signal.alarm(0)
                publish(directory, {"ok": True, **status})
                print(f"Session on vault '{status['vault']}' active until {status['expires_at']} for hosts "
                      f"{status['hosts'] or 'any'}. "
                      "Each request is logged below; Ctrl-C or `bw-once session stop` locks earlier.", flush=True)
            result = {"ok": True, **session_transaction(Vault(request["vault"]), request, ask=timed_confirm, announce=announce,
                                                        audit=lambda line: print(json.dumps(line), flush=True))}
        elif isinstance(request, dict) and request.get("op") == "login":
            result = {"ok": True, **login_transaction(Vault(request["vault"]), request, ask=timed_confirm)}
        else:
            result = {"ok": True, **transaction(Vault(request.get("vault")), request, ask=timed_confirm)}
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
            deadline = time.monotonic() + WAIT_SECONDS + AUTH_SECONDS + 20
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
    commands.add_parser("clear", help="clear the clipboard now if it still holds a bw-once copy")
    listing = commands.add_parser("list")
    listing.add_argument("--host", required=True)
    listing.add_argument("--username", help="only logins with this username (when you know the account)")
    copy = commands.add_parser("copy")
    copy.add_argument("--host", required=True)
    copy.add_argument("--id", help="item UUID from `list`; omit to pick the only exact-host login")
    copy.add_argument("--username", help="pick the exact-host login with this username (no --id needed)")
    copy.add_argument("--field", required=True, choices=("username", "password", "totp"))
    copy.add_argument("--to", choices=("clipboard", "page"), default="clipboard",
                      help="page: one fetch by the https://<host> page via the returned fill_js (Touch ID broker only)")
    copy.add_argument("--selector", help="CSS selector of the field fill_js fills (default per --field)")
    chosen = commands.add_parser("pick", help="after a copy listed several logins: name the one to release")
    chosen.add_argument("--token", required=True)
    chosen.add_argument("--id", required=True)
    chosen.add_argument("--selector", help="CSS selector for fill_js after a `copy --to page` (default per field)")
    for command in (listing, copy):
        command.add_argument("--thread", help="T3 thread title, shown in the Touch ID panel as the agent's claim")
        command.add_argument("--why", help="one line: why this login is needed (shown as the agent's claim)")
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
    touchid = commands.add_parser("touchid", help="Touch ID broker: enroll (native window) | status | forget")
    touchid.add_argument("action", choices=("enroll", "status", "forget"))
    args = vars(parser.parse_args())
    if args["op"] in ("session", "touchid"):
        action = args.pop("action")
        if not action:
            parser.error("Choose session start|stop|status")
        args["op"] = f"{args['op']}-{action}"
    try:
        reject_injection()
        directory = args.pop("worker")
        if directory:
            worker(directory)
            return
        if args["op"] == "clear":
            print(json.dumps(clear_clipboard()))
            return
        if args["op"] == "pick":
            result = with_fill_js(submit_pick(args["token"], args["id"]), args["selector"])
            print(json.dumps(result))
            raise SystemExit(0 if result.get("ok") else 1)
        explicit_vault = args["vault"]
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
                      "default_match": vault.config.get("default_match", "base_domain"),
                      "matching_scope": "host-only; browser defaults and equivalent domains not imported",
                      "bw_version": version, "touch_id_flag": touch_id_flag(vault),
                      "ready": state == "locked" and sys.platform == "darwin" and result_ok(status, expected),
                      "clipboard_ready": (ROOT / "clipboard").is_file(),
                      "touchid": broker({"op": "status", "vaults": broker_vaults(args["vault"])})
                      if broker_vaults(args["vault"]) and (ROOT / "bw-broker").is_file() else {"enrolled": False},
                      "session": via_session({"op": "session-status", "vault": args["vault"]}) or {"active": False}}
        elif args["op"] == "session-start":
            args["ttl"] = ttl_minutes(args["ttl"])
            result = launch(args)
        elif args["op"] in ("session-stop", "session-status"):
            result = via_session(args) or {"ok": True, "active": False}
        elif args["op"] in ("touchid-enroll", "touchid-status", "touchid-forget"):
            vaults = broker_vaults(explicit_vault)
            if not vaults:
                raise Failure("Touch ID needs vaults with an account email in ~/.config/bw-once/vaults.json")
            result = broker({"op": args["op"].removeprefix("touchid-"), "vaults": vaults})
            if args["op"] != "touchid-status" and result.get("ok"):
                for legacy in (Path.home() / ".config" / "bw-once").glob("touchid-*.json"):
                    legacy.unlink()  # Superseded per-vault enrolment files (pre-broker).
        elif args["op"] in ("list", "copy"):
            claim = {"thread": args.pop("thread"), "why": args.pop("why")}
            to, selector = args.pop("to", "clipboard"), args.pop("selector", None)
            vaults = broker_vaults(explicit_vault)
            result = None if to == "page" else via_session(args)  # Session and Terminal flows deliver to the clipboard.
            result = result or via_recopy(args, claim["thread"], vaults, to)
            if not result and broker_enrolled(vaults):
                # One Touch ID panel, every enrolled vault searched (or just --vault); no Terminal.
                fields = {key: args[key] for key in ("op", "host", "field", "username", "id") if args.get(key)}
                result = broker({**fields, **claim, **({"to": to} if args["op"] == "copy" else {}), "vaults": vaults})
            if not result and to == "page":
                raise Failure("--to page needs the Touch ID broker (bw-once touchid enroll)")
            result = with_fill_js(result or launch(args), selector)
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
