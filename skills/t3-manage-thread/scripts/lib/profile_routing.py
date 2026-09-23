# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Automatic account routing for T3 spawns: one policy for Claude and Codex.

Candidates are the enabled T3 instances of the requested model's driver. Each
one is assessed from the shared usage cache (t3_limits): an exhausted relevant
window excludes it until that window resets; an unreachable/stale/malformed
reading makes it "unknown"; the rest are ranked by their worst window's pace
room (pace − used), then by minimum headroom. Ties prefer the inherited account
(or its cross-driver sibling), then the instance id. Verified capacity always
beats unknown. All candidates exhausted → refuse (an explicit --profile is the
override and never polls). Paid overage is never capacity.

    profile_routing.py MODEL PREFERRED_INSTANCE SETTINGS_JSON   # prints the chosen id;
                                                                 # the explanation goes to stderr
"""
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from t3_limits import SETTINGS, claude_accounts, codex_accounts, provider_profiles, relative
from profile_registry import registry, compatible

TIGHT_PERCENT = 90  # label only: near a cap, still eligible (ranking already prefers room)
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
    detail: str = ""       # why unknown/excluded, or "tight" label
    rows: list = field(default_factory=list)
    room: float = 0.0      # worst-window pace room (ok only)
    headroom: float = 0.0  # min(100 - used) (ok only)
    bottleneck: str = ""


def assess(account, model, now):
    rows = [r for r in account.rows if relevant(r.window, model)]
    candidate = Candidate(account.instance_id, account.label, "ok", rows=rows)
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
    paced = [(r.pace(now)[1], r.window) for r in rows if r.pace(now) is not None]
    # Bottleneck pace first, then absolute headroom. No-reset zero windows are
    # unused capacity, but carry no invented pacing signal.
    candidate.room, candidate.bottleneck = min(paced) if paced else (0.0, "")
    if any(r.used_percent >= TIGHT_PERCENT for r in rows):
        candidate.detail = "tight"
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
        best = min(ok, key=lambda c: (-c.room, -c.headroom, *tie(c)))
        why = f"best bottleneck room ({best.bottleneck} {best.room:+.0f})" if best.bottleneck else "unused capacity"
        if len(ok) > 1 and best.instance_id == preferred and any(
                (c.room, c.headroom) == (best.room, best.headroom) for c in ok if c is not best):
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
    lines = [f"Profile routing for {model} (usage cached ≤90 s; explicit --profile NAME bypasses this):"]
    width = max((len(c.instance_id) for c in candidates), default=8)
    for c in candidates:
        if c.status == "ok":
            windows = " · ".join(f"{r.window} {r.used_percent:.0f}%" +
                                 (f" (room {r.pace(now)[1]:+.0f})" if r.pace(now) else "")
                                 for r in c.rows)
            tag = "  [tight]" if c.detail == "tight" else ""
        else:
            windows = f"{c.status}: {c.detail}"
            tag = ""
        mark = "  ← selected" if c.instance_id == selected else ""
        lines.append(f"  {c.instance_id:<{width}}  {windows}{tag}{mark}")
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
