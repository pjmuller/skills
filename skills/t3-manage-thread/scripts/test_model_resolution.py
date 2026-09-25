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
