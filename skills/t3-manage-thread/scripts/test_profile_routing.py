"""Routing contracts: no network, Keychain, or live thread mutations."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "lib"))
from profile_routing import choose, explain, relevant, route
from t3_limits import Account, Row, claude_profiles, claude_rows

NOW = datetime.now(timezone.utc)


def account(id, used=20, scoped=None, **kwargs):
    rows = [Row("session", used, NOW + timedelta(hours=2), 18000),
            Row("weekly", used, NOW + timedelta(days=2), 604800)]
    if scoped:
        rows.append(Row(scoped[0] + " only", scoped[1], NOW + timedelta(days=2), 604800))
    return Account(id, id, rows=rows, **kwargs)


def test_model_only_exhaustion_and_unrelated_cap():
    rows = [account("a", scoped=("Fable", 100)), account("b", 78)]
    assert choose(rows, "claude-fable-5-1", "a", NOW)[0] == "b"
    assert choose(rows, "claude-opus-5", "a", NOW)[0] == "a"
    with pytest.raises(ValueError, match="exhausted"):
        choose(rows[:1], "claude-fable-5-1", "a", NOW)


def test_unknown_stale_and_expired_windows():
    stale = account("a", 1, stale=True)
    healthy = account("b", 90)
    assert choose([stale, healthy], "claude-fable-5", "a", NOW)[0] == "b"
    unknown = Account("c", "c", error="unreachable")
    assert choose([stale, unknown], "claude-fable-5", "c", NOW)[0] == "c"
    stale.rows[0].used_percent = 100
    assert choose([stale, unknown], "claude-fable-5", "a", NOW)[0] == "c"
    stale.rows[0].resets_at = NOW - timedelta(seconds=1)
    assert choose([stale, unknown], "claude-fable-5", "a", NOW)[0] == "a"


def test_score_headroom_per_hour_and_stable_ties():
    a, b = account("a", plan="max_20x"), account("b", plan="pro")
    assert choose([b, a], "claude-fable-5", "a", NOW)[0] == "a"
    assert choose([b, a], "claude-fable-5", "b", NOW)[0] == "b"  # plan labels do not break a tie
    assert choose([b, a], "claude-fable-5", "missing", NOW)[0] == "a"
    selected, reason, candidates = choose([b, a], "claude-fable-5", "a", NOW)
    explanation = explain("claude-fable-5", candidates, NOW, selected, reason)
    assert "a  [max_20x]" in explanation and "b  [pro]" in explanation and "%/h" in explanation
    assert "Percentages are per account" in explanation and "tie → inherited" in reason
    b.rows[1].resets_at = NOW + timedelta(days=6)  # same headroom, later reset → less urgent
    assert choose([b, a], "claude-fable-5", "b", NOW)[0] == "a"


def test_soonest_weekly_reset_wins_and_grows_continuously():
    """PJ 2026-09-27: the first weekly cap to expire gets priority, more the closer
    it gets — already from ~36 h out, not only in the last hours."""
    soon = Account("soon", "soon", rows=[Row("session", 8, NOW + timedelta(hours=4), 18000),
                                         Row("weekly", 57, NOW + timedelta(hours=36), 604800)])
    later = Account("later", "later", rows=[Row("session", 1, NOW + timedelta(hours=3), 18000),
                                            Row("weekly", 32, NOW + timedelta(days=5), 604800)])
    assert choose([later, soon], "claude-fable-5", "later", NOW)[0] == "soon"  # 43/36 > 68/120
    later.rows[1].used_percent = 0  # fully fresh, five days ahead: still less urgent
    assert choose([later, soon], "claude-fable-5", "later", NOW)[0] == "soon"
    soon.rows[1].resets_at = NOW + timedelta(days=6)  # now the later reset → later wins
    assert choose([later, soon], "claude-fable-5", "later", NOW)[0] == "later"
    # Within the last hour the priority stops growing (1 h floor), but stays highest.
    soon.rows[1].resets_at = NOW + timedelta(minutes=10)
    _, _, candidates = choose([later, soon], "claude-fable-5", "later", NOW)
    assert candidates[1].score == 43


def test_session_never_masks_an_expiring_weekly_but_tight_session_demotes():
    a = Account("a", "a", rows=[Row("session", 89, NOW + timedelta(hours=5), 18000),
                                Row("weekly", 60, NOW + timedelta(hours=2), 604800)])
    b = Account("b", "b", rows=[Row("session", 5, NOW + timedelta(hours=5), 18000),
                                Row("weekly", 60, NOW + timedelta(hours=20), 604800)])
    selected, reason, candidates = choose([a, b], "gpt-6-sol", "b", NOW)
    assert selected == "a" and candidates[0].score == 20 and candidates[0].bottleneck == "weekly"
    a.rows[0].used_percent = 95  # session tight: b goes first even though a expires sooner
    selected, reason, candidates = choose([a, b], "gpt-6-sol", "b", NOW)
    assert selected == "b" and "[session tight]" in explain("gpt-6-sol", candidates, NOW, selected, reason)
    b.rows[0].used_percent = 97  # everyone tight → best score again, with a warning
    selected, reason, _ = choose([a, b], "gpt-6-sol", "b", NOW)
    assert selected == "a" and "session is tight" in reason
    a.rows[1].used_percent = 100
    assert choose([a, b], "gpt-6-sol", "b", NOW)[2][0].status == "excluded"


def test_model_only_cap_is_the_bottleneck_for_its_family_only():
    dentai = Account("dentai", "dentai", rows=[
        Row("session", 8, NOW + timedelta(hours=4, minutes=50), 18000),
        Row("weekly", 57, NOW + timedelta(hours=2, minutes=30), 604800),
        Row("Fable only", 86, NOW + timedelta(hours=2, minutes=30), 604800),
    ])
    kamp = Account("kamp", "kamp", rows=[
        Row("session", 1, NOW + timedelta(hours=2, minutes=50), 18000),
        Row("weekly", 32, NOW + timedelta(hours=35), 604800),
        Row("Fable only", 52, NOW + timedelta(hours=35), 604800),
    ])
    selected, reason, candidates = choose([kamp, dentai], "claude-fable-5-1", "kamp", NOW)
    assert selected == "dentai" and candidates[1].bottleneck == "Fable only"
    assert round(candidates[1].score, 1) == 5.6 and round(candidates[0].score, 1) == 1.4
    assert choose([kamp, dentai], "claude-opus-5", "kamp", NOW)[2][1].bottleneck == "weekly"


def test_untouched_weekly_counts_as_its_full_length():
    fresh = Account("fresh", "fresh", rows=[Row("session", 0, None, 18000), Row("weekly", 0, None, 604800)])
    used = Account("used", "used", rows=[Row("weekly", 40, NOW + timedelta(days=6), 604800)])
    _, _, candidates = choose([fresh, used], "claude-fable-5", "fresh", NOW)
    assert round(candidates[0].score, 3) == round(100 / 168, 3)  # 0.595 %/h
    assert choose([fresh, used], "claude-fable-5", "fresh", NOW)[0] == "fresh"  # 0.595 > 60/144
    used.rows[0].resets_at = NOW + timedelta(days=2)
    assert choose([fresh, used], "claude-fable-5", "fresh", NOW)[0] == "used"


def test_single_enabled_and_builtin_fallback(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"providerInstances": {
        "claudeAgent": {"driver": "claudeAgent", "enabled": False},
        "a": {"driver": "claudeAgent", "enabled": True},
        "b": {"driver": "claudeAgent", "enabled": True, "config": {"enabled": False}}
    }}))
    # A single profile is still polled: an exhausted one refuses, an unreachable one is unverified.
    collect = Mock(return_value=[Account("a", "a", error="HTTP 429")])
    selected, reason, explanation = route("claude-fable-5", "b", settings, collect)
    assert selected == "a" and "unverified" in reason and "unknown: HTTP 429" in explanation
    assert "[unknown] unknown: HTTP 429" in explanation
    collect = Mock(return_value=[account("a", 100)])
    with pytest.raises(ValueError, match="--profile") as info:
        route("claude-fable-5", "b", settings, collect)
    assert "excluded: session exhausted" in info.value.explanation
    settings.write_text('{}')
    assert claude_profiles(settings)[0][0] == "claudeAgent"
    collect = Mock(return_value=[Account("codex", "codex", error="no Codex login")])
    assert route("gpt-6-astra", "codex", settings, collect)[0] == "codex"


def test_codex_windows_and_nonstandard_caps():
    rows = [Row("weekly", 55, NOW + timedelta(days=3), 604800)]  # Pro: weekly only, no session
    a = Account("Codex A", "codex_a", rows=rows)
    b = Account("Codex B", "codex_b", rows=[Row("weekly", 21, NOW + timedelta(days=6, hours=7), 604800),
                                            Row("3h", 100, NOW + timedelta(hours=1), 10800)])
    selected, reason, _ = choose([a, b], "gpt-6-astra", "codex_b", NOW)
    assert selected == "codex_a" and "weekly" in reason  # the odd-length cap still excludes b
    b.rows[1].used_percent = 0
    b.rows[0].resets_at = NOW + timedelta(days=1)  # 79 % left with one day to go: 3.3 %/h beats 0.6
    assert choose([a, b], "gpt-6-astra", "codex_b", NOW)[0] == "codex_b"
    nan = Account("Codex C", "codex_c", rows=[Row("weekly", float("nan"), NOW + timedelta(days=1), 604800)])
    assert choose([nan], "gpt-6-astra", "codex_c", NOW)[1].startswith("usage unknown")


def test_driver_switch_routes_by_capacity_ties_prefer_sibling(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"providerInstances": {
        "codex": {"driver": "codex", "displayName": "Codex Alpha", "enabled": True},
        "codex_beta": {"driver": "codex", "displayName": "Codex Beta", "enabled": True},
        "claudeAgent": {"driver": "claudeAgent", "displayName": "Claude Beta", "enabled": True},
        "gamma": {"driver": "futureDriver", "displayName": "Future Gamma", "enabled": True},
    }}))
    even = lambda id: Account(id, id, rows=[Row("weekly", 20, NOW + timedelta(days=2), 604800)])
    collect = Mock(return_value=[even("codex"), even("codex_beta")])
    assert route("gpt-6-astra", "claudeAgent", settings, collect)[0] == "codex_beta"  # tie → sibling
    assert route("gpt-6-astra", "gamma", settings, collect)[0] == "codex"  # no sibling: still routed
    collect = Mock(return_value=[even("codex"), Account("codex_beta", "codex_beta", rows=[
        Row("weekly", 80, NOW + timedelta(days=2), 604800)])])
    assert route("gpt-6-astra", "claudeAgent", settings, collect)[0] == "codex"  # capacity beats sibling


def test_legacy_scoped_payload():
    rows, _ = claude_rows({"five_hour": {"utilization": 10},
                           "seven_day_fable": {"utilization": 100}})
    assert [(r.window, r.used_percent) for r in rows] == [("session", 10), ("Fable only", 100)]



def test_scoped_display_names_and_unknown_scopes():
    assert relevant("Claude Fable 5.1 only", "claude-fable-5-1")
    assert not relevant("Claude Opus 5 only", "claude-fable-5-1")
    assert relevant("future-model only", "claude-fable-5-1")
    assert relevant("scoped only", "claude-fable-5-1")


