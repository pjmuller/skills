#!/usr/bin/env python3
"""Resolve family aliases against T3's local model catalog without an LLM call."""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


FAMILIES = {
    "sol": ("codex", re.compile(r"gpt-(\d+(?:\.\d+)?)-sol$"), "gpt-6-sol"),
    "opus": ("claudeAgent", re.compile(r"claude-opus-(\d+(?:-\d+)*)$"), "claude-opus-5-5"),
}
MAX_CACHE_AGE = timedelta(hours=1)


def _read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _version(slug, pattern):
    match = pattern.fullmatch(slug)
    if not match:
        return None
    return tuple(int(part) for part in re.split(r"[.-]", match.group(1)))


def _fresh(value):
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - instant
        return timedelta(0) <= age <= MAX_CACHE_AGE
    except (AttributeError, TypeError, ValueError):
        return False


def resolve(alias, base_dir, instance_id=None):
    driver, pattern, fallback = FAMILIES[alias]
    base_dir = Path(base_dir)
    stored = _read_json(base_dir / "userdata/model-manifest.json")
    if not isinstance(stored, dict):
        stored = {}
    manifest = stored.get("manifest")
    current_models = manifest.get("currentModels") if isinstance(manifest, dict) else None
    current = current_models.get(driver, []) if isinstance(current_models, dict) else []
    if not isinstance(current, list):
        current = []
    candidates = {slug for slug in current if isinstance(slug, str) and _version(slug, pattern) is not None}
    if not candidates:
        print(f"note: T3 model catalog lacks {alias}; using {fallback}", file=sys.stderr)
        candidates = {fallback}

    if driver == "codex" and instance_id:
        settings = _read_json(base_dir / "userdata/settings.json")
        instances = settings.get("providerInstances") if isinstance(settings, dict) else None
        instance = instances.get(instance_id) if isinstance(instances, dict) else None
        config = instance.get("config") if isinstance(instance, dict) else None
        if not isinstance(config, dict):
            config = {}
        home_path = config.get("homePath")
        home = Path(home_path if isinstance(home_path, str) and home_path else "~/.codex").expanduser()
        cache = _read_json(home / "models_cache.json")
        if isinstance(cache, dict) and _fresh(cache.get("fetched_at")) and isinstance(cache.get("models"), list):
            available = {
                item["slug"] for item in cache.get("models", [])
                if isinstance(item, dict) and isinstance(item.get("slug"), str)
                and item.get("visibility") == "list" and item.get("supported_in_api") is True
                and _version(item["slug"], pattern) is not None
            }
            if available:
                # Codex's per-account catalog is authoritative; it can include a
                # still-available version that T3 no longer calls current.
                candidates = available
            else:
                raise ValueError(f"Codex account {instance_id} has no available {alias} model")

    return max(candidates, key=lambda slug: (_version(slug, pattern), slug))


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in FAMILIES:
        raise SystemExit("usage: model_resolution.py sol|opus T3_HOME [INSTANCE_ID]")
    try:
        print(resolve(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None))
    except ValueError as error:
        raise SystemExit(str(error)) from None
