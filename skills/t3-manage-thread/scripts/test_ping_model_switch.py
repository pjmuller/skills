"""t3-ping-thread's real model-switch block, without a live T3 server."""
import json
import shlex
import subprocess
from pathlib import Path

import pytest

from test_profile_registry import settings  # noqa: F401  (shared native-registry fixture)

SCRIPTS = Path(__file__).resolve().parent


def run_switch(settings, model, thinking, current):
    script = (SCRIPTS / "t3-ping-thread").read_text()
    block = script[script.index("previous_selection_json=") : script.index('# The server drives provider sessions')]
    runner = "\n".join([
        "set -eu",
        f"source {SCRIPTS}/lib/t3-common.sh",
        f"t3_base_dir={shlex.quote(str(settings.parent.parent))}",
        f"model_choice={shlex.quote(model)}; thinking_choice={shlex.quote(thinking)}",
        f"model_selection_json={shlex.quote(json.dumps(current))}",
        block,
        'echo "$model_switched $model_selection_json"',
    ])
    return subprocess.run(["bash", "-c", runner], capture_output=True, text=True)


CLAUDE = {"instanceId": "claudeAgent", "model": "claude-fable-5-1",
          "options": [{"id": "effort", "value": "medium"}, {"id": "fastMode", "value": True}]}
CODEX = {"instanceId": "codex_beta", "model": "gpt-6-astra", "options": [{"id": "reasoningEffort", "value": "medium"}]}


@pytest.mark.parametrize("model,thinking,current,expected", [
    ("opus", "", CLAUDE, ("claude-opus-5-5", "effort", "high")),  # house effort, fastMode dropped
    ("haiku", "medium", CLAUDE, ("claude-haiku-4-5", "effort", "medium")),  # downgrade, explicit effort
    ("", "high", CLAUDE, ("claude-fable-5-1", "effort", "high")),  # effort only keeps model
    ("fable", "", {**CLAUDE, "options": [{"id": "effort", "value": "high"}]},
     ("claude-fable-5-1", "effort", "medium")),  # same model, explicit --model: house effort
    ("sol", "", {**CODEX, "model": "gpt-6.1-sol", "options": [{"id": "reasoningEffort", "value": "low"}]},
     ("gpt-6.1-sol", "reasoningEffort", "high")),
    ("sol", "", CODEX, ("gpt-6.1-sol", "reasoningEffort", "high")),  # same Codex account
    ("luna", "low", CODEX, ("gpt-6-luna", "reasoningEffort", "low")),
    ("sol", "", CLAUDE, None),  # other provider: refused, never migrated
    ("fable", "", CODEX, None),
    ("gpt-5.6-sol", "", CODEX, None),  # below the floor
    ("", "ultra", CLAUDE, None),
])
def test_ping_model_switch(settings, model, thinking, current, expected):  # noqa: F811
    result = run_switch(settings, model, thinking, current)
    if expected is None:
        assert result.returncode != 0
        assert any(w in result.stderr for w in ["keeps its provider account", "below the floor", "Invalid thinking"])
        return
    assert result.returncode == 0, result.stderr
    switched, selection = result.stdout.split(" ", 1)
    selection = json.loads(selection)
    assert switched == "1"
    assert selection["instanceId"] == current["instanceId"]
    assert selection["model"] == expected[0]
    assert {"id": expected[1], "value": expected[2]} in selection["options"]
    assert ({"id": "fastMode", "value": True} in selection["options"]) == (selection["model"] == current["model"]
                                                                         and "fastMode" in json.dumps(current))
