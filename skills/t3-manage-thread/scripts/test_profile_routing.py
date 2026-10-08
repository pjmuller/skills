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
    a, b = account("a", plan="max_20x"), account("b", plan="max_20x")
    assert choose([b, a], "claude-fable-5", "a", NOW)[0] == "a"
    assert choose([b, a], "claude-fable-5", "b", NOW)[0] == "b"  # equal plans: inherited account wins
    assert choose([b, a], "claude-fable-5", "missing", NOW)[0] == "a"
    selected, reason, candidates = choose([b, a], "claude-fable-5", "a", NOW)
    explanation = explain("claude-fable-5", candidates, NOW, selected, reason)
    assert "a  [max_20x]" in explanation and "b  [max_20x]" in explanation and "%/h × 20x" in explanation
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
    assert selected == "b" and "[session tight: 5 ≤ 10 plan-% units]" in explain("gpt-6-sol", candidates, NOW, selected, reason)
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




def test_plan_multiplier_weights_identical_percentages():
    """PJ 2026-10-08: a 5x account at the same % as a 20x has a quarter of the quota;
    routing must stop treating equal percentages as equal work."""
    big, small = account("big", 40, plan="max_20x"), account("small", 40, plan="max_5x")
    selected, reason, candidates = choose([small, big], "claude-fable-5", "small", NOW)
    assert selected == "big" and "× 20x" in reason and "plan-weighted" in reason
    assert candidates[0].weight == 5 and candidates[1].weight == 20
    assert round(candidates[1].score / candidates[0].score, 3) == 4.0
    assert choose([small, account("pro", 40, plan="pro")], "claude-fable-5", "pro", NOW)[0] == "small"
    # The label format is controlled; stray digits in prose or e-mails never become a multiplier.
    from profile_routing import plan_weight
    assert plan_weight("max_20x (pro)") == 20 and plan_weight("max_5x") == 5
    assert plan_weight("pro") == plan_weight("prolite · x20x@example.com") == plan_weight("unknown") == 1
    assert plan_weight("legacy_20x") == plan_weight("20x") == 1  # only the `max_Nx` shape is trusted


def test_small_plan_still_wins_when_its_reset_is_urgent_or_the_big_one_is_nearly_out():
    big = Account("big", "big", plan="max_20x", rows=[Row("session", 10, NOW + timedelta(hours=4), 18000),
                                                        Row("weekly", 50, NOW + timedelta(hours=72), 604800)])
    small = Account("small", "small", plan="max_5x", rows=[Row("session", 10, NOW + timedelta(hours=4), 18000),
                                                            Row("weekly", 50, NOW + timedelta(hours=24), 604800)])
    assert choose([small, big], "claude-fable-5", "small", NOW)[0] == "big"  # 20·50/72 = 13.9 > 5·50/24 = 10.4
    small.rows[1].resets_at = NOW + timedelta(hours=12)  # 5·50/12 = 20.8: the sooner reset wins again
    assert choose([small, big], "claude-fable-5", "big", NOW)[0] == "small"
    small.rows[1].resets_at = NOW + timedelta(hours=72)
    big.rows[1].used_percent = 95  # 20·5/72 = 1.4 < 5·50/72 = 3.5: a nearly exhausted 20x loses
    assert choose([small, big], "claude-fable-5", "big", NOW)[0] == "small"


def test_session_tightness_is_measured_in_plan_units_of_the_largest_verified_plan():
    big = account("big", 10, plan="max_20x")
    big.rows[1].resets_at = NOW + timedelta(days=5)
    small = Account("small", "small", plan="max_5x", rows=[Row("session", 59, NOW + timedelta(hours=4), 18000),
                                                            Row("weekly", 10, NOW + timedelta(hours=24), 604800)])
    # 5x at 59 % used: 5·41 = 205 plan-% > 200 → not tight; its sooner reset wins (5·90/24 > 20·90/120).
    selected, _, candidates = choose([big, small], "claude-fable-5", "big", NOW)
    assert selected == "small" and not candidates[1].session_tight
    small.rows[0].used_percent = 60  # 5·40 = 200 ≤ 200 → tight: ranks after the 20x despite weekly room
    selected, _, candidates = choose([big, small], "claude-fable-5", "big", NOW)
    assert selected == "big" and candidates[1].session_tight and "200 ≤ 200" in candidates[1].detail
    big.rows[0].used_percent = 89  # 20·11 = 220 → the old ≥ 90 % rule is unchanged for a 20x
    assert not choose([big, small], "claude-fable-5", "big", NOW)[2][0].session_tight
    big.rows[0].used_percent = 90
    assert choose([big, small], "claude-fable-5", "big", NOW)[2][0].session_tight
    small.rows[0].used_percent = 61
    # An excluded 20x must not set the bar: alone among verified accounts, a 5x uses its own scale.
    big.rows[1].used_percent = 100
    selected, _, candidates = choose([big, small], "claude-fable-5", "big", NOW)
    assert selected == "small" and candidates[0].status == "excluded" and not candidates[1].session_tight


def test_unused_1x_beside_20x_is_overflow_only_and_says_so():
    pro = account("pro", 0, plan="pro")
    big = account("big", 80, plan="max_20x")
    selected, _, candidates = choose([pro, big], "claude-fable-5", "pro", NOW)
    assert selected == "big" and candidates[0].session_tight
    assert "[session tight: 100 ≤ 200 plan-% units]" in explain("claude-fable-5", candidates, NOW, selected, "")
    big.rows[0].used_percent = 95  # both tight → plan-weighted score decides: 20·1 vs 1·100 per 48 h
    big.rows[1].used_percent = 99
    assert choose([pro, big], "claude-fable-5", "pro", NOW)[0] == "pro"
