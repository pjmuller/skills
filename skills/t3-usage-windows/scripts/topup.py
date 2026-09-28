#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Open usage windows from 05:00 and keep the five-hour ones chained all day.

A LaunchAgent ticks every ~10 min, 05:00-21:00 every day. A profile whose session window
expired gets `t3-usage-windows start --profile <ids>` so a fresh window starts; a profile
with no session window (Codex: weekly only, start unknown) gets one turn per local day on the
first tick at/after 05:00. Deterministic, no LLM thread in the loop (in-thread timers die with
T3's session reaper or a Mac sleep).

    t3-usage-windows topup run [--dry-run] [--force] [--ignore-hours]
    t3-usage-windows topup install [--interval 600] | remove | status
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import plistlib
import shlex
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from local_timezone import system_timezone

TZ = system_timezone()
LABEL = "com.t3-skills.t3-usage-windows.topup"
LEGACY_LABEL = "com.t3-skills.t3-hello-world-topup"
PATH_ENV = "$HOME/.local/bin:$HOME/.local/share/mise/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
HERE = Path(__file__).resolve()
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
LOG = Path.home() / ".t3/userdata/logs/t3-usage-windows-topup.log"
STATE = LOG.with_name("t3-usage-windows-topup.state.json")  # {instance: last morning-start date}
RUNTIME = Path.home() / ".t3/userdata/server-runtime.json"
HELLO_WORLD = HERE.with_name("t3-usage-windows")
START_HOUR, END_HOUR = 5, 21
GRACE = 60  # seconds after expiry before a window counts as stale
DEFAULT_INTERVAL = 600
THREAD_VARS = ("T3_SOURCE_THREAD_ID", "CODEX_THREAD_ID", "T3_MCP_BEARER_TOKEN")


# --- pure functions (unit-tested) ---------------------------------------------
def within_hours(now: datetime) -> bool:
    """05:00 <= now < 21:00 system local time, every day."""
    return START_HOUR <= now.hour < END_HOUR


def morning_due(no_window: list[str], started: dict, now: datetime) -> list[str]:
    """No-session-window instances not yet started today (local date), from 05:00 on."""
    if now.hour < START_HOUR:
        return []
    today = now.date().isoformat()
    return [instance for instance in no_window if started.get(instance) != today]


def classify(rows: list[dict], force: bool = False) -> tuple[list[str], list[str], list[str]]:
    """(stale, unknown, no-window) instance ids from `t3-limits --json` rows.
    Stale = a session window whose reset is null or expired more than GRACE ago.
    Accounts that report no session window at all (Codex on the OAuth usage endpoint,
    observed 2026-09-08 even right after a turn) are never stale: a missing row is not
    evidence of an expired one and would re-fire every tick. They get one morning start
    per day instead (morning_due)."""
    sessions: dict[str, dict | None] = {}
    unknown: list[str] = []
    for row in rows:
        instance = row["instance_id"]
        if row.get("error"):
            unknown.append(instance)
            continue
        sessions.setdefault(instance, None)
        if row.get("window") == "session":
            sessions[instance] = row
    stale, no_window = [], []
    for instance, session in sessions.items():
        if instance in unknown:
            continue
        if session is None:
            no_window.append(instance)
        elif force or session.get("resets_in_seconds") is None or session["resets_in_seconds"] <= -GRACE:
            stale.append(instance)
    return stale, unknown, no_window


def wait_seconds(rows: list[dict], interval: int) -> int | None:
    """Sleep until the soonest upcoming session reset (+GRACE) when it lands inside
    this tick's interval — ~1-minute precision without polling faster. Bounded by
    construction: never more than interval + GRACE."""
    upcoming = [
        row["resets_in_seconds"]
        for row in rows
        if row.get("window") == "session" and (row.get("resets_in_seconds") or 0) > 0
    ]
    if not upcoming or min(upcoming) > interval:
        return None
    return min(upcoming) + GRACE


# --- environment ---------------------------------------------------------------
def log(message: str) -> None:
    stamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {message}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")
    print(line)  # launchd discards stdout; a terminal run sees the same line


def load_started() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_started(instances: list[str], now: datetime) -> None:
    started = load_started() | dict.fromkeys(instances, now.date().isoformat())
    STATE.write_text(json.dumps(started, indent=2, sort_keys=True) + "\n")


def clean_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in THREAD_VARS}
    env["PATH"] = os.path.expandvars(PATH_ENV)
    return env


def t3_up() -> bool:
    """server-runtime.json, else the last origin t3-common.sh saw (the file can vanish while
    the server keeps running — see t3_bootstrap in lib/t3-common.sh)."""
    try:
        if RUNTIME.exists():
            origin = json.loads(RUNTIME.read_text()).get("origin")
        else:
            origin = RUNTIME.with_name("last-server-origin").read_text().strip()
        if not origin:
            return False
        with urllib.request.urlopen(f"{origin}/.well-known/t3/environment", timeout=5):
            return True
    except (OSError, ValueError):
        return False


def limits_rows() -> list[dict]:
    command = ["t3-limits", "--json"]
    result = subprocess.run(command, check=False, capture_output=True, text=True, env=clean_env())
    if result.returncode not in (0, 1) or not result.stdout.strip():
        raise RuntimeError((result.stderr or "t3-limits failed").strip()[:160])
    return json.loads(result.stdout)


def installed_interval() -> int:
    try:
        return int(plistlib.loads(PLIST.read_bytes())["StartInterval"])
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException):
        return DEFAULT_INTERVAL


def launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], check=False, capture_output=True, text=True)


def loaded() -> bool:
    return launchctl("print", f"gui/{os.getuid()}/{LABEL}").returncode == 0


# --- commands ------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    now = datetime.now(TZ)
    if not args.ignore_hours and not within_hours(now):
        log("outside hours, skipped")
        return 0
    if not t3_up():
        log("T3 Code not up, skipped")
        return 0
    try:
        rows = limits_rows()
        if getattr(args, "profile", None):
            from profiles import filter_rows
            rows = filter_rows(rows, args.profile)
    except (RuntimeError, ValueError) as error:
        log(f"t3-limits failed: {error}")
        return 0

    stale, unknown, no_window = classify(rows, args.force)
    due = no_window if args.force else morning_due(no_window, load_started(), now)
    if not stale and not due:
        wait = wait_seconds(rows, args.interval or installed_interval())
        if wait and not args.dry_run:
            log(f"all fresh, waiting {wait}s for the next session reset")
            time.sleep(wait)
            if not args.ignore_hours and not within_hours(datetime.now(TZ)):
                log("outside hours after wait, skipped")
                return 0
            try:
                rows = limits_rows()
            except (RuntimeError, ValueError) as error:
                log(f"t3-limits failed after wait: {error}")
                return 0
            if getattr(args, "profile", None):
                from profiles import filter_rows
                rows = filter_rows(rows, args.profile)
            stale, unknown, no_window = classify(rows, args.force)
            now = datetime.now(TZ)
            due = no_window if args.force else morning_due(no_window, load_started(), now)

    note = f" · unknown, skipped: {','.join(unknown)}" if unknown else ""
    done_today = [i for i in no_window if i not in due]
    note += f" · no session window, started today: {','.join(done_today)}" if done_today else ""
    if not stale and not due:
        log(f"all windows fresh, nothing to do{note}")
        return 0

    # Separate starts so a failing Claude profile never re-fires the once-a-day ones.
    batches = [(label, ids) for label, ids in (("stale", stale), ("morning", due)) if ids]
    code = 0
    for label, ids in batches:
        command = [str(HELLO_WORLD), "start", "--profile", ",".join(ids)]
        if args.dry_run:
            log(f"dry-run: {label} {','.join(ids)}{note} → {' '.join(command)}")
            continue
        result = subprocess.run(command, check=False, capture_output=True, text=True, env=clean_env())
        log((result.stdout + result.stderr).strip())
        if result.returncode == 0 and label == "morning":
            save_started(ids, now)  # a failed start retries next tick
        log(f"topup: {label} {','.join(ids)} → {'ok' if result.returncode == 0 else 'FAILED'}{note}")
        code = code or result.returncode
    return code


def cmd_install(args: argparse.Namespace) -> int:
    if args.interval <= 0:
        raise SystemExit("--interval must be positive")
    if args.dry_run:
        print(f"would migrate {LEGACY_LABEL} to {LABEL}, every {args.interval}s")
        return 0
    legacy = LEGACY_LABEL
    launchctl("bootout", f"gui/{os.getuid()}/{legacy}")
    if launchctl("print", f"gui/{os.getuid()}/{legacy}").returncode == 0:
        raise SystemExit(f"cannot unload legacy job: {legacy}; retry install")
    PLIST.with_name(f"{legacy}.plist").unlink(missing_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(
        plistlib.dumps(
            {
                "Label": LABEL,
                "ProgramArguments": ["/bin/zsh", "-lc", shlex.quote(str(HELLO_WORLD)) + " topup run"],
                "StartInterval": args.interval,
                "RunAtLoad": False,
                "ProcessType": "Interactive",  # Standard still gets a utility clamp: t3 CLI 15-25s per call vs <1s (A/B 2026-09-09)
            }
        )
    )
    if loaded():
        launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    result = launchctl("bootstrap", f"gui/{os.getuid()}", str(PLIST))
    if result.returncode != 0:
        raise SystemExit(f"launchctl bootstrap failed: {result.stderr.strip()}")
    print(f"armed  {LABEL}  every {args.interval}s (daily {START_HOUR}:00-{END_HOUR}:00)")
    print(f"log    {LOG}")
    return 0


def cmd_uninstall(_args: argparse.Namespace) -> int:
    if _args.dry_run:
        print(f"would remove {LABEL}")
        return 0
    launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    if loaded():
        raise SystemExit(f"cannot unload {LABEL}; plist retained")
    PLIST.unlink(missing_ok=True)
    print(f"removed {LABEL} (log kept: {LOG})")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    if getattr(_args, "json", False):
        print(json.dumps({"label": LABEL, "loaded": loaded(), "interval": installed_interval(),
                          "legacy_loaded": launchctl("print", f"gui/{os.getuid()}/{LEGACY_LABEL}").returncode == 0}))
        return 0
    print(f"{LABEL}: {'loaded' if loaded() else 'NOT loaded'} · every {installed_interval()}s")
    lines = LOG.read_text().splitlines()[-5:] if LOG.exists() else []
    print("\n".join(lines) or f"(no log yet: {LOG})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="t3-usage-windows topup", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="one tick")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--json", action="store_true")
    run.add_argument("--profile")
    run.add_argument("--force", action="store_true", help="treat every known account as stale")
    run.add_argument("--ignore-hours", action="store_true", help="skip the 05:00-21:00 gate")
    run.add_argument("--interval", type=int, help="tick length for the smart wait (default: the plist's)")
    run.set_defaults(func=cmd_run)

    install = sub.add_parser("install", help="arm the LaunchAgent")
    install.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--json", action="store_true")
    install.set_defaults(func=cmd_install)

    remove = sub.add_parser("remove", help="bootout + remove the plist")
    remove.add_argument("--dry-run", action="store_true")
    remove.add_argument("--json", action="store_true")
    remove.set_defaults(func=cmd_uninstall)
    status = sub.add_parser("status", help="loaded?, interval, last log lines")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)
    args = parser.parse_args(argv)
    if getattr(args, "json", False) and args.command != "status":
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = args.func(args)
        print(json.dumps({"ok": code == 0, "output": output.getvalue()}))
        return code
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
