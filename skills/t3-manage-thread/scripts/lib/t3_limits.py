#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Print the current subscription rate-limit windows for every Claude profile T3 Code
knows about, plus Codex.

Read-only and deterministic: T3's `settings.json` lists the enabled `claudeAgent`
provider instances, each one's OAuth token is read from the macOS Keychain, and the
percentages come from Anthropic's `/api/oauth/usage`. Tokens are never printed and
never refreshed (a refresh would rotate them out from under Claude Code itself); an
expired token just reports itself. Codex comes from the CodexBar CLI.

    t3-limits                     # one aligned block per account (Europe/Brussels)
    t3-limits --json              # flat rows for other scripts
    t3-limits --markdown          # one table, for pasting into a chat / routing decision
    t3-limits --profile work    # substring of instance id / display name / "codex"
    t3-limits --claude-only | --codex-only
    t3-limits --fresh             # skip the 90s cache (see limits.md)

Percentages are **used**, not left (CodexBar's menubar shows the inverse).
Pace: `pace` = the share of the window that has elapsed (what an evenly spread
load would have used by now); `room` = pace - used, so +20 means the account is
20 points under pace (spare capacity), -20 means it is burning faster than even.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Brussels")
SETTINGS = Path(os.environ.get("T3CODE_HOME", Path.home() / ".t3")) / "userdata" / "settings.json"
KEYCHAIN_BASE = "Claude Code-credentials"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
HEADERS = {"anthropic-beta": "oauth-2025-04-20", "User-Agent": "t3-limits/0.1"}
TIMEOUT = 10
CACHE = SETTINGS.parent / "t3-limits-cache.json"
FRESH_SECONDS = 90  # windows only move on the minute scale
STALE_SECONDS = 15 * 60  # older than this and "no data" beats a wrong number
MAX_RETRY_SECONDS = 5
SESSION_SECONDS = 5 * 3600
WEEKLY_SECONDS = 7 * 86400
CURRENCY = {"EUR": "€", "USD": "$", "GBP": "£"}
EXPIRED_HINT = "token expired — run any turn in that profile to refresh"


def debug(message: str) -> None:
    if os.environ.get("T3_LIMITS_DEBUG"):
        print(f"t3-limits: {message}", file=sys.stderr)


@dataclass
class Row:
    window: str
    used_percent: float
    resets_at: datetime | None
    length_seconds: int | None = None

    def pace(self, now: datetime) -> tuple[float, float] | None:
        """(expected used %, room) for an evenly spread load; None when the window
        has no reset time or no known length."""
        if self.resets_at is None or not self.length_seconds:
            return None
        remaining = (self.resets_at - now).total_seconds()
        if remaining <= 0:  # stale window (no request since it ended)
            return None
        expected = 100 * (1 - remaining / self.length_seconds)
        expected = min(100.0, max(0.0, expected))
        return expected, expected - self.used_percent


@dataclass
class Account:
    label: str
    instance_id: str
    plan: str = ""
    rows: list[Row] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""
    stale: bool = False  # served from cache after a failed fetch
    fetched_at: datetime | None = None


# --- Claude ------------------------------------------------------------------


def keychain_service(home_path: str) -> str:
    """T3's per-profile Claude config dir maps to its own Keychain item; the empty
    home path is Claude Code's default install."""
    if not home_path:
        return KEYCHAIN_BASE
    absolute = str(Path(home_path).expanduser())
    digest = hashlib.sha256(unicodedata.normalize("NFC", absolute).encode()).hexdigest()
    return f"{KEYCHAIN_BASE}-{digest[:8]}"


def claude_profiles(settings_path: Path) -> list[tuple[str, str, str]]:
    """(instance_id, display name, home path) for enabled claudeAgent instances."""
    try:
        settings = json.loads(settings_path.read_text())
        instances = dict(settings.get("providerInstances", {}))
    except (OSError, ValueError):
        return []
    # Mirror the built-in Claude fallback when T3 resets provider settings.
    if "claudeAgent" not in instances:
        legacy = settings.get("providers", {}).get("claudeAgent", {})
        instances["claudeAgent"] = {"driver": "claudeAgent", "enabled": legacy.get("enabled", True)}
    found = []
    for instance_id, entry in instances.items():
        if entry.get("driver") != "claudeAgent" or entry.get("enabled") is False or (entry.get("config") or {}).get("enabled") is False:
            continue
        label = entry.get("displayName") or instance_id
        home = (entry.get("config") or {}).get("homePath") or ""
        found.append((instance_id, label, home))
    return found


def keychain_token(service: str) -> dict:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-w"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise LookupError(f"no Keychain item {service}")
    return json.loads(result.stdout).get("claudeAiOauth") or {}


def fetch_claude_usage(token: str) -> dict:
    request = urllib.request.Request(
        USAGE_URL, headers={"Authorization": f"Bearer {token}", **HEADERS}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())




def read_cache(path: Path) -> dict:
    """Last good usage payload per profile instance id (never tokens)."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def write_cache(cache: dict, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(cache))
        temporary.chmod(0o600)
        temporary.replace(path)
    except OSError as error:
        debug(f"cache write failed: {error}")


def retry_delay(error: Exception) -> float:
    header = getattr(error, "headers", None)
    try:
        return min(MAX_RETRY_SECONDS, max(0.0, float((header or {}).get("Retry-After"))))
    except (TypeError, ValueError):
        return 1.0


def fetch_with_retry(token: str, fetch) -> dict:
    """The usage endpoint is shared with other pollers, so a 429 is routine: back off
    once (honouring Retry-After) before the caller falls back to its cache."""
    try:
        return fetch(token)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise
        delay = retry_delay(error)
    except urllib.error.URLError:
        delay = 1.0
    debug(f"retrying in {delay:.1f}s")
    time.sleep(delay)
    return fetch(token)


def claude_rows(payload: dict) -> tuple[list[Row], list[str]]:
    rows: list[Row] = []
    for limit in payload.get("limits") or []:
        kind = limit.get("kind")
        if kind == "session":
            window = "session"
        elif kind == "weekly_all":
            window = "weekly"
        elif kind == "weekly_scoped":
            model = ((limit.get("scope") or {}).get("model") or {}).get("display_name")
            window = f"{model or 'scoped'} only"
        else:
            continue
        rows.append(
            Row(
                window,
                float(limit.get("percent") or 0),
                parse_time(limit.get("resets_at")),
                SESSION_SECONDS if kind == "session" else WEEKLY_SECONDS,
            )
        )
    if not rows:  # older payloads: only the two top-level windows
        for key, window, length in (
            ("five_hour", "session", SESSION_SECONDS),
            ("seven_day", "weekly", WEEKLY_SECONDS),
            ("seven_day_opus", "Opus only", WEEKLY_SECONDS),
            ("seven_day_sonnet", "Sonnet only", WEEKLY_SECONDS),
            ("seven_day_fable", "Fable only", WEEKLY_SECONDS),
        ):
            entry = payload.get(key) or {}
            if entry.get("utilization") is not None:
                rows.append(
                    Row(
                        window,
                        float(entry["utilization"]),
                        parse_time(entry.get("resets_at")),
                        length,
                    )
                )

    # `extra_usage` (paid overage) is deliberately not reported: enabling it is a conscious
    # decision to keep working, never a routing signal — see limits.md.
    return rows, []


def claude_accounts(
    fetch=fetch_claude_usage,
    settings_path: Path = SETTINGS,
    cache_path: Path = CACHE,
    fresh: bool = False,
    now: datetime | None = None,
) -> list[Account]:
    now = now or datetime.now(timezone.utc)
    cache = read_cache(cache_path)
    accounts, dirty = [], False
    for instance_id, label, home in claude_profiles(settings_path):
        account = Account(label=label, instance_id=instance_id)
        entry = cache.get(instance_id) or {}
        entry = entry if entry.get("payload") else {}
        age = now.timestamp() - float(entry.get("fetched_at") or 0) if entry else None
        credentials: dict = {}
        payload = None
        try:
            credentials = keychain_token(keychain_service(home))
            if entry and not fresh and age < FRESH_SECONDS:
                debug(f"{instance_id}: cache hit ({age:.0f}s old)")
                payload = entry["payload"]
            else:
                payload = fetch_with_retry(credentials["accessToken"], fetch)
                cache[instance_id] = {"payload": payload, "fetched_at": now.timestamp()}
                dirty = True
        except urllib.error.HTTPError as error:
            account.error = EXPIRED_HINT if error.code == 401 else f"HTTP {error.code}"
        except (LookupError, KeyError, OSError, ValueError) as error:
            account.error = str(error) or error.__class__.__name__
        if account.error and account.error != EXPIRED_HINT and entry and age < STALE_SECONDS:
            debug(f"{instance_id}: {account.error} — serving cache ({age:.0f}s old)")
            payload, account.error = entry["payload"], ""
            account.stale, account.fetched_at = True, now - timedelta(seconds=age)
        if payload is not None:
            # The tier can disagree with the plan (a Pro account reporting `max_20x`);
            # show both rather than a single misleading label. See limits.md.
            tier = str(credentials.get("rateLimitTier") or "").removeprefix("default_claude_")
            subscription = str(credentials.get("subscriptionType") or "")
            if tier and subscription and not tier.startswith(subscription):
                account.plan = f"{tier} ({subscription})"
            else:
                account.plan = tier or subscription
            account.rows, account.notes = claude_rows(payload)
        accounts.append(account)
    if dirty:
        write_cache(cache, cache_path)
    return accounts


# --- Codex -------------------------------------------------------------------


def fetch_codex_usage() -> dict:
    result = subprocess.run(
        [
            "codexbar",
            "usage",
            "--provider",
            "codex",
            "--format",
            "json",
            "--no-credits",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or result.stdout).strip()[:120] or "codexbar failed"
        )
    payload = json.loads(result.stdout)
    return payload[0] if isinstance(payload, list) else payload


def codex_account(fetch=fetch_codex_usage) -> Account:
    account = Account(label="Codex", instance_id="codex")
    try:
        payload = fetch()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        account.error = str(error) or error.__class__.__name__
        return account
    if payload.get("error"):
        account.error = str(payload["error"])[:120]
        return account

    usage = payload.get("usage") or {}
    account.label = f"Codex  {usage.get('accountEmail') or '-'}"
    account.plan = str(usage.get("loginMethod") or "")
    # Only the top-level windows; the Spark sub-windows (extraRateWindows) are noise.
    for key, window, length in (
        ("primary", "session", SESSION_SECONDS),
        ("secondary", "weekly", WEEKLY_SECONDS),
    ):
        entry = usage.get(key)
        if not entry:
            continue
        minutes = entry.get("windowMinutes")
        account.rows.append(
            Row(
                window,
                float(entry.get("usedPercent") or 0),
                parse_time(entry.get("resetsAt")),
                int(minutes) * 60 if minutes else length,
            )
        )
    credits = (usage.get("codexResetCredits") or {}).get("availableCount")
    if credits:
        account.notes.append(f"reset credits: {credits}")
    return account


# --- formatting --------------------------------------------------------------


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def relative(seconds: float) -> str:
    if seconds <= 0:
        return "now"
    if seconds >= 86400:
        return f"in {int(seconds // 86400)}d{int(seconds % 86400 // 3600):02d}h"
    if seconds >= 3600:
        return f"in {int(seconds // 3600)}h{int(seconds % 3600 // 60):02d}"
    return f"in {max(1, int(seconds // 60))}m"


def reset_text(when: datetime | None, now: datetime) -> str:
    if when is None:
        return "no reset"
    local = when.astimezone(TZ)
    clock = local.strftime("%H:%M")
    if local.date() != now.astimezone(TZ).date():
        clock = local.strftime("%b %-d ") + clock
    return f"resets {clock} ({relative((when - now).total_seconds())})"


PACE_LEGEND = "pace = % of window elapsed · room = pace − used (+ under pace, − over pace)"


def relative_age(account: Account, now: datetime) -> str:
    seconds = (now - account.fetched_at).total_seconds() if account.fetched_at else 0
    return f"{int(seconds // 60)}m" if seconds >= 60 else f"{int(seconds)}s"


def pace_text(row: Row, now: datetime) -> str:
    pace = row.pace(now)
    if pace is None:
        return "pace   -   room   -"
    expected, room = pace
    return f"pace {expected:3.0f}%  room {room:+4.0f}"


def render(accounts: list[Account], now: datetime) -> str:
    rows = [row for account in accounts for row in account.rows]
    width = max((len(row.window) for row in rows), default=7)
    out = [PACE_LEGEND]
    for account in accounts:
        head = f"{account.label}"
        if account.instance_id != "codex":
            head += f"  ({account.instance_id})"
        if account.stale:
            head += f"  (cached {relative_age(account, now)} ago)"
        out.append(f"{head}  {account.plan}".rstrip())
        if account.error:
            out.append(f"  {account.error}")
        for row in account.rows:
            out.append(
                f"  {row.window:<{width}} {row.used_percent:3.0f}% used   "
                f"{pace_text(row, now)}   {reset_text(row.resets_at, now)}"
            )
        out.extend(f"  {note}" for note in account.notes)
    return "\n".join(out)


def render_markdown(accounts: list[Account], now: datetime) -> str:
    stamp = now.astimezone(TZ).strftime("%a %Y-%m-%d %H:%M %Z")
    out = [
        f"Rate limits at {stamp} — {PACE_LEGEND}",
        "",
        "| profile | instance | window | used | pace | room | resets |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for account in accounts:
        if account.error:
            out.append(
                f"| {account.label} | `{account.instance_id}` | — | | | | {account.error} |"
            )
        for row in account.rows:
            pace = row.pace(now)
            expected = f"{pace[0]:.0f}%" if pace else "-"
            room = f"{pace[1]:+.0f}" if pace else "-"
            out.append(
                f"| {account.label} | `{account.instance_id}` | {row.window} "
                f"| {row.used_percent:.0f}% | {expected} | {room} "
                f"| {reset_text(row.resets_at, now).removeprefix('resets ')} |"
            )
        for note in account.notes:
            out.append(f"| {account.label} | `{account.instance_id}` | {note} | | | | |")
    return "\n".join(out)


def json_rows(accounts: list[Account], now: datetime) -> list[dict]:
    out = []
    for account in accounts:
        if account.error:  # consumers must tell "unknown" from "stale"
            out.append(
                {
                    "account": account.label,
                    "instance_id": account.instance_id,
                    "window": None,
                    "error": account.error,
                }
            )
        for row in account.rows:
            pace = row.pace(now)
            out.append(
                {
                    "account": account.label,
                    "instance_id": account.instance_id,
                    "window": row.window,
                    "used_percent": row.used_percent,
                    "window_seconds": row.length_seconds,
                    "pace_percent": round(pace[0], 1) if pace else None,
                    "room_percent": round(pace[1], 1) if pace else None,
                    "resets_at": row.resets_at.isoformat().replace("+00:00", "Z")
                    if row.resets_at
                    else None,
                    "resets_in_seconds": int((row.resets_at - now).total_seconds())
                    if row.resets_at
                    else None,
                    **(
                        {
                            "stale": True,
                            "fetched_at": account.fetched_at.isoformat().replace(
                                "+00:00", "Z"
                            )
                            if account.fetched_at
                            else None,
                        }
                        if account.stale
                        else {}
                    ),
                }
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="flat rows for scripts")
    fmt.add_argument("--markdown", action="store_true", help="one markdown table")
    parser.add_argument(
        "--profile", help="substring of instance id / display name / 'codex'"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="skip the 90s usage cache"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--claude-only", action="store_true")
    group.add_argument("--codex-only", action="store_true")
    args = parser.parse_args(argv)

    accounts: list[Account] = []
    if not args.codex_only:
        accounts += claude_accounts(fresh=args.fresh)
    if not args.claude_only:
        accounts.append(codex_account())
    if args.profile:
        needle = args.profile.casefold()
        accounts = [
            account
            for account in accounts
            if needle in account.instance_id.casefold()
            or needle in account.label.casefold()
        ]
    if not accounts:
        print("No matching accounts.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    if args.json:
        print(json.dumps(json_rows(accounts, now), indent=2))
    elif args.markdown:
        print(render_markdown(accounts, now))
    else:
        print(render(accounts, now))
    return 1 if all(account.error for account in accounts) else 0


if __name__ == "__main__":
    raise SystemExit(main())
