#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Print the current subscription rate-limit windows for every Claude and Codex
profile T3 Code knows about.

Read-only and deterministic: T3's `settings.json` lists the enabled provider
instances; each Claude instance's OAuth token is read from the macOS Keychain and
each Codex instance's from `<home>/auth.json`; the percentages come from Anthropic's
`/api/oauth/usage` and ChatGPT's `/backend-api/wham/usage`. Tokens are never printed
and never refreshed (a refresh would rotate them out from under the CLI itself); an
expired token just reports itself.

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
import math
import os
import subprocess
import sys
import tempfile
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
CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
CODEX_HOME = Path.home() / ".codex"  # Codex CLI default; T3's empty homePath
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
        if self.resets_at is None or not self.length_seconds or math.isnan(self.used_percent):
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


def provider_profiles(settings_path: Path, driver: str) -> list[tuple[str, str, str]]:
    """(instance_id, display name, home path) for enabled instances of one driver."""
    try:
        settings = json.loads(settings_path.read_text())
        instances = dict(settings.get("providerInstances", {}))
    except (OSError, ValueError):
        return []
    # Mirror T3's built-in fallback when provider settings were reset: the driver
    # name doubles as the default instance id.
    if driver not in instances:
        legacy = settings.get("providers", {}).get(driver, {})
        instances[driver] = {"driver": driver, "enabled": legacy.get("enabled", True)}
    found = []
    for instance_id, entry in instances.items():
        if entry.get("driver") != driver or entry.get("enabled") is False or (entry.get("config") or {}).get("enabled") is False:
            continue
        label = entry.get("displayName") or instance_id
        home = (entry.get("config") or {}).get("homePath") or ""
        found.append((instance_id, label, home))
    return found


def claude_profiles(settings_path: Path) -> list[tuple[str, str, str]]:
    return provider_profiles(settings_path, "claudeAgent")


def codex_profiles(settings_path: Path) -> list[tuple[str, str, str]]:
    return provider_profiles(settings_path, "codex")


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
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name)  # 0600
        with os.fdopen(handle, "w") as stream:
            stream.write(json.dumps(cache))
        os.replace(temporary, path)
    except OSError as error:
        debug(f"cache write failed: {error}")


def retry_delay(error: Exception) -> float:
    header = getattr(error, "headers", None)
    try:
        return min(MAX_RETRY_SECONDS, max(0.0, float((header or {}).get("Retry-After"))))
    except (TypeError, ValueError):
        return 1.0


def fetch_with_retry(credentials, fetch) -> dict:
    """The usage endpoints are shared with other pollers, so a 429 is routine: back off
    once (honouring Retry-After) before the caller falls back to its cache."""
    try:
        return fetch(credentials)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise
        delay = retry_delay(error)
    except urllib.error.URLError:
        delay = 1.0
    debug(f"retrying in {delay:.1f}s")
    time.sleep(delay)
    return fetch(credentials)


def percent(value) -> float:
    """A missing percentage is unknown (NaN), never 0 — routing treats NaN as unverified."""
    try:
        return float(value) if value is not None else math.nan
    except (TypeError, ValueError):
        return math.nan


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
                percent(limit.get("percent")),
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
                        percent(entry["utilization"]),
                        parse_time(entry.get("resets_at")),
                        length,
                    )
                )

    # `extra_usage` (paid overage) is deliberately not reported: enabling it is a conscious
    # decision to keep working, never a routing signal — see limits.md.
    return rows, []


def collect(
    profiles: list[tuple[str, str, str]],
    credentials_for,
    fetch,
    parse,
    cache_path: Path,
    fresh: bool,
    now: datetime,
) -> list[Account]:
    """One Account per T3 instance: local credential → usage payload → rows, with
    the shared fresh/stale cache keyed by instance id (never tokens). A cache entry
    is only valid for the identity (home path + account id) that produced it."""
    cache = read_cache(cache_path)
    accounts, dirty = [], False
    for instance_id, label, home in profiles:
        account = Account(label=label, instance_id=instance_id)
        credentials: dict = {}
        payload = None
        entry: dict = {}
        age = None
        try:
            credentials = credentials_for(home)
            identity = f"{home}|{credentials.get('identity', '')}"
            entry = cache.get(instance_id) or {}
            entry = entry if entry.get("payload") and entry.get("identity") == identity else {}
            age = now.timestamp() - float(entry.get("fetched_at") or 0) if entry else None
            if entry and not fresh and age < FRESH_SECONDS:
                debug(f"{instance_id}: cache hit ({age:.0f}s old)")
                payload = entry["payload"]
            else:
                payload = fetch_with_retry(credentials, fetch)
                cache[instance_id] = {"payload": payload, "fetched_at": now.timestamp(),
                                      "identity": identity}
                dirty = True
        except urllib.error.HTTPError as error:
            account.error = EXPIRED_HINT if error.code in (401, 403) else f"HTTP {error.code}"
        except (LookupError, KeyError, OSError, ValueError) as error:
            account.error = str(error) or error.__class__.__name__
        if account.error and entry:
            account.fetched_at = now - timedelta(seconds=age)
            if account.error != EXPIRED_HINT and age < STALE_SECONDS:
                debug(f"{instance_id}: {account.error} — serving cache ({age:.0f}s old)")
                payload, account.error, account.stale = entry["payload"], "", True
            else:
                # Too old to trust as a reading, but an exhausted cap is still a fact
                # until its reset: keep only that evidence next to the error.
                try:
                    _, rows, _ = parse(entry["payload"], credentials)
                    account.rows = [r for r in rows if r.used_percent >= 100 and
                                    r.resets_at is not None and r.resets_at > now]
                except (TypeError, ValueError, KeyError, AttributeError, OverflowError):
                    pass
        if payload is not None:
            try:
                account.plan, account.rows, account.notes = parse(payload, credentials)
            except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as error:
                # One malformed payload must not abort the other accounts: unknown, not a crash.
                account.error, account.rows, account.stale = f"malformed usage payload ({error.__class__.__name__})", [], False
        accounts.append(account)
    if dirty:
        write_cache(cache, cache_path)
    return accounts


def claude_plan(credentials: dict) -> str:
    # The tier can disagree with the plan (a Pro account reporting `max_20x`);
    # show both rather than a single misleading label. See limits.md.
    tier = str(credentials.get("rateLimitTier") or "").removeprefix("default_claude_")
    subscription = str(credentials.get("subscriptionType") or "")
    if tier and subscription and not tier.startswith(subscription):
        return f"{tier} ({subscription})"
    return tier or subscription


def claude_accounts(
    fetch=fetch_claude_usage,
    settings_path: Path = SETTINGS,
    cache_path: Path = CACHE,
    fresh: bool = False,
    now: datetime | None = None,
) -> list[Account]:
    return collect(
        claude_profiles(settings_path),
        lambda home: keychain_token(keychain_service(home)),
        lambda credentials: fetch(credentials["accessToken"]),
        lambda payload, credentials: (claude_plan(credentials), *claude_rows(payload)),
        cache_path, fresh, now or datetime.now(timezone.utc),
    )


# --- Codex -------------------------------------------------------------------


def codex_credentials(home_path: str) -> dict:
    """Codex CLI's login for one home (`auth.json`); the empty T3 homePath is the
    default `~/.codex`. API-key logins have no subscription windows."""
    path = (Path(home_path).expanduser() if home_path else CODEX_HOME) / "auth.json"
    if not path.exists():
        raise LookupError(f"no Codex login in {path.parent}")
    auth = json.loads(path.read_text())
    tokens = auth.get("tokens") or {}
    if auth.get("auth_mode") not in (None, "chatgpt") or not tokens.get("access_token"):
        raise LookupError(f"no ChatGPT login in {path.parent} (auth_mode {auth.get('auth_mode')})")
    account_id = tokens.get("account_id") or ""
    return {"accessToken": tokens["access_token"], "accountId": account_id, "identity": account_id}


def fetch_codex_usage(credentials: dict) -> dict:
    request = urllib.request.Request(
        CODEX_USAGE_URL,
        headers={
            "Authorization": f"Bearer {credentials['accessToken']}",
            "ChatGPT-Account-Id": credentials.get("accountId", ""),
            "User-Agent": HEADERS["User-Agent"],
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())


def window_name(seconds: int | None) -> str:
    if seconds == SESSION_SECONDS:
        return "session"
    if seconds == WEEKLY_SECONDS:
        return "weekly"
    return f"{(seconds or 0) // 3600}h"


def codex_rows(payload: dict) -> tuple[str, list[Row], list[str]]:
    """(plan, rows, notes) from ChatGPT's usage endpoint. Only the subscription
    windows become rows; model reserves and reset credits are notes."""
    rows: list[Row] = []
    limit = payload.get("rate_limit") or {}
    for key in ("primary_window", "secondary_window"):
        entry = limit.get(key)
        if not entry:
            continue
        seconds = entry.get("limit_window_seconds")
        reset = entry.get("reset_at")
        rows.append(
            Row(
                window_name(seconds),
                percent(entry.get("used_percent")),
                datetime.fromtimestamp(reset, timezone.utc) if reset else None,
                int(seconds) if seconds else None,
            )
        )
    notes = []
    for extra in payload.get("additional_rate_limits") or []:
        window = ((extra.get("rate_limit") or {}).get("primary_window")) or {}
        if window:
            notes.append(f"{extra.get('limit_name') or 'reserve'} ({extra.get('normal_model_slug') or '-'}): "
                         f"{float(window.get('used_percent') or 0):.0f}% used")
    credits = (payload.get("rate_limit_reset_credits") or {}).get("available_count")
    if credits:
        notes.append(f"reset credits: {credits}")
    plan = str(payload.get("plan_type") or "")
    email = payload.get("email")
    return (f"{plan} · {email}" if email else plan), rows, notes


def codex_accounts(
    fetch=fetch_codex_usage,
    settings_path: Path = SETTINGS,
    cache_path: Path = CACHE,
    fresh: bool = False,
    now: datetime | None = None,
) -> list[Account]:
    return collect(
        codex_profiles(settings_path), codex_credentials, fetch,
        lambda payload, _credentials: codex_rows(payload),
        cache_path, fresh, now or datetime.now(timezone.utc),
    )


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
PLAN_HINT = "Percentages are per account; plan labels are advisory (Claude login may lag; Codex pro has no multiplier); free quota does not reserve running work."


def plan_label(account: Account) -> str:
    return account.plan or "unknown"


def relative_age(account: Account, now: datetime) -> str:
    seconds = (now - account.fetched_at).total_seconds() if account.fetched_at else 0
    return f"{int(seconds // 60)}m" if seconds >= 60 else f"{int(seconds)}s"


def used_text(row: Row) -> str:
    return "  ?" if math.isnan(row.used_percent) else f"{row.used_percent:3.0f}"


def pace_text(row: Row, now: datetime) -> str:
    pace = row.pace(now)
    if pace is None or math.isnan(row.used_percent):
        return "pace   -   room   -"
    expected, room = pace
    return f"pace {expected:3.0f}%  room {room:+4.0f}"


def render(accounts: list[Account], now: datetime) -> str:
    rows = [row for account in accounts for row in account.rows]
    width = max((len(row.window) for row in rows), default=7)
    out = [PACE_LEGEND, PLAN_HINT]
    for account in accounts:
        head = f"{account.label}  ({account.instance_id})"
        if account.stale:
            head += f"  (cached {relative_age(account, now)} ago)"
        out.append(f"{head}  {plan_label(account)}")
        if account.error:
            out.append(f"  {account.error}")
        for row in account.rows:
            out.append(
                f"  {row.window:<{width}} {used_text(row)}% used   "
                f"{pace_text(row, now)}   {reset_text(row.resets_at, now)}"
            )
        out.extend(f"  {note}" for note in account.notes)
    return "\n".join(out)


def render_markdown(accounts: list[Account], now: datetime) -> str:
    stamp = now.astimezone(TZ).strftime("%a %Y-%m-%d %H:%M %Z")
    out = [
        f"Rate limits at {stamp} — {PACE_LEGEND}",
        PLAN_HINT,
        "",
        "| profile | instance | plan | window | used | pace | room | resets |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for account in accounts:
        if account.error:
            out.append(
                f"| {account.label} | `{account.instance_id}` | {plan_label(account)} | — | | | | {account.error} |"
            )
        for row in account.rows:
            pace = row.pace(now)
            expected = f"{pace[0]:.0f}%" if pace else "-"
            room = f"{pace[1]:+.0f}" if pace else "-"
            out.append(
                f"| {account.label} | `{account.instance_id}` | {plan_label(account)} | {row.window} "
                f"| {used_text(row).strip()}% | {expected} | {room} "
                f"| {reset_text(row.resets_at, now).removeprefix('resets ')} |"
            )
        for note in account.notes:
            out.append(f"| {account.label} | `{account.instance_id}` | {plan_label(account)} | {note} | | | | |")
    return "\n".join(out)


def json_rows(accounts: list[Account], now: datetime) -> list[dict]:
    out = []
    for account in accounts:
        if account.error:  # consumers must tell "unknown" from "stale"
            out.append(
                {
                    "account": account.label,
                    "instance_id": account.instance_id,
                    "plan": plan_label(account),
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
                    "plan": plan_label(account),
                    "window": row.window,
                    "used_percent": None if math.isnan(row.used_percent) else row.used_percent,
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
        "--profile", help="substring of instance id / display name"
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
        accounts += codex_accounts(fresh=args.fresh)
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
