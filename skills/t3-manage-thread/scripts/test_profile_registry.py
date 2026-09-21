"""Native registry + real spawn selection block, without live thread mutations."""
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "lib"))
from profile_registry import registry, resolve, enabled
from profile_routing import route


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "userdata" / "settings.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"providerInstances": {
        "codex": {"driver": "codex", "displayName": "Codex Alpha", "enabled": True},
        "codex_beta": {"driver": "codex", "displayName": "Codex Beta", "enabled": True},
        "claudeAgent": {"driver": "claudeAgent", "displayName": "Claude Beta", "enabled": True},
        "antigravity_beta": {"driver": "antigravity", "displayName": "Gemini Beta", "enabled": True},
        "new_instance": {"driver": "futureDriver", "displayName": "Future Gamma", "enabled": True},
        "codex_disabled": {"driver": "codex", "displayName": "Codex Beta", "enabled": False},
    }}))
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


def test_auto_preserves_codex_and_refuses_account_guess(settings):
    assert route("gpt-6-astra", "codex_beta", settings)[0] == "codex_beta"
    with pytest.raises(ValueError, match="Choose --profile"):
        route("gpt-6-astra", "claudeAgent", settings)


@pytest.mark.parametrize("profile,model,inherited,expected,option", [
    ("beta", "astra", "claudeAgent", "codex_beta", "reasoningEffort"),
    ("auto", "astra", "codex_beta", "codex_beta", "reasoningEffort"),
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
    ("auto", "astra", "claudeAgent", None, None),
])
def test_spawn_selection(settings, tmp_path, profile, model, inherited, expected, option):
    script = (SCRIPTS / "t3-spawn-thread").read_text()
    functions = script[script.index("normalize_provider()") : script.index("detect_source_thread_id()")]
    selection = script[script.index('provider_instance_id="$(printf') : script.index('if [[ -z "$thread_title"')]
    # Keep the real helpers but point their relative paths at this checkout.
    code = functions + selection
    code = code.replace('$(dirname "$(readlink -f "$0")")', str(SCRIPTS))
    inherited_model = ("claude-opus-5" if inherited == "claudeAgent" else
                       "future-model" if inherited == "new_instance" else "gpt-5.6-sol")
    payload = json.dumps({"instanceId": inherited, "model": inherited_model,
                          "options": [{"id": "fastMode", "value": True}]})
    runner = tmp_path / "selection.sh"
    runner.write_text("set -eu\n" +
        f"provider_choice={shlex.quote(profile)}; model_choice={shlex.quote(model)}; thinking_choice=auto\n" +
        f"t3_base_dir={shlex.quote(str(settings.parent.parent))}\n" +
        f"model_selection_json={shlex.quote(payload)}\n" + code + '\necho "$model_selection_json"\n')
    result = subprocess.run(["bash", str(runner)], capture_output=True, text=True)
    if expected is None:
        assert result.returncode != 0
        assert any(word in result.stderr for word in ["incompatible", "Ambiguous", "Choose --profile"])
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
        if model == "auto" and inherited == "codex":
            assert {"id": "fastMode", "value": True} in selected["options"]


def test_native_enablement_defaults():
    assert enabled({"driver": "futureDriver"})
    assert enabled({"driver": "codex"})
    assert not enabled({"driver": "grok"})
    assert not enabled({"driver": "codex", "enabled": True, "config": {"enabled": False}})
    assert not enabled({})
