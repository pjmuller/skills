"""Secret-safe credential diagnostics: `gws.py --config … doctor [--live]`.

Offline by default. It reports where the client and token come from, whether the files are
safe and complete, and the one command that fixes the first real problem. It never prints a
secret: client ids are fingerprinted, tokens are only ever described.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from . import auth as auth_module
from .config import WorkspaceConfig

CLOUD_VARS = auth_module.CLOUD_VARS
FIX = "gws.py --config {config} auth mint"


def _fingerprint(value: str | None) -> str | None:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()[:8]}" if value else None


def _symlinked(path: Path) -> bool:
    return path.is_symlink() or any(parent.is_symlink() for parent in path.parents)


def _mode(path: Path) -> tuple[str | None, bool | None]:
    if not path.exists() or _symlinked(path):
        return None, None
    bits = stat.S_IMODE(path.stat().st_mode)
    return f"{bits:04o}", bits in {0o400, 0o600}


def _client_facts(config: WorkspaceConfig) -> tuple[dict[str, Any], str | None, str | None]:
    """`MISSING` is tolerable (an offline token refreshes itself); `BROKEN` never is."""
    try:
        client = auth_module.client_credentials(config)
    except auth_module.MissingClient as exc:
        return {"source": "MISSING", "client_id": None, "error": str(exc)}, None, None
    except auth_module.AuthError as exc:
        return {"source": "BROKEN", "client_id": None, "error": str(exc)}, None, None
    return ({"source": client.source, "client_id": _fingerprint(client.client_id), "error": None},
            client.client_id, client.client_secret)


def _token_facts(config: WorkspaceConfig, client_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    kind, path = auth_module.token_source(config)
    facts: dict[str, Any] = {
        "source": kind, "path": str(path) if path else None, "mode": None, "mode_ok": None,
        "symlink": False, "has_refresh_token": False, "client_match": None,
        "missing_scopes": [], "error": None,
    }
    material: dict[str, Any] = {}
    if kind == "cloud env":
        missing = sorted(name for name in CLOUD_VARS if not os.environ.get(name))
        facts["has_refresh_token"] = not missing
        facts["error"] = f"missing variables: {', '.join(missing)}" if missing else None
        if not missing:
            material = {"refresh_token": os.environ["GWS_REFRESH_TOKEN"],
                        "client_id": os.environ["GWS_CLIENT_ID"],
                        "client_secret": os.environ["GWS_CLIENT_SECRET"]}
        return facts, material
    if kind == "none":
        return facts, material
    facts["symlink"] = _symlinked(path)
    facts["mode"], facts["mode_ok"] = _mode(path)
    if facts["symlink"]:
        facts["error"] = "credential path contains a symlink"
        return facts, material
    if kind == "offline file":
        refresh_token = path.read_text(encoding="utf-8").strip()
        facts["has_refresh_token"] = bool(refresh_token)
        material = {"refresh_token": refresh_token, "client_id": client_id}
        return facts, material
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        facts["error"] = "unreadable JSON"
        return facts, material
    scopes = document.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    facts["has_refresh_token"] = bool(document.get("refresh_token"))
    facts["missing_scopes"] = sorted(set(config.scopes) - set(scopes))
    cached = document.get("client_id") if isinstance(document.get("client_id"), str) else None
    facts["client_match"] = cached == client_id if cached and client_id else None
    material = {"refresh_token": document.get("refresh_token"),
                "client_id": cached or client_id, "client_secret": document.get("client_secret")}
    return facts, material


def _next_step(facts: dict[str, Any], config_path: str) -> str | None:
    client, token = facts["client"], facts["token"]
    fix = FIX.format(config=config_path)
    if token["source"] == "cloud env":
        return f"set all of {', '.join(CLOUD_VARS)}" if token.get("error") else None
    if client["source"] == "BROKEN":
        return client["error"]
    if token["source"] == "none":
        return f"{fix}   (no offline token yet)" if client["source"] != "MISSING" else client["error"]
    if token.get("symlink"):
        return f"replace the symlinked credential path with a regular file: {token['path']}"
    if token.get("mode_ok") is False:
        return f"chmod 600 {token['path']}"
    if token.get("error") or token.get("missing_scopes") or not token.get("has_refresh_token"):
        return f"{fix} --force"
    if token.get("client_match") is False:
        return f"{fix} --force   (the configured OAuth client differs from the cached token)"
    if client["source"] == "MISSING" and token["source"] == "offline file":
        return client["error"]
    live = facts["live"]
    if live.get("error_code") == "invalid_grant":
        return f"token revoked or expired; the account owner runs {fix} --force"
    if live.get("error_code") == "invalid_client":
        return f"client secret wrong or rotated; fix the client source ({client['source']})"
    if live.get("account_match") is False or (live.get("stage") == "identity"
                                              and live.get("http_status") in {401, 403}):
        return f"the account owner runs {fix} --force"
    return None


def _live_check(config: WorkspaceConfig, material: dict[str, Any], facts: dict[str, Any]) -> None:
    live = facts["live"]
    live["checked"] = True
    live["stage"] = "refresh"
    payload = parse.urlencode({
        "grant_type": "refresh_token", "refresh_token": material.get("refresh_token"),
        "client_id": material.get("client_id"), "client_secret": material.get("client_secret"),
    }).encode()
    try:
        with request.urlopen(request.Request(auth_module.TOKEN_URI, data=payload), timeout=30) as response:
            access_token = json.loads(response.read())["access_token"]
    except error.HTTPError as exc:
        live["http_status"] = exc.code
        if 400 <= exc.code < 500:
            try:
                code = json.loads(exc.read(4096)).get("error")
            except (OSError, ValueError):
                code = None
            live["error_code"] = code if isinstance(code, str) and code.isidentifier() else None
            live["error"] = f"refresh rejected{f': {code}' if live['error_code'] else f' (HTTP {exc.code})'}"
        else:
            live["error"] = "network or Google unavailable; retry"
        return
    except (OSError, KeyError, TypeError, ValueError, error.URLError):
        live["error"] = "network or Google unavailable; retry"
        return
    live["stage"] = "identity"
    url = (auth_module.USERINFO if config.wants_openid else auth_module.GMAIL_PROFILE)
    try:
        req = request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
        with request.urlopen(req, timeout=30) as response:
            identity = json.loads(response.read())
    except error.HTTPError as exc:
        live["http_status"] = exc.code
        live["error"] = f"identity lookup failed (HTTP {exc.code})"
        return
    except (OSError, TypeError, ValueError, error.URLError):
        live["error"] = "network or Google unavailable; retry"
        return
    actual = str(identity.get("email") or identity.get("emailAddress") or "").lower()
    live["account_match"] = actual == config.account.lower()
    if not live["account_match"]:
        live["error"] = "authorized account does not match the configured account"


def inspect(config: WorkspaceConfig, *, live: bool = False) -> dict[str, Any]:
    client, client_id, client_secret = _client_facts(config)
    token, material = _token_facts(config, client_id)
    if material.get("client_secret") is None and client_secret:
        material["client_secret"] = client_secret
    warnings = []
    if client["source"] == "MISSING" and token["source"] in ("external", "legacy"):
        warnings.append("existing token can refresh, but minting a new one needs an OAuth client")
    facts: dict[str, Any] = {
        "config": str(config.source), "account": config.account,
        "config_dir": str(config.config_dir), "client": client, "token": token,
        "warnings": warnings,
        "live": {"checked": False, "account_match": None, "stage": None, "http_status": None,
                 "error_code": None, "error": None},
        "healthy": False, "next": None,
    }
    # Same rules the auth layer enforces: a broken or disagreeing client is never healthy.
    offline_ok = (
        token["source"] != "none" and not token.get("error") and token.get("has_refresh_token")
        and token.get("mode_ok") is not False and not token.get("missing_scopes")
        and client["source"] != "BROKEN" and token.get("client_match") is not False
        and (client["source"] != "MISSING" or token["source"] in ("external", "legacy", "cloud env"))
    )
    if live and offline_ok:
        _live_check(config, material, facts)
    facts["healthy"] = bool(offline_ok and (not live or facts["live"]["account_match"] is True))
    facts["next"] = _next_step(facts, str(config.source))
    return facts


def _print(facts: dict[str, Any]) -> None:
    print(f"{facts['config']}")
    print(f"  account: {facts['account']}  ({facts['config_dir']})")
    client = facts["client"]
    print(f"  client: {client['source']}" + (f" id {client['client_id']}" if client["client_id"] else ""))
    if client["error"]:
        print(f"  client error: {client['error']}")
    token = facts["token"]
    print(f"  token: {token['source']}" + (f" ({token['path']})" if token["path"] else ""))
    if token["source"] != "none":
        print(f"  checks: mode={token['mode'] or 'n/a'} mode_ok={token['mode_ok']} "
              f"symlink={token['symlink']} refresh={token['has_refresh_token']} "
              f"client_match={token['client_match']} missing_scopes={token['missing_scopes']}")
        if token["error"]:
            print(f"  token error: {token['error']}")
    if facts["live"]["checked"]:
        print(f"  live: account_match={facts['live']['account_match']}"
              + (f" ({facts['live']['error']})" if facts["live"]["error"] else ""))
    for warning in facts["warnings"]:
        print(f"  warning: {warning}")
    print(f"  status: {'healthy' if facts['healthy'] else 'unhealthy'}")
    if facts["next"]:
        print(f"  next: {facts['next']}")


def run_doctor(config: WorkspaceConfig, *, live: bool = False, as_json: bool = False) -> int:
    facts = inspect(config, live=live)
    print(json.dumps(facts, indent=2, sort_keys=True)) if as_json else _print(facts)
    return 0 if facts["healthy"] else 1
