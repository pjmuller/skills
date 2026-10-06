"""One fixed vault operation per human Terminal unlock; never a session broker."""
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
import stat
import subprocess
import sys
import tempfile
import termios
import time
from urllib.parse import urlsplit
import uuid

AUTH_SECONDS = 180
FILE_LIMIT = 50 * 1024 * 1024
TEXT_LIMIT = 600  # Conservative UTF-8 pilot cap, below the encrypted-text limit.
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


def validate(request):
    op = request.get("op")
    allowed = {"list": {"op", "host"}, "copy": {"op", "host", "id", "field"},
               "send-text": {"op", "input_file", "name", "views"},
               "send-file": {"op", "input_file", "name", "views"}}
    if op not in allowed or set(request) != allowed[op]:
        raise Failure("Invalid request")
    request = dict(request)
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
        if not isinstance(request["input_file"], str):
            raise Failure("Invalid input file")
        request["input_file"] = str(Path(request["input_file"]).expanduser().resolve())
    return request


class Vault:
    def __init__(self):
        self.binary = shutil.which("bw")
        if not self.binary:
            raise Failure("Bitwarden CLI is missing")
        self.env = clean_env()
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
        if self.json("status").get("status") != "locked":
            raise Failure("CLI must be logged in and locked; login manually first")

    def relock(self):
        with shield_cleanup():
            try:
                self.call("lock")
                self.locked()  # Keep the former session for this verification.
            except Exception:
                raise Failure("CLI lock verification failed; result withheld, lock manually now") from None
            finally:
                self.session = None


@contextmanager
def mutex():
    cache = Path.home() / ".cache" / "bw-once"
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    if cache.is_symlink() or cache.stat().st_uid != os.getuid():
        raise Failure("Unsafe helper lock directory")
    os.chmod(cache, 0o700)
    fd = os.open(cache / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
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
    until = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
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


def confirm(request, payload):
    print("Bitwarden one-time request (master password follows):", flush=True)
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


def transaction(vault, request, ask=confirm, deliver=clipboard):
    request = validate(request)
    with mutex():
        if request["op"] == "copy" and deliver is clipboard and not (ROOT / "clipboard").is_file():
            raise Failure("Clipboard helper missing; run installer first")
        vault.relock()
        try:
            if request["op"] in ("list", "copy"):
                vault.call("sync")
                vault.locked()
            with snapshot(request) as payload:
                if not ask(request, payload):
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
        result = {"ok": True, **transaction(Vault(), request)}
    except Failure as error:
        result = {"ok": False, "error": str(error)}
    except Exception:
        result = {"ok": False, "error": "Request failed; CLI result withheld"}
    finally:
        signal.alarm(0)
    try:
        private_json(directory / "result.tmp", result)
        os.rename(directory / "result.tmp", directory / "result.json")
    except OSError:
        print("Result channel closed; CLI cleanup finished. Close this Terminal window.", flush=True)
        return
    print("Request finished. Close this Terminal window.", flush=True)


def launch(request):
    if sys.platform != "darwin" or not shutil.which("osascript"):
        raise Failure("A real macOS Terminal is required; no noninteractive fallback")
    request = validate(request)
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
            if (path / "worker.json").is_file() and not (path / "result.json").is_file():
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
    commands = parser.add_subparsers(dest="op")
    commands.add_parser("status")
    commands.add_parser("doctor")
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
    args = vars(parser.parse_args())
    try:
        reject_injection()
        directory = args.pop("worker")
        if directory:
            worker(directory)
            return
        if args["op"] in ("status", "doctor"):
            vault = Vault()
            state = vault.json("status").get("status")
            version = vault.call("--version").decode().strip()
            if not re.fullmatch(r"\d+\.\d+\.\d+(?:[\w.-]*)", version):
                raise Failure("Invalid CLI version response")
            result = {"ok": True, "status": state if state in ("locked", "unlocked", "unauthenticated") else "unknown",
                      "bw_version": version, "ready": state == "locked" and sys.platform == "darwin",
                      "clipboard_ready": (ROOT / "clipboard").is_file()}
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
