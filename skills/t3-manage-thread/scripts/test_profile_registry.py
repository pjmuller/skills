"""Native registry + real spawn selection block, without live thread mutations."""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "lib"))
from profile_registry import registry, resolve, enabled
from profile_routing import route
from t3_limits import Account


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "userdata" / "settings.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"providerInstances": {
        "codex": {"driver": "codex", "displayName": "Codex Alpha", "enabled": True,
                  "config": {"homePath": str(tmp_path / "no-codex-home")}},
        "codex_beta": {"driver": "codex", "displayName": "Codex Beta", "enabled": True,
                       "config": {"homePath": str(tmp_path / "no-codex-home-beta")}},
        "claudeAgent": {"driver": "claudeAgent", "displayName": "Claude Beta", "enabled": True},
        "antigravity_beta": {"driver": "antigravity", "displayName": "Gemini Beta", "enabled": True},
        "new_instance": {"driver": "futureDriver", "displayName": "Future Gamma", "enabled": True},
        "codex_disabled": {"driver": "codex", "displayName": "Codex Beta", "enabled": False},
    }}))
    (path.parent / "model-manifest.json").write_text(json.dumps({"manifest": {
        "currentModels": {"codex": ["gpt-6.1-sol"]}}}))
    return path


def test_registry_names_and_ambiguity(settings):
    profiles = registry(settings)
    assert resolve(profiles, "BETA", "codex") == "codex_beta"
    assert resolve(profiles, "Beta", "claude") == "claudeAgent"
    assert resolve(profiles, "Gamma") == "new_instance"
    assert resolve(profiles, "codex_beta", "claude") == "codex_beta"  # exact wins; shell validates
    with pytest.raises(ValueError, match="Ambiguous"):
        resolve(profiles, "beta")
    with pytest.raises(ValueError, match="disabled"):
        resolve(profiles, "codex_disabled")
    with pytest.raises(ValueError, match="Unknown"):
        resolve(profiles, "missing")


def test_auto_preserves_codex_and_sibling_tie(settings):
    unknown = lambda **_: [Account("codex", "codex", error="x"), Account("codex_beta", "codex_beta", error="x")]
    assert route("gpt-6-astra", "codex_beta", settings, unknown)[0] == "codex_beta"
    # Driver switch with no verified capacity: Claude Beta -> Codex Beta (sibling label).
    assert route("gpt-6-astra", "claudeAgent", settings, unknown)[0] == "codex_beta"
    assert route("gpt-6-astra", "new_instance", settings, unknown)[0] == "codex"  # no sibling: first id


def test_list_profiles_rows(settings):
    result = subprocess.run([str(SCRIPTS / "t3-list-profiles"), "--json"], capture_output=True, text=True,
                            env={**os.environ, "T3CODE_HOME": str(settings.parent.parent)})
    assert result.returncode == 0, result.stderr
    got = {(r["ecosystem"], r["instance_id"]): r["profile"] for r in json.loads(result.stdout)}
    assert got[("OpenAI", "codex")] == "alpha" and got[("OpenAI", "codex_beta")] == "beta"
    assert got[("Claude", "claudeAgent")] == "beta"          # same label, other ecosystem
    assert ("OpenAI", "codex_disabled") not in got


def test_list_profiles_shows_cached_plan_tier_without_network(settings):
    userdata = settings.parent
    (userdata / "t3-limits-cache.json").write_text(json.dumps({
        "codex": {"payload": {"plan_type": "prolite"}}, "codex_beta": {"payload": {"plan_type": "pro"}},
        "claudeAgent": {"payload": {"_t3_claude_plan": "max_20x"}}}))
    (userdata / "t3-plan-multipliers.json").write_text(json.dumps({"codex": {"prolite": 5}}))
    env = {**os.environ, "T3CODE_HOME": str(userdata.parent)}
    run = lambda *args: subprocess.run([str(SCRIPTS / "t3-list-profiles"), *args], capture_output=True, text=True, env=env)
    rows = {r["instance_id"]: r for r in json.loads(run("--json").stdout)}
    assert (rows["codex"]["multiplier"], rows["codex"]["multiplier_source"]) == (5, "map")
    assert rows["codex_beta"]["tier"] == "pro · 1x?" and rows["claudeAgent"]["tier"] == "max_20x · 20x"
    assert "tier" not in rows["antigravity_beta"]
    assert "prolite · 5x map" in run().stdout


def test_native_enablement_defaults():
    assert enabled({"driver": "futureDriver"})
    assert enabled({"driver": "codex"})
    assert not enabled({"driver": "grok"})
    assert not enabled({"driver": "codex", "enabled": True, "config": {"enabled": False}})
    assert not enabled({})
