"""Routing contracts: no network, Keychain, or live thread mutations."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "lib"))
from profile_routing import choose, relevant, route
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


def test_pace_headroom_and_stable_ties():
    a, b = account("a"), account("b")
    assert choose([b, a], "claude-fable-5", "a", NOW)[0] == "a"
    assert choose([b, a], "claude-fable-5", "missing", NOW)[0] == "a"
    b.rows[1].resets_at = NOW + timedelta(days=6)
    assert choose([b, a], "claude-fable-5", "b", NOW)[0] == "a"


def test_single_enabled_and_builtin_fallback(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"providerInstances": {
        "claudeAgent": {"driver": "claudeAgent", "enabled": False},
        "a": {"driver": "claudeAgent", "enabled": True},
        "b": {"driver": "claudeAgent", "enabled": True, "config": {"enabled": False}}
    }}))
    collect = Mock(side_effect=AssertionError("single profile must not poll"))
    assert route("claude-fable-5", "b", settings, collect)[0] == "a"
    settings.write_text('{}')
    assert claude_profiles(settings)[0][0] == "claudeAgent"
    assert route("gpt-6-astra", "codex", settings, collect)[0] == "codex"


def test_legacy_scoped_payload():
    rows, _ = claude_rows({"five_hour": {"utilization": 10},
                           "seven_day_fable": {"utilization": 100}})
    assert [(r.window, r.used_percent) for r in rows] == [("session", 10), ("Fable only", 100)]


def test_shell_override_and_model_effort(tmp_path):
    # Exercise the actual selection/effort block with a stub router; no T3 server.
    script = (SCRIPTS / "t3-spawn-thread").read_text()
    functions = script[script.index("normalize_model()") : script.index("detect_source_thread_id()")]
    selection = script[script.index('provider_instance_id="$(printf') : script.index("# Mirror T3's own rule")]
    prelude = '''set -eu
normalize_provider() { printf '%s' "$1"; }
uv() { echo polled >&2; echo claudeAgent_b; }
provider_choice="$1"; model_choice=fable; thinking_choice=high
t3_base_dir=/unused
model_selection_json='{"instanceId":"claudeAgent_a","model":"claude-opus-5","options":[]}'
'''
    runner = tmp_path / "selection.sh"
    runner.write_text(prelude + functions + selection + '\necho "$model_selection_json"\n')
    for profile, expected, polled in [("claudeAgent_a", "claudeAgent_a", False),
                                      ("auto", "claudeAgent_b", True)]:
        result = subprocess.run(["bash", str(runner), profile], capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        assert payload == {"instanceId": expected, "model": "claude-fable-5-1",
                           "options": [{"id": "effort", "value": "high"}]}
        assert ("polled" in result.stderr) is polled


def test_scoped_display_names_and_unknown_scopes():
    assert relevant("Claude Fable 5.1 only", "claude-fable-5-1")
    assert not relevant("Claude Opus 5 only", "claude-fable-5-1")
    assert relevant("future-model only", "claude-fable-5-1")
    assert relevant("scoped only", "claude-fable-5-1")
