#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Print the current subscription rate-limit windows for every Claude and Codex
profile T3 Code knows about.

Read-only and deterministic: T3's `settings.json` lists the enabled provider
instances; each Claude instance's OAuth token is read from macOS Keychain or Linux credentials and
each Codex instance's from `<home>/auth.json`; Claude's current plan comes from
`/api/oauth/profile`, and percentages come from Anthropic's
`/api/oauth/usage` and ChatGPT's `/backend-api/wham/usage`. Tokens are never printed
and never refreshed (a refresh would rotate them out from under the CLI itself); an
expired token just reports itself. A Claude profile with a 1-year setup-token and no
usable /login token is read through one tiny `claude -p` turn instead (see limits.md).

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
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Brussels")
SETTINGS = Path(os.environ.get("T3CODE_HOME", Path.home() / ".t3")) / "userdata" / "settings.json"
KEYCHAIN_BASE = "Claude Code-credentials"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
CODEX_HOME = Path.home() / ".codex"  # Codex CLI default; T3's empty homePath
HEADERS = {"anthropic-beta": "oauth-2025-04-20", "User-Agent": "t3-limits/0.1"}
TIMEOUT = 10
PROFILE_TIMEOUT = 3
CACHE = SETTINGS.parent / "t3-limits-cache.json"
MULTIPLIERS = SETTINGS.parent / "t3-plan-multipliers.json"  # private: {driver: {plan label: N}}
STATED_MULTIPLIER = re.compile(r"^max_(\d+)x\b")  # `max_20x`, `max_5x (pro)`; nothing else is trusted
FRESH_SECONDS = 90  # windows only move on the minute scale
STALE_SECONDS = 15 * 60  # older than this and "no data" beats a wrong number
MAX_RETRY_SECONDS = 5
SESSION_SECONDS = 5 * 3600
WEEKLY_SECONDS = 7 * 86400
EXPIRED_HINT = "token expired — run any turn in that profile to refresh"
AUTH_CODES = (401, 403)
PROBE_STORE = SETTINGS.parent / "t3-limits-probe.json"
PROBE_SECONDS = 5 * 60  # a probe is a real (tiny) Haiku turn; reuse its reading this long
PROBE_TIMEOUT = 30
# Unmodified CLI, no tools/MCP/hooks/skills/session file; `user` settings keep the
# profile's env token, which outranks any token in the caller's environment.
PROBE_ARGS = ["-p", "Respond with hello.", "--effort", "low", "--output-format", "stream-json",
              "--verbose", "--no-session-persistence", "--strict-mcp-config",
              "--disable-slash-commands", "--tools", "", "--setting-sources", "user",
              "--settings", '{"disableAllHooks": true}']
# Only a Fable turn reports the Fable weekly cap (as `seven_day_overage_included`, matched
# against the usage API on two accounts 2026-10-19) and costs ~100x a Haiku turn: refresh it
# at most this often, inside the same open-window gate.
FABLE_PROBE_SECONDS = 2 * 3600
PROBE_NOTE = "via setup-token probe"


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
    driver: str = ""  # T3 driver; scopes the private plan-multiplier map
    identity_hash: str = ""  # binds operator-confirmed tier metadata to this account


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
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:  # no macOS `security` binary (Linux/WSL)
        raise LookupError(f"no Keychain on this platform ({service})")
    if result.returncode != 0:
        raise LookupError(f"no Keychain item {service}")
    return json.loads(result.stdout).get("claudeAiOauth") or {}


def claude_home(home_path: str) -> Path:
    return Path(home_path or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()


def has_setup_token(home_path: str) -> bool:
    """A 1-year `claude setup-token` lives in the env (CLAUDE_CODE_OAUTH_TOKEN) or the
    profile's settings.json `env` block. It makes model calls, but the usage API answers
    403 to it, so limits still need the /login credential."""
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return True
    try:
        settings = json.loads((claude_home(home_path) / "settings.json").read_text())
    except (OSError, ValueError):
        return False
    return bool((settings.get("env") or {}).get("CLAUDE_CODE_OAUTH_TOKEN"))


def claude_credentials(home_path: str) -> dict:
    """The /login credential for one profile: macOS Keychain item, else the
    `.credentials.json` file Claude Code writes on Linux/WSL (and as macOS fallback)."""
    errors = []
    if sys.platform == "darwin":
        try:
            token = keychain_token(keychain_service(home_path or os.environ.get("CLAUDE_CONFIG_DIR", "")))
            if token.get("accessToken"):
                return token
        except (LookupError, OSError, ValueError, AttributeError):
            errors.append("Claude Keychain credential unavailable")
    path = claude_home(home_path) / ".credentials.json"
    try:
        token = json.loads(path.read_text()).get("claudeAiOauth") or {}
    except (OSError, ValueError, AttributeError):
        token = {}
    if isinstance(token, dict) and token.get("accessToken"):
        return token
    if has_setup_token(home_path):
        raise LookupError("setup-token only: usage needs a /login credential (`claude auth login` in that profile)")
    raise LookupError("; ".join(errors + [f"no Claude login in {path.parent}"]))


def fetch_claude_profile(token: str) -> dict:
    request = urllib.request.Request(
        PROFILE_URL, headers={"Authorization": f"Bearer {token}",
                              "Cache-Control": "no-cache", **HEADERS}
    )
    with urllib.request.urlopen(request, timeout=PROFILE_TIMEOUT) as response:
        return json.loads(response.read())


def fetch_claude_usage(token: str, fetch_profile=fetch_claude_profile) -> dict:
    request = urllib.request.Request(
        USAGE_URL, headers={"Authorization": f"Bearer {token}", **HEADERS}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict):
        return payload  # collect reports malformed usage independently
    # Discovery is optional: never retry valid usage or demote it for a profile error.
    payload["_t3_claude_plan"] = None
    try:
        profile = fetch_profile(token)
        tier = profile.get("organization", {}).get("rate_limit_tier")
        if isinstance(tier, str) and tier:
            payload["_t3_claude_plan"] = tier.removeprefix("default_claude_")
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return payload  # cache only the tier, never the profile's identity/billing data


def claude_usage_credentials(home_path: str) -> dict:
    """The /login token when it is still valid, else (setup-token profiles) a marker for
    the CLI probe; plan labels of an expired login stay usable as fallback metadata."""
    setup_token = has_setup_token(home_path)
    try:
        credentials = dict(claude_credentials(home_path))
    except LookupError:
        if not setup_token:
            raise
        credentials = {}
    expires = credentials.get("expiresAt")
    expired = isinstance(expires, (int, float)) and expires / 1000 < time.time() + 60
    if expired and not setup_token:
        credentials["source"] = "expired"  # never sent; fetch refuses after the cache is loaded
    elif expired or not credentials.get("accessToken"):
        credentials["source"] = "cli"
    credentials["home"], credentials["setup_token"] = home_path, setup_token
    config = (claude_home(home_path) / ".claude.json" if home_path or os.environ.get("CLAUDE_CONFIG_DIR")
              else Path.home() / ".claude.json")
    try:
        account = json.loads(config.read_text()).get("oauthAccount") or {}
        if not isinstance(account.get("accountUuid"), str) or not account["accountUuid"]:
            raise ValueError("no stable account identity")
        identity = f"{account['accountUuid']}|{account.get('organizationUuid', '')}"
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # rotate only when no stable account id exists
        identity = (credentials.get("accessToken") if credentials.get("source") != "cli" else None) \
            or f"home:{claude_home(home_path)}"
    credentials["identity"] = hashlib.sha256(identity.encode()).hexdigest()
    return credentials


def last_activity(home_path: str) -> float:
    """Newest transcript write in the profile (epoch s): only real turns open a window."""
    newest = 0.0
    try:
        for project in os.scandir(claude_home(home_path) / "projects"):
            if project.is_dir():
                for entry in os.scandir(project.path):
                    if entry.name.endswith(".jsonl"):
                        newest = max(newest, entry.stat().st_mtime)
    except OSError:
        pass
    return newest


def run_probe(home_path: str, model: str = "haiku") -> dict:
    """One tiny turn through the unmodified `claude` CLI on the profile's own token; its
    stream-json `rate_limit_event` carries the account's windows (fractions, epoch s).
    Anthropic allows subscription OAuth only in Claude Code itself, so no raw API call."""
    binary = shutil.which("claude")
    if not binary:
        raise LookupError("usage probe: claude CLI not on PATH")
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    if home_path:
        env["CLAUDE_CONFIG_DIR"] = str(Path(home_path).expanduser())
    with tempfile.TemporaryDirectory() as cwd:
        try:
            result = subprocess.run([binary, *PROBE_ARGS, "--model", model], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=PROBE_TIMEOUT, check=False)
        except subprocess.TimeoutExpired:
            raise LookupError(f"usage probe timed out ({PROBE_TIMEOUT}s)")
    windows, failure = {}, ""
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "rate_limit_event":
            windows = (event.get("rate_limit_info") or {}).get("unifiedWindows") or windows
        elif event.get("type") == "result" and event.get("is_error"):
            failure = str(event.get("result") or event.get("subtype") or "error")[:120]
    payload = {}
    keys = {"five_hour": "five_hour", "seven_day": "seven_day"}
    if model == "fable":
        keys["seven_day_overage_included"] = "seven_day_fable"
    for key, name in keys.items():
        window = windows.get(key)
        if isinstance(window, dict) and isinstance(window.get("utilization"), (int, float)):
            reset = window.get("resetsAt")
            payload[name] = {
                "utilization": round(float(window["utilization"]) * 100, 1),
                "resets_at": datetime.fromtimestamp(reset, timezone.utc).isoformat()
                if isinstance(reset, (int, float)) else None,
            }
    if not payload:
        raise LookupError(f"usage probe: {failure or 'no rate_limit_event'} (exit {result.returncode})")
    return payload


def idle_payload(payload: dict, now: datetime) -> dict:
    """No turn since the last session window closed: the session is untouched and the
    weekly readings stand until their own reset."""
    idle = {"utilization": 0.0, "resets_at": None}
    out = {"five_hour": idle}
    for key in ("seven_day", "seven_day_fable"):
        weekly = payload.get(key) or {}
        reset = parse_time(weekly.get("resets_at"))
        if weekly or key == "seven_day":
            out[key] = weekly if reset and reset > now else idle
    return out


def window_open(payload: dict, closed_at: float, activity: float, now: datetime) -> bool:
    """Would a probe land inside an open session window (so it starts none)? Only when that is
    certain: the last reading's window still runs, or a local turn came after a point known to
    be window-free (`closed_at`: the reading's reset or an idle check) less than 5 h ago — the
    window that turn opened or joined cannot have ended yet."""
    reset = parse_time((payload.get("five_hour") or {}).get("resets_at"))
    if reset is not None and reset > now + timedelta(minutes=1):
        return True
    closed_at = max(closed_at, reset.timestamp() if reset else 0.0)
    return activity > closed_at > now.timestamp() - SESSION_SECONDS


def probe_claude_usage(home_path: str, identity: str = "", fresh: bool = False, now: datetime | None = None,
                       store_path: Path | None = None, run=None) -> dict:
    """Setup-token usage without starting windows: probe only inside an open session window
    (window_open; `fresh` overrides), else derive the idle reading. Readings are stored per
    config dir and account identity (never tokens)."""
    now = now or datetime.now(timezone.utc)
    store_path = store_path or PROBE_STORE
    store, key = read_cache(store_path), str(claude_home(home_path))
    entry = store.get(key) or {}
    entry = entry if entry.get("identity") == identity else {}
    payload, observed = entry.get("payload") or {}, float(entry.get("observed_at") or 0)
    # The probe can't see the plan; the last live tier from the usage API beats the saved login label.
    plan = {"_t3_last_live_plan": entry["live_plan"], "_t3_last_live_plan_at": entry.get("live_plan_at")} \
        if entry.get("live_plan") else {}
    if payload and not fresh and now.timestamp() - observed < PROBE_SECONDS:
        return dict(payload, **plan, _t3_observed_at=observed, _t3_source="cli")
    activity = last_activity(home_path)
    if fresh or window_open(payload, float(entry.get("closed_at") or 0), activity, now):
        fable = now.timestamp() - float(entry.get("fable_at") or 0) >= FABLE_PROBE_SECONDS
        if fable:  # counts even if it fails or reports no Fable cap: never a Fable turn per poll
            entry = store[key] = dict(entry, identity=identity, fable_at=now.timestamp())
            write_cache(store, store_path)
        payload = (run or run_probe)(home_path, "fable" if fable else "haiku")
        if not fable and (entry.get("payload") or {}).get("seven_day_fable"):  # keep the last one
            payload = dict(payload, seven_day_fable=entry["payload"]["seven_day_fable"])
        store[key] = dict(entry, payload=payload, observed_at=now.timestamp(), identity=identity)
        write_cache(store, store_path)
        return dict(payload, **plan, _t3_observed_at=now.timestamp(), _t3_source="cli")
    reset = parse_time((payload.get("five_hour") or {}).get("resets_at"))
    if activity <= max(reset.timestamp() if reset else 0.0, now.timestamp() - SESSION_SECONDS):
        # No local turn since the reset, or none for 5 h: no window open now. Remember that
        # point, so the next turn is known to sit in a fresh window.
        store[key] = dict(entry, identity=identity, closed_at=now.timestamp())
        write_cache(store, store_path)
    elif payload:  # turns since the reset that may sit in a window that has since closed
        raise LookupError("usage unknown: turns since the last reading, window state uncertain "
                          "(clears ≤ 5 h after the last turn; `t3-limits --fresh` probes now)")
    if not payload:
        raise LookupError("no usage reading yet: shows after the next turn in this profile "
                          "(`t3-limits --fresh` probes now and may start a 5 h window)")
    return dict(idle_payload(payload, now), **plan, _t3_observed_at=observed, _t3_source="cli")


def remember_live_plan(home_path: str, identity: str, plan: str, now: datetime, store_path: Path) -> None:
    """Keep the usage API's live tier for when this setup-token profile falls back to the probe."""
    store, key = read_cache(store_path), str(claude_home(home_path))
    entry = store.get(key) or {}
    entry = entry if entry.get("identity") == identity else {"identity": identity}
    if entry.get("live_plan") != plan or now.timestamp() - float(entry.get("live_plan_at") or 0) > 86400:
        store[key] = dict(entry, live_plan=plan, live_plan_at=now.timestamp())
        write_cache(store, store_path)


def fetch_claude(credentials: dict, fetch, fresh: bool = False, now: datetime | None = None,
                 store_path: Path | None = None) -> dict:
    """Usage API with the /login token; a setup-token profile falls back to the CLI probe
    when that token is gone or the API refuses it (a revoked token can even answer 429)."""
    home, identity = credentials.get("home", ""), credentials.get("identity", "")
    if credentials.get("source") == "expired":
        raise LookupError(EXPIRED_HINT)
    if credentials.get("source") == "cli":
        return probe_claude_usage(home, identity, fresh, now, store_path)
    try:
        payload = fetch(credentials["accessToken"])
    except (urllib.error.URLError, OSError):
        if not credentials.get("setup_token"):
            raise
        debug("usage API failed — falling back to the setup-token probe")
        return probe_claude_usage(home, identity, fresh, now, store_path)
    live = payload.get("_t3_claude_plan") if isinstance(payload, dict) else None
    if credentials.get("setup_token") and isinstance(live, str) and live:
        remember_live_plan(home, identity, live, now or datetime.now(timezone.utc), store_path or PROBE_STORE)
    return payload


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
        if error.code in AUTH_CODES:
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
    driver: str = "",
) -> list[Account]:
    """One Account per T3 instance: local credential → usage payload → rows, with
    the shared fresh/stale cache keyed by instance id (never tokens). A cache entry
    is only valid for the identity (home path + account id) that produced it."""
    cache = read_cache(cache_path)
    accounts, dirty = [], False
    for instance_id, label, home in profiles:
        account = Account(label=label, instance_id=instance_id, driver=driver)
        auth_failed = False
        credentials: dict = {}
        payload = None
        entry: dict = {}
        age = None
        try:
            credentials = credentials_for(home)
            account.identity_hash = hashlib.sha256(str(credentials["identity"]).encode()).hexdigest() if credentials.get("identity") else ""
            identity = f"{home}|{credentials.get('identity', '')}"
            entry = cache.get(instance_id) or {}
            entry = entry if entry.get("payload") and entry.get("identity") == identity else {}
            age = now.timestamp() - float(entry.get("fetched_at") or 0) if entry else None
            if entry and not fresh and age < FRESH_SECONDS:
                debug(f"{instance_id}: cache hit ({age:.0f}s old)")
                payload = entry["payload"]
                account.fetched_at = now - timedelta(seconds=age)
            else:
                payload = fetch_with_retry(credentials, fetch)
                account.fetched_at = now
                cache[instance_id] = {"payload": payload, "fetched_at": now.timestamp(),
                                      "identity": identity}
                dirty = True
        except urllib.error.HTTPError as error:
            auth_failed = error.code in AUTH_CODES
            account.error = (f"login rejected (HTTP {error.code}): run a turn in that profile, re-login if it fails"
                             if auth_failed else f"HTTP {error.code}")
        except (LookupError, KeyError, OSError, ValueError) as error:
            account.error = str(error) or error.__class__.__name__
            auth_failed = account.error == EXPIRED_HINT
        if account.error and entry:
            account.fetched_at = now - timedelta(seconds=age)
            if not auth_failed and age < STALE_SECONDS:
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
            observed = payload.get("_t3_observed_at") if isinstance(payload, dict) else None
            if isinstance(observed, (int, float)) and not account.stale:
                account.fetched_at = datetime.fromtimestamp(observed, timezone.utc)
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


def claude_reading(payload: dict, credentials: dict) -> tuple:
    rows, notes = claude_rows(payload)
    if payload.get("_t3_source") == "cli":
        notes.append(PROBE_NOTE)
    login = claude_plan(credentials)
    live = payload.get("_t3_claude_plan")
    if isinstance(live, str) and live:
        if login and login != live:
            notes.append(f"live plan {live}; saved login label {login}")
        return live, rows, notes
    last = payload.get("_t3_last_live_plan")
    if isinstance(last, str) and last:
        when = payload.get("_t3_last_live_plan_at")
        seen = datetime.fromtimestamp(when, TZ).strftime("%b %-d") if isinstance(when, (int, float)) else "?"
        if login and login != last:
            notes.append(f"saved login label {login}")
        return f"{last} (live {seen})", rows, notes
    if login:
        login = login[:-1] + ", login fallback)" if login.endswith(")") else login + " (login fallback)"
    return login, rows, notes


@contextmanager
def default_home_env(profiles: list[tuple[str, str, str]]):
    """Inside a thread of a homePath instance, T3 sets CLAUDE_CONFIG_DIR to that home;
    the default (empty homePath) instance would then read the caller's account twice."""
    current = os.environ.get("CLAUDE_CONFIG_DIR")
    homes = {Path(home).expanduser() for _, _, home in profiles if home}
    if not current or Path(current).expanduser() not in homes:
        yield
        return
    del os.environ["CLAUDE_CONFIG_DIR"]
    try:
        yield
    finally:
        os.environ["CLAUDE_CONFIG_DIR"] = current


def claude_accounts(
    fetch=fetch_claude_usage,
    settings_path: Path = SETTINGS,
    cache_path: Path = CACHE,
    fresh: bool = False,
    now: datetime | None = None,
) -> list[Account]:
    profiles = claude_profiles(settings_path)
    with default_home_env(profiles):
        return collect(
            profiles,
            claude_usage_credentials,
            # the probe gate reads the clock itself: earlier profiles may have taken a minute
            lambda credentials: fetch_claude(credentials, fetch, fresh, now, cache_path.with_name(PROBE_STORE.name)),
            claude_reading,
            cache_path, fresh, now or datetime.now(timezone.utc), "claudeAgent",
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
        cache_path, fresh, now or datetime.now(timezone.utc), "codex",
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
PLAN_HINT = ("Percentages are per account; routing multiplies headroom by plan tier: label (max_20x → 20x), "
             "else private t3-plan-multipliers.json (`5x map`), else `1x?` (unverified, ranked smallest); "
             "free quota does not reserve running work.")


def plan_label(account: Account) -> str:
    return account.plan or "unknown"


def plan_multiplier(account: Account, path: Path | None = None) -> tuple[int, str]:
    """(multiplier, source): `label` when the live label states it, `map` from the
    user's private {driver: {bare plan: N}} file for labels that state none (Codex
    `pro`/`prolite`), else (1, "unknown"). A tier is advertised size, not capacity left."""
    plan = plan_label(account)
    stated = STATED_MULTIPLIER.search(plan)
    if stated:
        return int(stated.group(1)), "label"
    try:
        config = json.loads((path or MULTIPLIERS).read_text())
        mapped = config.get(account.driver, {}).get(re.split(r" · | \(", plan)[0])
        # Only absent plan metadata may use an identity-bound operator assertion.
        # A new login/account or any reported plan invalidates this fallback.
        if not account.plan and account.identity_hash:
            entry = config.get("instances", {}).get(account.instance_id, {})
            if entry.get("identity_hash") == account.identity_hash:
                mapped = entry.get("multiplier")
    except (OSError, ValueError, AttributeError):
        mapped = None
    if isinstance(mapped, int) and not isinstance(mapped, bool) and mapped >= 1:
        return mapped, "map"
    return 1, "unknown"


def tier_text(multiplier: int, source: str) -> str:
    return {"label": f"{multiplier}x", "map": f"{multiplier}x map"}.get(source, "1x?")


def plan_tier(account: Account) -> str:
    """Label plus tier, e.g. `prolite · a@b.c · 5x map`."""
    return f"{plan_label(account)} · {tier_text(*plan_multiplier(account))}"


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
        out.append(f"{head}  {plan_tier(account)}")
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
        plan = plan_tier(account)
        if account.error:
            out.append(
                f"| {account.label} | `{account.instance_id}` | {plan} | — | | | | {account.error} |"
            )
        for row in account.rows:
            pace = row.pace(now)
            expected = f"{pace[0]:.0f}%" if pace else "-"
            room = f"{pace[1]:+.0f}" if pace else "-"
            out.append(
                f"| {account.label} | `{account.instance_id}` | {plan} | {row.window} "
                f"| {used_text(row).strip()}% | {expected} | {room} "
                f"| {reset_text(row.resets_at, now).removeprefix('resets ')} |"
            )
        for note in account.notes:
            out.append(f"| {account.label} | `{account.instance_id}` | {plan} | {note} | | | | |")
    return "\n".join(out)


def json_rows(accounts: list[Account], now: datetime) -> list[dict]:
    out = []
    for account in accounts:
        multiplier, source = plan_multiplier(account)
        tier = {"multiplier": multiplier, "multiplier_source": source}
        if account.error:  # consumers must tell "unknown" from "stale"
            out.append(
                {
                    "account": account.label,
                    "instance_id": account.instance_id,
                    "plan": plan_label(account),
                    **({"identity_hash": account.identity_hash} if account.identity_hash else {}),
                    **tier,
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
                    **({"identity_hash": account.identity_hash} if account.identity_hash else {}),
                    **tier,
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
                    **({"stale": True} if account.stale else {}),
                    **(
                        {"fetched_at": account.fetched_at.isoformat().replace("+00:00", "Z")
                         if account.fetched_at else None}
                        if account.fetched_at or account.stale
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
