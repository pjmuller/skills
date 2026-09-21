"""Reusable Google Workspace core: one config shape, one command set, one client API.

    sys.path.insert(0, "<core>/scripts")
    from gws_core import load_config, Workspace
    with Workspace(load_config("<wrapper>/workspace.json")) as ws:
        ws.gmail.search("newer_than:1d")

Only `config`/`errors` are imported eagerly; everything else is loaded on first use so a
caller that needs `credentials` alone does not pay for httpx or the OAuth consent stack.
"""

from __future__ import annotations

from .config import WorkspaceConfig, config_path, load_config
from .errors import ApiError, AuthError, ConfigError, WorkspaceError

__all__ = [
    "ApiError", "AuthError", "ConfigError", "WorkspaceConfig", "WorkspaceError", "Workspace",
    "Session", "access_token", "config_path", "credentials", "load_config", "main",
]

_LAZY = {
    "Session": ("session", "Session"),
    "Workspace": ("session", "Workspace"),
    "credentials": ("auth", "credentials"),
    "access_token": ("auth", "access_token"),
    "main": ("cli", "main"),
}


def __getattr__(name: str):
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module, attribute = _LAZY[name]
    return getattr(importlib.import_module(f".{module}", __name__), attribute)


def __dir__() -> list[str]:
    return sorted(__all__)
