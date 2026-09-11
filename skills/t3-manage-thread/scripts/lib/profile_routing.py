# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Automatic Claude account routing; usage collection belongs to t3_limits."""
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from t3_limits import SETTINGS, claude_accounts, claude_profiles


def relevant(window, model):
    if window in {"session", "weekly"}:
        return True
    # Unknown scoped caps are conservatively applicable. Match a model family,
    # including versioned display names, without treating Opus as Fable.
    if window.endswith(" only"):
        families = {"fable", "opus", "sonnet", "haiku"}
        scoped = families.intersection(re.findall(r"[a-z]+", window[:-5].lower()))
        requested = families.intersection(re.findall(r"[a-z]+", model.lower()))
        return not scoped or not requested or bool(scoped & requested)
    return False


def choose(accounts, model, preferred, now):
    healthy, unknown = [], []
    for account in accounts:
        rows = [r for r in account.rows if relevant(r.window, model)]
        # A cached exhausted cap remains a reason to avoid an account until its
        # reset, even when a failed refresh makes the rest of the data uncertain.
        if any(r.used_percent >= 100 and
               (r.resets_at is None or r.resets_at > now) for r in rows):
            continue
        uncertain = account.error or account.stale or not {"session", "weekly"}.issubset(
            {r.window for r in rows})
        uncertain = uncertain or any(
            not math.isfinite(r.used_percent) or not 0 <= r.used_percent < 100 or
            (r.resets_at is not None and r.resets_at <= now) or
            (r.resets_at is None and r.used_percent != 0) for r in rows)
        if uncertain:
            unknown.append(account.instance_id)
            continue
        headroom = min(100 - r.used_percent for r in rows)
        rooms = [r.pace(now)[1] for r in rows if r.pace(now) is not None]
        # Bottleneck pace first, then absolute headroom. No-reset zero windows
        # are unused capacity, but carry no invented pacing signal.
        room = min(rooms) if rooms else 0
        healthy.append((room, headroom, account.instance_id))
    if healthy:
        healthy.sort(key=lambda item: (-item[0], -item[1], item[2] != preferred, item[2]))
        return healthy[0][2], "verified capacity (bottleneck pace, then headroom)"
    if unknown:
        return min(unknown, key=lambda i: (i != preferred, i)), "usage unknown/stale; capacity unverified"
    raise ValueError("all compatible profiles have exhausted subscription quotas; use --profile to override")


def route(model, preferred, settings_path=SETTINGS, collect=claude_accounts):
    # Other providers lack per-instance usage attribution; never apply one
    # CodexBar account's quota to arbitrary Codex instances.
    if not model.startswith("claude-"):
        return preferred, ""
    ids = [p[0] for p in claude_profiles(settings_path)]
    if len(ids) < 2:
        return (ids[0] if ids else preferred), "single compatible profile; usage not polled"
    now = datetime.now(timezone.utc)
    accounts = collect(settings_path=settings_path,
                       cache_path=settings_path.parent / "t3-limits-cache.json", now=now)
    return choose(accounts, model, preferred, now)


if __name__ == "__main__":
    try:
        selected, reason = route(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
    except ValueError as error:
        print(f"Profile routing: {error}", file=sys.stderr)
        raise SystemExit(2)
    if reason:
        print(f"Profile routing: {selected} — {reason}", file=sys.stderr)
    print(selected)
