"""Native T3 profile discovery, without account-specific aliases."""
import json
import sys
from pathlib import Path


def registry(path):
    settings = json.loads(Path(path).read_text())
    instances = dict(settings.get("providerInstances", {}))
    # T3's legacy built-in defaults; configured instances always take precedence.
    for driver in {"codex", "claudeAgent", *settings.get("providers", {})}:
        instances.setdefault(driver, {
            "driver": driver, **settings.get("providers", {}).get(driver, {})})
    return instances


def enabled(entry):
    if not entry:
        return False
    config = entry.get("config") or {}
    if entry.get("enabled") is False or config.get("enabled") is False:
        return False
    # Native resolveProviderInstanceEnabled: unknown fork drivers default on.
    default = entry.get("driver") not in {"cursor", "grok", "opencode", "antigravity"}
    return entry.get("enabled", config.get("enabled", default))


def family(entry):
    driver = entry.get("driver", "unknown")
    return "claude" if driver == "claudeAgent" else driver


def resolve(instances, requested, model_family="unknown"):
    if requested == "auto":
        return requested
    requested = {"claude": "claudeAgent", "sol": "codex"}.get(requested, requested)
    if requested in instances:
        if not enabled(instances[requested]):
            raise ValueError(f"T3 provider is disabled: {requested}")
        return requested
    name = requested.casefold()
    matches = [id for id, entry in instances.items() if enabled(entry) and
               (name in id.casefold() or name in str(entry.get("displayName") or
                 (entry.get("config") or {}).get("displayName") or "").casefold())]
    if model_family != "unknown":
        matches = [id for id in matches if family(instances[id]) == model_family]
    if len(matches) == 1:
        return matches[0]
    available = ", ".join(f"{id} ({entry.get('displayName') or entry.get('driver')})"
                          for id, entry in instances.items() if enabled(entry))
    raise ValueError(f"{'Ambiguous' if matches else 'Unknown or incompatible'} --profile: "
                     f"{requested}. Enabled provider instances: {available}")


DRIVER_WORDS = {"claude", "codex", "gemini", "antigravity", "opencode", "cursor", "grok"}


def account_label(entry):
    """Display name minus the driver word: 'Codex Beta' and 'Claude Beta' share 'beta'."""
    name = str(entry.get("displayName") or (entry.get("config") or {}).get("displayName") or "")
    return tuple(w for w in name.casefold().split() if w not in DRIVER_WORDS)


def compatible(instances, preferred, model_family):
    candidates = [id for id, entry in instances.items()
                  if enabled(entry) and family(entry) == model_family]
    if preferred in candidates:
        return preferred
    if len(candidates) == 1:
        return candidates[0]
    # Driver switch: stay on the same account (sibling instance with the same label).
    label = account_label(instances.get(preferred, {}))
    siblings = [id for id in candidates if label and account_label(instances[id]) == label]
    if len(siblings) == 1:
        return siblings[0]
    raise ValueError(f"Choose --profile explicitly for {model_family}: "
                     f"{', '.join(candidates) or 'no enabled profiles'}")


if __name__ == "__main__":
    try:
        instances = registry(sys.argv[2])
        if sys.argv[1] == "resolve":
            print(resolve(instances, sys.argv[3], sys.argv[4]))
        elif sys.argv[1] == "enabled":
            print(str(enabled(instances.get(sys.argv[3], {}))).lower())
        else:
            print(family(instances.get(sys.argv[3], {})))
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(2)
