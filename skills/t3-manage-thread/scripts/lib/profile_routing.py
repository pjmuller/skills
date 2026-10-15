# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Automatic account routing for T3 spawns: one policy for Claude and Codex.

Three rules (spawn-thread.md §Automatic profile routing):

1. Exclude an account with an exhausted relevant window until it resets; an
   unreachable/stale/malformed reading makes it "unknown" (ranked after every
   verified account). A verified account whose 5 h session is tight (rule 2)
   ranks after the ones that still have session room.
2. Score = the tightest relevant weekly-class window's headroom per hour until
   its reset (`headroom% / max(hours, 1)`; an untouched window counts as
   100 % over its full length), times the plan multiplier (t3_limits.plan_multiplier:
   stated by the label, `max_20x` → 20; else the user's private map, Codex
   `prolite` → 5; else 1, never optimistic about an unknown tier). Highest
   wins: quota that expires soonest is worth the most, growing continuously as
   the reset nears — the same thing a human reads off the reset times. A
   heuristic for urgency, not a throughput estimate.
   Session tightness is measured in the same plan units: tight when
   multiplier × session headroom % is at most SESSION_TIGHT_SHARE of the largest
   verified plan's full session (20x only: the old ≥ 90 % rule; 5x beside 20x:
   ≥ 60 % used; 1x beside 20x: always tight, i.e. overflow only).
3. Ties prefer the inherited account (or its cross-driver sibling), then the
   instance id. Paid overage is never capacity.

A private, expiring override (t3-routing-override.json beside settings.json)
may put an ordered account preference on top of rule 2 for a while, e.g. to
concentrate work on one account before applying a banked reset. Rules 1, the
session guard and every explicit choice still win over it.

    profile_routing.py MODEL PREFERRED_INSTANCE SETTINGS_JSON [ALLOWED_IDS_CSV]
        prints the chosen id (only among ALLOWED when given); explanation on stderr
    profile_routing.py --check MODEL INSTANCE SETTINGS_JSON
        explicit single account: exit 0 when usable or unverified (warning on
        stderr), exit 2 printing the best alternative id when it is excluded
"""
import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from t3_limits import (PLAN_HINT, SETTINGS, claude_accounts, codex_accounts, plan_label, plan_multiplier,
                       provider_profiles, relative, tier_text)
from profile_registry import registry, compatible

SESSION_TIGHT_SHARE = 0.10  # session room below this share of the largest verified plan's session demotes
WEEKLY_CLASS_SECONDS = 24 * 3600  # windows at least this long carry the urgency score
MIN_HOURS = 1.0  # smoothing floor: priority stops growing inside the last hour
FAMILIES = {"fable", "opus", "sonnet", "haiku"}
DRIVERS = {"claude": ("claudeAgent", claude_accounts), "codex": ("codex", codex_accounts)}
OVERRIDE = SETTINGS.parent / "t3-routing-override.json"  # private and temporary, see spawn-thread.md


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
    weight: int = 1        # plan multiplier (label, private map, else 1)
    tier: str = "1x?"       # weight and its source, for the explanation
    rate: float = 0.0      # tightest weekly-class window's headroom % per hour to reset (ok only)
    score: float = 0.0     # rate × weight: plan units per hour
    bottleneck: str = ""
    weekly_used: float = 0.0  # highest relevant weekly-class used % (override cap)
    session_room: float | None = None  # weight × tightest session headroom %, None without a session window
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
    weight, source = plan_multiplier(account)
    candidate = Candidate(account.instance_id, account.label, "ok", plan=plan_label(account), rows=rows,
                          weight=weight, tier=tier_text(weight, source))
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
        candidate.rate, candidate.bottleneck = min(rated)
        candidate.score = candidate.rate * candidate.weight
    candidate.weekly_used = max(r.used_percent for r in weekly)
    sessions = [100 - r.used_percent for r in rows if (r.length_seconds or 0) < WEEKLY_CLASS_SECONDS]
    if sessions:
        candidate.session_room = candidate.weight * min(sessions)
    return candidate


def mark_session_tight(ok):
    """Relative to the verified candidates only: an excluded or stale big plan
    must not demote the usable small ones."""
    largest = max((c.weight for c in ok), default=1)
    for c in ok:
        c.session_tight = c.session_room is not None and c.session_room <= SESSION_TIGHT_SHARE * 100 * largest
        if c.session_tight:
            c.detail = f"session tight: {c.session_room:.0f} ≤ {SESSION_TIGHT_SHARE * 100 * largest:.0f} plan-% units"


def relative_age(account, now):
    seconds = (now - account.fetched_at).total_seconds() if account.fetched_at else 0
    return relative(seconds).removeprefix("in ") if seconds >= 60 else f"{int(seconds)}s"


def load_override(now, path=None):
    """{"until", "weekly_cap", "prefer": [(id, from)]} while the private override
    file is valid and unexpired; None when absent; {"note"} when expired/invalid."""
    path = path or OVERRIDE
    try:
        data = json.loads(path.read_text())
        until = datetime.fromisoformat(data["until"])
        prefer = [(e, None) if isinstance(e, str) else
                  (e["id"], datetime.fromisoformat(e["from"]) if e.get("from") else None)
                  for e in data["prefer"]]
        cap = float(data.get("weekly_cap", 90))
        if until.tzinfo is None or any(start and start.tzinfo is None for _, start in prefer):
            raise ValueError("timestamps need a UTC offset")
        if not isinstance(data["prefer"], list) or not all(isinstance(id, str) and id for id, _ in prefer):
            raise ValueError("prefer must list instance ids")
        if not 0 < cap <= 100:
            raise ValueError("weekly_cap must be in (0, 100]")
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return {"note": f"override {path.name} ignored: invalid ({error.__class__.__name__}: {error})"}
    if now >= until:
        return {"note": f"override expired {until:%a %d %b %H:%M %z}; ordinary routing"}
    return {"until": until, "weekly_cap": cap, "prefer": prefer}


def override_pick(candidates, override, now):
    """(candidate, notes): the first `prefer` account that is verified, not
    session-tight, past its `from` and under the weekly cap; notes say why each
    earlier entry was skipped. Entries of other drivers stay silent."""
    by_id = {c.instance_id: c for c in candidates}
    cap, notes = override["weekly_cap"], []
    for id, start in override["prefer"]:
        c = by_id.get(id)
        if c is None:
            continue
        if c.status != "ok":
            why = f"{c.status} ({c.detail})"
        elif start and now < start:
            why = f"waits until {start:%a %d %b %H:%M}"
        elif c.session_tight:
            why = "session tight"
        elif c.weekly_used >= cap:
            why = f"weekly {c.weekly_used:.0f}% ≥ cap {cap:.0f}%"
        else:
            return c, notes
        notes.append(f"{id} {why}")
    return None, notes


def choose(accounts, model, preferred, now, override=None):
    """(instance_id, reason, candidates) — raises ValueError with the candidates
    attached when every account is exhausted."""
    candidates = [assess(a, model, now) for a in accounts]
    ok = [c for c in candidates if c.status == "ok"]
    unknown = [c for c in candidates if c.status == "unknown"]
    tie = lambda c: (c.instance_id != preferred, c.instance_id)
    note = (override or {}).get("note", "")
    if ok:
        mark_session_tight(ok)
        if override and not note:
            pick, skipped = override_pick(candidates, override, now)
            head = f"override until {override['until']:%a %d %b %H:%M}"
            if pick:
                why = (f"{head}: first preferred account under weekly cap {override['weekly_cap']:.0f}% "
                       f"(weekly {pick.weekly_used:.0f}%)")
                return pick.instance_id, why + "".join(f"; skipped {s}" for s in skipped), candidates
            if skipped:
                note = f"{head}: no preferred account eligible ({'; '.join(skipped)})"
        best = min(ok, key=lambda c: (c.session_tight, -c.score, *tie(c)))
        why = (f"{best.bottleneck} {best.rate:.1f} %/h × {best.weight}x = {best.score:.1f} — "
               "highest plan-weighted headroom per hour to reset"
               if best.bottleneck else "unused capacity")
        if best.session_tight:
            why += " (every verified account's session is tight)"
        if len(ok) > 1 and best.instance_id == preferred and any(
                (c.session_tight, c.score) == (best.session_tight, best.score) for c in ok if c is not best):
            why += ", tie → inherited account"
        return best.instance_id, why + (f" [{note}]" if note else ""), candidates
    if unknown:
        best = min(unknown, key=tie)
        return best.instance_id, "usage unknown/stale for every candidate; capacity unverified", candidates
    error = ValueError("every compatible profile has an exhausted subscription window; "
                       "wait for a reset or pass --profile NAME --force-profile to override")
    error.candidates = candidates
    raise error


def explain(model, candidates, now, selected=None, reason=""):
    lines = [f"Profile routing for {model} (usage cached ≤90 s; --force-profile bypasses this):", PLAN_HINT]
    width = max((len(c.instance_id) for c in candidates), default=8)
    for c in candidates:
        if c.status == "ok":
            windows = " · ".join(f"{r.window} {r.used_percent:.0f}%" +
                                 (f" (room {r.pace(now)[1]:+.0f})" if r.pace(now) else "")
                                 for r in c.rows)
            if c.bottleneck:
                windows += f"  [{c.bottleneck} {c.rate:.1f} %/h × {c.weight}x = {c.score:.1f}]"
            tag = f"  [{c.detail}]" if c.session_tight else ""
        else:
            windows = f"{c.status}: {c.detail}"
            tag = ""
        mark = "  ← selected" if c.instance_id == selected else ""
        lines.append(f"  {c.instance_id:<{width}}  [{c.plan} · {c.tier}] {windows}{tag}{mark}")
    if selected:
        lines.append(f"  → {selected}: {reason}")
    return "\n".join(lines)


def route(model, preferred, settings_path=SETTINGS, collect=None, allowed=None, override_path=None):
    """(instance_id, reason, explanation). Drivers without per-instance usage keep
    the inherited account (sibling on a driver switch). `allowed` (ids) narrows
    the candidates to the accounts the user named."""
    family = model_family(model)
    instances = registry(settings_path)
    if allowed:
        driver = DRIVERS.get(family, (None,))[0]
        wrong = [id for id in allowed if instances.get(id, {}).get("driver") != driver]
        if driver is None or wrong:
            raise ValueError(f"--profile {','.join(allowed)}: every account must be a {family} profile "
                             f"for {model}" + (f"; not: {', '.join(wrong)}" if wrong else ""))
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
    if allowed:
        accounts = [a for a in accounts if a.instance_id in allowed]
    override = load_override(now, override_path or settings_path.parent / OVERRIDE.name)
    try:
        selected, reason, candidates = choose(accounts, model, preferred, now, override)
    except ValueError as error:
        error.explanation = explain(model, error.candidates, now)
        raise
    return selected, reason, explain(model, candidates, now, selected, reason)


def check(model, instance_id, settings_path=SETTINGS, collect=None):
    """Capacity check for one explicit account. Returns a stderr note (empty
    when not applicable); raises ValueError with .alternative/.explanation when
    a relevant window is exhausted."""
    family = model_family(model)
    if family not in DRIVERS or registry(settings_path).get(instance_id, {}).get("driver") != DRIVERS[family][0]:
        return ""  # other drivers have no per-account usage; a family mismatch fails later
    driver, accounts_for = DRIVERS[family]
    now = datetime.now(timezone.utc)
    accounts = (collect or accounts_for)(settings_path=settings_path,
                                         cache_path=settings_path.parent / "t3-limits-cache.json", now=now)
    named = next((a for a in accounts if a.instance_id == instance_id), None)
    if named is None:
        return f"warning: no usage reading for {instance_id}; capacity unverified"
    candidate = assess(named, model, now)
    if candidate.status == "unknown":
        return f"warning: {instance_id} usage unknown ({candidate.detail}); capacity unverified"
    if candidate.status == "ok":
        return explain(model, [candidate], now, instance_id, "explicit --profile, capacity ok")
    error = ValueError(f"{instance_id} cannot run {model}: {candidate.detail}")
    error.alternative, reason = None, ""
    others = [a for a in accounts if a.instance_id != instance_id]
    try:
        error.alternative, reason, candidates = choose(others, model, instance_id, now)
    except ValueError as exhausted:
        candidates = exhausted.candidates
    error.explanation = explain(model, [candidate, *candidates], now, error.alternative, reason)
    raise error


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        try:
            note = check(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
        except ValueError as error:
            print(error.explanation, file=sys.stderr)
            print(f"Profile check: {error}", file=sys.stderr)
            print(error.alternative or "")
            raise SystemExit(2)
        if note:
            print(note, file=sys.stderr)
        raise SystemExit(0)
    try:
        allowed = [id for id in (sys.argv[4] if len(sys.argv) > 4 else "").split(",") if id]
        selected, reason, explanation = route(sys.argv[1], sys.argv[2], Path(sys.argv[3]), allowed=allowed)
    except ValueError as error:
        print(getattr(error, "explanation", ""), file=sys.stderr)
        print(f"Profile routing: {error}", file=sys.stderr)
        raise SystemExit(2)
    if explanation:
        print(explanation, file=sys.stderr)
    print(selected)
