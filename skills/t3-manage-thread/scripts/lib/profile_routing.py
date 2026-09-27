# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Automatic account routing for T3 spawns: one policy for Claude and Codex.

Three rules (spawn-thread.md §Automatic profile routing):

1. Exclude an account with an exhausted relevant window until it resets; an
   unreachable/stale/malformed reading makes it "unknown" (ranked after every
   verified account). A verified account whose 5 h session is ≥ SESSION_TIGHT_PERCENT
   used ranks after the ones that still have session room.
2. Score = the tightest relevant weekly-class window's headroom per hour until
   its reset (`headroom% / max(hours, 1)`; an untouched window counts as
   100 % over its full length). Highest wins: quota that expires soonest is
   worth the most, growing continuously as the reset nears — the same thing a
   human reads off the reset times. A heuristic for urgency, not a throughput
   estimate: percentages are per account and plan sizes are invisible.
3. Ties prefer the inherited account (or its cross-driver sibling), then the
   instance id. Paid overage is never capacity.

    profile_routing.py MODEL PREFERRED_INSTANCE SETTINGS_JSON   # prints the chosen id;
                                                                 # the explanation goes to stderr
"""
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from t3_limits import PLAN_HINT, SETTINGS, WEEKLY_SECONDS, claude_accounts, codex_accounts, plan_label, provider_profiles, relative
from profile_registry import registry, compatible

SESSION_TIGHT_PERCENT = 90  # a 5 h window this full ranks the account after the others
WEEKLY_CLASS_SECONDS = 24 * 3600  # windows at least this long carry the urgency score
MIN_HOURS = 1.0  # smoothing floor: priority stops growing inside the last hour
FAMILIES = {"fable", "opus", "sonnet", "haiku"}
DRIVERS = {"claude": ("claudeAgent", claude_accounts), "codex": ("codex", codex_accounts)}


def model_family(model):
    if model.startswith("claude-"):
        return "claude"
    if model.startswith(("gpt-", "codex-")):
        return "codex"
    if model.startswith("gemini-"):
        return "antigravity"
    return "unknown"


def relevant(window, model):
    """Every top-level window counts; a `<Model> only` cap only for that family.
    Unknown scoped caps are conservatively applicable."""
    if not window.endswith(" only"):
        return True
    scoped = FAMILIES.intersection(re.findall(r"[a-z]+", window[:-5].lower()))
    requested = FAMILIES.intersection(re.findall(r"[a-z]+", model.lower()))
    return not scoped or not requested or bool(scoped & requested)


@dataclass
class Candidate:
    instance_id: str
    label: str
    status: str            # ok | unknown | excluded
    plan: str = "unknown"
    detail: str = ""       # why unknown/excluded, or "tight" label
    rows: list = field(default_factory=list)
    score: float = 0.0     # tightest weekly-class window's headroom per hour to reset (ok only)
    bottleneck: str = ""
    session_tight: bool = False


def hourly_headroom(row, now):
    """Headroom % per hour until the window resets, or None without a usable reading."""
    if math.isnan(row.used_percent):
        return None
    if row.resets_at is None:
        if row.used_percent == 0 and row.length_seconds:
            return 100.0 / (row.length_seconds / 3600)  # untouched: its full length is ahead
        return None
    hours = (row.resets_at - now).total_seconds() / 3600
    return (100 - row.used_percent) / max(hours, MIN_HOURS)


def assess(account, model, now):
    rows = [r for r in account.rows if relevant(r.window, model)]
    candidate = Candidate(account.instance_id, account.label, "ok", plan=plan_label(account), rows=rows)
    # A cached exhausted cap remains a reason to avoid an account until its
    # reset, even when a failed refresh makes the rest of the data uncertain.
    exhausted = [r for r in rows if r.used_percent >= 100 and (r.resets_at is None or r.resets_at > now)]
    if exhausted:
        r = exhausted[0]
        candidate.status, candidate.detail = "excluded", f"{r.window} exhausted" + (
            f", resets {relative((r.resets_at - now).total_seconds())}" if r.resets_at else "")
        return candidate
    if account.error:
        candidate.status, candidate.detail = "unknown", account.error
        return candidate
    if account.stale:
        candidate.status, candidate.detail = "unknown", f"stale reading ({relative_age(account, now)} old)"
        return candidate
    if not rows or any(
            not math.isfinite(r.used_percent) or not 0 <= r.used_percent < 100 or
            (r.resets_at is not None and r.resets_at <= now) or
            (r.resets_at is None and r.used_percent != 0) for r in rows):
        candidate.status, candidate.detail = "unknown", "no usable windows (missing % or past reset)"
        return candidate
    candidate.headroom = min(100 - r.used_percent for r in rows)
    weekly = [r for r in rows if (r.length_seconds or 0) >= WEEKLY_CLASS_SECONDS] or rows
    rated = [(hourly_headroom(r, now), r.window) for r in weekly]
    rated = [(rate, window) for rate, window in rated if rate is not None]
    if rated:
        candidate.score, candidate.bottleneck = min(rated)
    candidate.session_tight = any(
        (r.length_seconds or 0) < WEEKLY_CLASS_SECONDS and r.used_percent >= SESSION_TIGHT_PERCENT for r in rows)
    if candidate.session_tight:
        candidate.detail = "session tight"
    return candidate


def relative_age(account, now):
    seconds = (now - account.fetched_at).total_seconds() if account.fetched_at else 0
    return relative(seconds).removeprefix("in ") if seconds >= 60 else f"{int(seconds)}s"


def choose(accounts, model, preferred, now):
    """(instance_id, reason, candidates) — raises ValueError with the candidates
    attached when every account is exhausted."""
    candidates = [assess(a, model, now) for a in accounts]
    ok = [c for c in candidates if c.status == "ok"]
    unknown = [c for c in candidates if c.status == "unknown"]
    tie = lambda c: (c.instance_id != preferred, c.instance_id)
    if ok:
        best = min(ok, key=lambda c: (c.session_tight, -c.score, *tie(c)))
        why = (f"{best.bottleneck} {best.score:.1f} %/h — highest headroom per hour to reset"
               if best.bottleneck else "unused capacity")
        if best.session_tight:
            why += " (every verified account's session is tight)"
        if len(ok) > 1 and best.instance_id == preferred and any(
                (c.session_tight, c.score) == (best.session_tight, best.score) for c in ok if c is not best):
            why += ", tie → inherited account"
        return best.instance_id, why, candidates
    if unknown:
        best = min(unknown, key=tie)
        return best.instance_id, "usage unknown/stale for every candidate; capacity unverified", candidates
    error = ValueError("every compatible profile has an exhausted subscription window; "
                       "wait for a reset or pass --profile NAME to override")
    error.candidates = candidates
    raise error


def explain(model, candidates, now, selected=None, reason=""):
    lines = [f"Profile routing for {model} (usage cached ≤90 s; explicit --profile NAME bypasses this):", PLAN_HINT]
    width = max((len(c.instance_id) for c in candidates), default=8)
    for c in candidates:
        if c.status == "ok":
            windows = " · ".join(f"{r.window} {r.used_percent:.0f}%" +
                                 (f" (room {r.pace(now)[1]:+.0f})" if r.pace(now) else "")
                                 for r in c.rows)
            if c.bottleneck:
                windows += f"  [{c.bottleneck} {c.score:.1f} %/h]"
            tag = "  [session tight]" if c.session_tight else ""
        else:
            windows = f"{c.status}: {c.detail}"
            tag = ""
        mark = "  ← selected" if c.instance_id == selected else ""
        lines.append(f"  {c.instance_id:<{width}}  [{c.plan}] {windows}{tag}{mark}")
    if selected:
        lines.append(f"  → {selected}: {reason}")
    return "\n".join(lines)


def route(model, preferred, settings_path=SETTINGS, collect=None):
    """(instance_id, reason, explanation). Drivers without per-instance usage keep
    the inherited account (sibling on a driver switch)."""
    family = model_family(model)
    instances = registry(settings_path)
    if family not in DRIVERS:
        if family == "unknown":
            return preferred, "", ""
        return compatible(instances, preferred, family), "", ""
    driver, accounts_for = DRIVERS[family]
    ids = [p[0] for p in provider_profiles(settings_path, driver)]
    if not ids:
        return preferred, "", ""
    if preferred not in ids:
        # Driver switch (Claude thread → Codex): ties prefer the sibling account.
        try:
            preferred = compatible(instances, preferred, family)
        except ValueError:
            pass
    now = datetime.now(timezone.utc)
    accounts = (collect or accounts_for)(settings_path=settings_path,
                                         cache_path=settings_path.parent / "t3-limits-cache.json", now=now)
    try:
        selected, reason, candidates = choose(accounts, model, preferred, now)
    except ValueError as error:
        error.explanation = explain(model, error.candidates, now)
        raise
    return selected, reason, explain(model, candidates, now, selected, reason)


if __name__ == "__main__":
    try:
        selected, reason, explanation = route(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
    except ValueError as error:
        print(getattr(error, "explanation", ""), file=sys.stderr)
        print(f"Profile routing: {error}", file=sys.stderr)
        raise SystemExit(2)
    if explanation:
        print(explanation, file=sys.stderr)
    print(selected)
