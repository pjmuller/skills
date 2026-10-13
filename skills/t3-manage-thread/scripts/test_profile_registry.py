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


def run_selection(settings, tmp_path, profile, model, inherited, force=0, routing=None):
    """The real spawn selection block (no live T3), optionally with a fake routing helper."""
    script = (SCRIPTS / "t3-spawn-thread").read_text()
    functions = script[script.index("normalize_provider()") : script.index("detect_source_thread_id()")]
    selection = script[script.index('provider_instance_id="$(printf') : script.index('if [[ -z "$thread_title"')]
    # Keep the real helpers but point their relative paths at this checkout.
    code = functions + selection
    code = code.replace('$(dirname "$(readlink -f "$0")")', str(SCRIPTS))
    if routing:
        code = code.replace(f"{SCRIPTS}/lib/profile_routing.py", str(routing))
    inherited_model = ("claude-opus-5" if inherited == "claudeAgent" else
                       "future-model" if inherited == "new_instance" else "gpt-6.1-sol")
    payload = json.dumps({"instanceId": inherited, "model": inherited_model,
                          "options": [{"id": "fastMode", "value": True}]})
    runner = tmp_path / "selection.sh"
    runner.write_text("set -eu\n" +
        "allow_old_model_reason=''\n" +
        f"provider_choice={shlex.quote(profile)}; model_choice={shlex.quote(model)}; thinking_choice=auto\n" +
        f"provider_from_flag=1; force_profile={force}\n" +
        f"original_args=(--model {shlex.quote(model)} --profile {shlex.quote(profile)} -- brief)\n" +
        f"t3_base_dir={shlex.quote(str(settings.parent.parent))}\n" +
        f"model_selection_json={shlex.quote(payload)}\n" + code + '\necho "$model_selection_json"\n')
    # Hermetic: no Keychain (fake `security`) and no Codex homes → every account is "unknown".
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    (fake_bin / "security").write_text("#!/bin/sh\nexit 1\n")
    (fake_bin / "security").chmod(0o755)
    env = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}")
    return subprocess.run(["bash", str(runner)], capture_output=True, text=True, env=env)


@pytest.mark.parametrize("profile,model,inherited,expected,option", [
    ("beta", "astra", "claudeAgent", "codex_beta", "reasoningEffort"),
    ("auto", "astra", "codex_beta", "codex_beta", "reasoningEffort"),
    ("alpha,beta", "astra", "codex_beta", "codex_beta", "reasoningEffort"),  # list: tie keeps inherited
    ("codex_beta", "auto", "codex", "codex_beta", "reasoningEffort"),
    ("codex_beta", "auto", "claudeAgent", "codex_beta", "reasoningEffort"),
    ("beta", "fable", "codex_beta", "claudeAgent", "effort"),
    ("auto", "fable", "codex_beta", "claudeAgent", "effort"),
    ("Gamma", "future-model", "codex", "new_instance", "effort"),
    ("auto", "auto", "new_instance", "new_instance", "effort"),
    ("auto", "gemini", "codex", "antigravity_beta", None),
    ("antigravity_beta", "astra", "codex", None, None),
    ("codex_beta", "fable", "codex", None, None),
    ("beta", "auto", "codex", None, None),
    ("auto", "astra", "claudeAgent", "codex_beta", "reasoningEffort"),
    ("auto", "astra", "new_instance", "codex", "reasoningEffort"),  # no sibling: capacity routing, first id
    ("codex_beta", "gpt-6.1-sol", "codex", "codex_beta", "reasoningEffort"),
    ("codex_beta", "gpt-5.6-sol", "codex", None, None),
    ("auto", "claude-opus-5", "claudeAgent", "claudeAgent", "effort"),
    ("auto", "claude-fable-9", "claudeAgent", "claudeAgent", "effort"),  # future id: family effort
    ("codex_beta", "gpt-9-astra", "codex", "codex_beta", "reasoningEffort"),
])
def test_spawn_selection(settings, tmp_path, profile, model, inherited, expected, option):
    result = run_selection(settings, tmp_path, profile, model, inherited)
    if expected is None:
        assert result.returncode != 0
        assert any(word in result.stderr for word in ["incompatible", "Ambiguous", "Choose --profile", "below the floor"])
    else:
        assert result.returncode == 0, result.stderr
        selected = json.loads(result.stdout)
        assert selected["instanceId"] == expected
        if option:
            assert option in [o["id"] for o in selected["options"]]
        else:
            assert selected["options"] == []
        if model == "astra":
            assert selected["model"] == "gpt-6-astra"
            assert {"id": "reasoningEffort", "value": "medium"} in selected["options"]
        if model in ("gpt-6.1-sol", "claude-opus-5"):
            assert selected["model"] == model
        if model in ("claude-fable-9", "gpt-9-astra"):
            assert {"id": option, "value": "medium"} in selected["options"]
        if profile == "codex_beta" and model == "auto" and inherited == "claudeAgent":
            assert selected["model"] == "gpt-6.1-sol"
        if model == "auto" and inherited == "codex":
            assert {"id": "fastMode", "value": True} in selected["options"]



def test_explicit_exhausted_profile_refuses_unless_forced(settings, tmp_path):
    """Incident 2026-10-11: --profile kampkompas with its "Fable only" cap at 100 %."""
    fake = tmp_path / "routing.py"
    fake.write_text('import sys\nif sys.argv[1] == "--check":\n'
                    '    print("Fable only exhausted", file=sys.stderr); print("codex"); raise SystemExit(2)\n'
                    'print(sys.argv[2])\n')
    refused = run_selection(settings, tmp_path, "codex_beta", "astra", "codex", routing=fake)
    assert refused.returncode == 2
    assert "--model astra --profile codex -- brief" in refused.stderr and "--force-profile" in refused.stderr
    forced = run_selection(settings, tmp_path, "codex_beta", "astra", "codex", force=1, routing=fake)
    assert forced.returncode == 0 and json.loads(forced.stdout)["instanceId"] == "codex_beta"


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
