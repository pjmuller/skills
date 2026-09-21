"""Wrapper-owned account configuration: one JSON file, no executable config."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

KEYS = {
    "account", "config_dir", "scopes", "mint_scopes", "client_env",
    "legacy_token", "offline_token_file", "account_env", "config_dir_env",
    "cloud_token_env",
}
REQUIRED = ("account", "config_dir", "scopes")
OPENID_SCOPE = "https://www.googleapis.com/auth/userinfo.email"


@dataclass(frozen=True)
class WorkspaceConfig:
    """Everything account-specific. Commands and implementations never add defaults."""

    account: str
    config_dir: Path
    scopes: tuple[str, ...]
    mint_scopes: tuple[str, ...]
    client_env: tuple[Path, ...] = ()
    legacy_token: Path | None = None
    offline_token_file: Path | None = None
    cloud_token_env: bool = False
    source: Path | None = None

    @property
    def token_path(self) -> Path:
        return self.config_dir / "token.json"

    @property
    def client_path(self) -> Path:
        return self.config_dir / "client.json"

    @property
    def wants_openid(self) -> bool:
        """Tokens without the OpenID scope are identified through the Gmail profile instead."""
        return OPENID_SCOPE in self.scopes


def _path(base: Path, value: str) -> Path:
    """Absolute, `~`-relative, or relative to the config file. Resolved lexically: a symlink
    in the path must still be visible to the credential checks that refuse one."""
    expanded = Path(str(value)).expanduser()
    if expanded.is_absolute():
        return Path(os.path.normpath(expanded))
    return Path(os.path.normpath(base / expanded))


def _strings(raw: object, key: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
        raise ConfigError(f"{key} must be a list of non-empty strings")
    return tuple(raw)


def _override(raw: dict, key: str) -> str | None:
    """Read the env variable this config explicitly opts into, if it is set."""
    name = raw.get(key)
    return os.environ.get(str(name)) if name else None


def config_path(explicit: str | Path | None = None) -> Path:
    """`--config` wins, then $GWS_CONFIG. Never guessed from the working directory."""
    value = explicit or os.environ.get("GWS_CONFIG")
    if not value:
        raise ConfigError(
            "no account configuration: pass --config <wrapper>/workspace.json or set GWS_CONFIG"
        )
    return Path(value).expanduser()


def load_config(explicit: str | Path | None = None) -> WorkspaceConfig:
    """Read and validate a wrapper's workspace.json; apply the documented env overrides."""
    path = config_path(explicit)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"no account configuration at {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"unreadable account configuration {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    unknown = sorted(set(raw) - KEYS)
    if unknown:
        raise ConfigError(f"{path}: unknown key(s) {', '.join(unknown)}; known: {', '.join(sorted(KEYS))}")
    missing = [key for key in REQUIRED if not raw.get(key)]
    if missing:
        raise ConfigError(f"{path}: missing required key(s) {', '.join(missing)}")

    base = path.parent
    # Account and credential directory are overridable only through the variable the
    # wrapper names itself: an unconditional env override could point one account's
    # skill at another account's token.
    account = _override(raw, "account_env") or raw["account"]
    if not isinstance(account, str) or "@" not in account:
        raise ConfigError(f"{path}: account must be an email address")

    scopes = _strings(raw["scopes"], "scopes")
    # Exactly what the wrapper configured: minting must not widen a consent screen by itself.
    mint = _strings(raw["mint_scopes"], "mint_scopes") if raw.get("mint_scopes") else scopes
    config_dir = _path(base, _override(raw, "config_dir_env") or str(raw["config_dir"]))
    offline = raw.get("offline_token_file")
    if offline:
        offline = os.environ.get("GOOGLE_WORKSPACE_OFFLINE_TOKEN_FILE") or offline

    return WorkspaceConfig(
        account=account,
        config_dir=config_dir,
        scopes=scopes,
        mint_scopes=mint,
        client_env=tuple(_path(base, item) for item in _strings(raw.get("client_env", []), "client_env")),
        legacy_token=_path(base, raw["legacy_token"]) if raw.get("legacy_token") else None,
        offline_token_file=_path(base, str(offline)) if offline else None,
        cloud_token_env=bool(raw.get("cloud_token_env")),
        source=path,
    )
