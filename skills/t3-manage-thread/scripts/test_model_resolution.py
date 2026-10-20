import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "lib"))
from model_resolution import resolve


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_numeric_versions_and_family_filter(tmp_path):
    now = datetime.now(timezone.utc)
    write(tmp_path / "userdata/model-manifest.json", {
        "fetchedAtMs": int(now.timestamp() * 1000),
        "manifest": {"currentModels": {
            "codex": ["gpt-5.6-sol", "gpt-6-sol", "gpt-6-sol-preview", "gpt-7-astra"],
            "claudeAgent": ["claude-opus-5", "claude-opus-5-5", "claude-opus-5-10", "claude-opus-6-preview"],
        }},
    })
    assert resolve("sol", tmp_path) == "gpt-6-sol"
    assert resolve("opus", tmp_path) == "claude-opus-5-10"


def test_codex_account_catalog_and_stale_cache(tmp_path):
    now = datetime.now(timezone.utc)
    write(tmp_path / "userdata/model-manifest.json", {
        "fetchedAtMs": int(now.timestamp() * 1000),
        "manifest": {"currentModels": {"codex": ["gpt-6-sol"]}},
    })
    home = tmp_path / "codex-home"
    write(tmp_path / "userdata/settings.json", {"providerInstances": {
        "codex_test": {"config": {"homePath": str(home)}}
    }})
    cache_path = home / "models_cache.json"
    write(cache_path, {"fetched_at": now.isoformat(), "models": [
        {"slug": "gpt-5.6-sol", "visibility": "list", "supported_in_api": True},
        {"slug": "gpt-7-sol", "visibility": "hide", "supported_in_api": True},
    ]})
    assert resolve("sol", tmp_path, "codex_test") == "gpt-5.6-sol"
    write(cache_path, {"fetched_at": now.isoformat(), "models": [
        {"slug": "gpt-6-astra", "visibility": "list", "supported_in_api": True},
    ]})
    with pytest.raises(ValueError, match="no available sol model"):
        resolve("sol", tmp_path, "codex_test")
    write(cache_path, {"fetched_at": "2020-01-01T00:00:00Z", "models": [
        {"slug": "gpt-5.6-sol", "visibility": "list", "supported_in_api": True},
    ]})
    assert resolve("sol", tmp_path, "codex_test") == "gpt-6-sol"


def test_missing_catalog_uses_known_stable_fallback(tmp_path):
    assert resolve("sol", tmp_path) == "gpt-6-sol"
    assert resolve("opus", tmp_path) == "claude-opus-5-5"


@pytest.mark.parametrize("requested, expected, effort", [
    ("openai", "gpt-6-astra", "medium"),
    ("codex", "gpt-6-astra", "medium"),
    ("OpenAI", "gpt-6-astra", "medium"),
    ("claude", "claude-opus-5-5", "high"),
    ("anthropic", "claude-opus-5-5", "high"),
    ("sol", "gpt-6.1-sol", "high"),  # Direct review or Astra's scoped child.
    ("gpt-6.1-sol", "gpt-6.1-sol", "high"),
])
def test_provider_alias_and_explicit_model(tmp_path, requested, expected, effort):
    import os
    import subprocess
    write(tmp_path / "userdata/model-manifest.json", {"manifest": {"currentModels": {
        "codex": ["gpt-6.1-sol"], "claudeAgent": ["claude-opus-5-5"]}}})
    env = {**os.environ, "T3CODE_HOME": str(tmp_path)}
    result = subprocess.run([str(SCRIPTS / "t3-pick-instance"), "--resolve", requested],
                            env=env, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected
    result = subprocess.run(["bash", "-c", 'source "$1"; house_thinking "$2"', "test",
                             str(SCRIPTS / "lib/t3-common.sh"), expected],
                            capture_output=True, text=True, check=True)
    assert result.stdout == effort
