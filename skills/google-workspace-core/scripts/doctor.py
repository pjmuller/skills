#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["python-dotenv>=1.0.0"]
# ///
"""Secret-safe, offline-first diagnostics for Google Workspace wrappers."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from dotenv import dotenv_values

CLIENT_VARS = ("GOOGLE_WORKSPACE_CLIENT_ID", "GOOGLE_WORKSPACE_CLIENT_SECRET")
CLOUD_VARS = ("GWS_REFRESH_TOKEN", "GWS_CLIENT_ID", "GWS_CLIENT_SECRET")
TOKEN_URI = "https://oauth2.googleapis.com/token"
OAUTH_ERROR = re.compile(r"^[a-z_]{1,40}$")


@dataclass
class Inspection:
    facts: dict[str, Any]
    refresh_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_uri: str = TOKEN_URI
    identity_url: str = "https://openidconnect.googleapis.com/v1/userinfo"


def _fingerprint(value: str | None) -> str | None:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()[:8]}" if value else None


def _symlinked(path: Path, strict: bool = True) -> bool:
    parents = path.parents if strict else path.parents[:1]
    return path.is_symlink() or any(parent.is_symlink() for parent in parents)


def _mode(path: Path, strict: bool = True) -> tuple[str | None, bool | None]:
    if not path.exists() or _symlinked(path, strict):
        return None, None
    bits = stat.S_IMODE(path.stat().st_mode)
    return f"{bits:04o}", bits in {0o400, 0o600}


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None, "not an object"
        return value, None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "unreadable JSON"


def _has_workspace_config(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return False
    return any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "WORKSPACE_CONFIG"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        for node in tree.body
    )


def _load_config(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    selected: list[ast.stmt] = []
    found = False
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            selected.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "WORKSPACE_CONFIG" for target in targets):
                selected.append(node)
                found = True
    if not found:
        raise ValueError("WORKSPACE_CONFIG assignment not found")
    namespace: dict[str, Any] = {"__file__": str(path), "__name__": "workspace_doctor_config"}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    config = namespace.get("WORKSPACE_CONFIG")
    if not isinstance(config, dict):
        raise ValueError("WORKSPACE_CONFIG is not a dict")
    return config


def _resolve_wrapper(value: str | Path) -> tuple[Path, Path]:
    path = Path(value).expanduser()
    if path.is_file():
        config_path = path
        scripts = path.parent
    else:
        scripts = path if path.name == "scripts" else path / "scripts"
        config_path = scripts / "workspace_config.py"
        if not config_path.is_file():
            candidates = [scripts / name for name in ("google_workspace.py", "gmail_cli.py")]
            candidates += sorted(scripts.glob("*.py"))
            config_path = next((item for item in candidates if item.is_file() and _has_workspace_config(item)), config_path)
    return config_path.resolve(), scripts.resolve()


def _discover() -> list[tuple[Path, Path]]:
    core = Path(__file__).resolve().parents[1]
    skill_root = core.parent
    repo = skill_root.parent.parent if skill_root.parent.name in {".agents", ".claude"} else skill_root.parent
    roots = [core.parent, repo / ".claude/skills", repo / ".agents/skills"]
    found: dict[Path, tuple[Path, Path]] = {}
    for root in roots:
        for path in root.glob("*/scripts/workspace_config.py"):
            config, scripts = _resolve_wrapper(path)
            found.setdefault(config, (config, scripts))
    return list(found.values())


def _command_script(scripts: Path, interface: str, config_path: Path) -> Path:
    if config_path.name != "workspace_config.py":
        return config_path
    names = ("gws_auth.py",) if interface == "REST" else ("google_workspace.py", "gmail_cli.py")
    return next((scripts / name for name in names if (scripts / name).is_file()), scripts / names[0])


def _client_json(path: Path, *, allow_web: bool = False, strict_symlinks: bool = True) -> tuple[str | None, str | None, str | None]:
    if not path.exists():
        return None, None, None
    if _symlinked(path, strict_symlinks):
        return None, None, "symlinked"
    data, invalid = _read_json(path)
    if invalid:
        return None, None, invalid
    section = data.get("installed") or (data.get("web") if allow_web else None)
    if not isinstance(section, dict):
        return None, None, "missing installed/web client" if allow_web else "missing installed client"
    client_id, secret = section.get("client_id"), section.get("client_secret")
    if not isinstance(client_id, str) or not isinstance(secret, str) or not client_id or not secret:
        return None, None, "missing client fields"
    return client_id, secret, None


def _modular_client(config: dict[str, Any], scripts: Path, config_dir: Path) -> tuple[dict[str, Any], str | None, str | None]:
    env_path = scripts.parents[3] / ".env" if config.get("repo_env") else scripts / config.get("env_file", ".env")
    candidates: list[tuple[str, Path | None, dict[str, Any]]] = [
        ("environment", None, os.environ),
        ("repo .env path" if config.get("repo_env") else "wrapper .env path", env_path, dotenv_values(env_path) if env_path.is_file() else {}),
    ]
    incomplete: set[str] = set()
    for source, path, values in candidates:
        client_id, secret = (values.get(name) for name in CLIENT_VARS)
        if client_id and secret:
            return {"source": source, "path": str(path) if path else None, "client_id": _fingerprint(str(client_id)), "error": None}, str(client_id), str(secret)
        if client_id or secret:
            incomplete.update(name for name, value in zip(CLIENT_VARS, (client_id, secret)) if not value)
    client_path = config_dir / "client.json"
    client_id, secret, invalid = _client_json(client_path, allow_web=True)
    if client_id and secret:
        return {"source": "external client.json", "path": str(client_path), "client_id": _fingerprint(client_id), "error": None}, client_id, secret
    missing = sorted(incomplete or CLIENT_VARS)
    error_text = invalid or f"missing variables: {', '.join(missing)}"
    return {"source": "MISSING", "path": str(client_path), "env_path": str(env_path), "missing_variables": missing, "error": error_text}, None, None


def _file_client(config_dir: Path) -> tuple[dict[str, Any], str | None, str | None]:
    path = config_dir / "client.json"
    client_id, secret, invalid = _client_json(path, strict_symlinks=False)
    if client_id and secret:
        return {"source": "external client.json", "path": str(path), "client_id": _fingerprint(client_id), "error": None}, client_id, secret
    return {"source": "MISSING", "path": str(path), "missing_variables": [], "error": invalid or "missing client.json"}, None, None


def _token_file(path: Path, source: str, required_scopes: set[str], configured_client: str | None, *, strict_symlinks: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    mode, mode_ok = _mode(path, strict_symlinks)
    public: dict[str, Any] = {"source": source, "path": str(path), "exists": True, "mode": mode, "mode_ok": mode_ok, "symlink": _symlinked(path, strict_symlinks), "has_refresh_token": False, "client_match": None, "missing_scopes": [], "error": None}
    if public["symlink"]:
        public["error"] = "credential path contains a symlink"
        return public, {}
    data, invalid = _read_json(path)
    if invalid:
        public["error"] = invalid
        return public, {}
    scopes = data.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    public["has_refresh_token"] = bool(data.get("refresh_token"))
    public["missing_scopes"] = sorted(required_scopes - set(scopes))
    cached_client = data.get("client_id") if isinstance(data.get("client_id"), str) else None
    public["client_match"] = cached_client == configured_client if cached_client and configured_client else None
    return public, data


def _next_for(facts: dict[str, Any], command: Path) -> str | None:
    client, token = facts["client"], facts["token"]
    if token["source"] == "cloud env" and token.get("error"):
        return f"set all of {', '.join(CLOUD_VARS)}"
    if client["source"] == "MISSING":
        rest_token_works = facts["interface"] == "REST" and token["source"] == "external" and not token.get("error") and token.get("mode_ok") is not False and token.get("has_refresh_token") and not token.get("missing_scopes")
        if rest_token_works:
            return None
        if client.get("error") == "symlinked":
            return f"replace the symlinked client with a regular file: {client['path']}"
        if facts["interface"] == "modular" and client.get("missing_variables"):
            mise = f"if mise or a shell env file supplies them, run from the repo root via mise exec -- uv run --script {Path(__file__).resolve()} {facts['wrapper']}"
            return f"checked {client['env_path']}; set {', '.join(CLIENT_VARS)} together, or place client.json at {client['path']}; {mise}"
        if facts["interface"] == "readonly":
            return f"uv run --script {command} configure --client-env <oauth-client.env>"
        return f"place client.json at {client['path']}"
    if token.get("symlink"):
        return f"replace the symlinked credential path with a regular file: {token['path']}"
    if token.get("mode_ok") is False:
        return f"chmod 600 {token['path']}"
    if token.get("exists") is False:
        return f"uv run --script {command} auth" if facts["interface"] != "REST" else f"uv run --script {command}"
    client_mismatch = token.get("client_match") is False and facts["interface"] != "REST"
    force = token.get("error") or client_mismatch or token.get("missing_scopes") or not token.get("has_refresh_token")
    if token["source"] == "none":
        force = False
    if token["source"] == "none" or force:
        suffix = " --force" if force else ""
        if facts["interface"] == "REST":
            return f"uv run --script {command}{suffix}"
        return f"uv run --script {command} auth{suffix}"
    live = facts.get("live", {})
    if live.get("account_match") is False:
        action = " --force" if facts["interface"] == "REST" else " auth --force"
        return f"uv run --script {command}{action}"
    if live.get("error_code") == "invalid_grant":
        action = " --force" if facts["interface"] == "REST" else " auth --force"
        return f"token revoked or expired; account owner runs uv run --script {command}{action}"
    if live.get("error_code") == "invalid_client":
        location = f" at {client['path']}" if client.get("path") else ""
        return f"client secret wrong or rotated; fix client source {client['source']}{location}"
    if live.get("stage") == "identity" and live.get("http_status") in {401, 403}:
        action = " --force" if facts["interface"] == "REST" else " auth --force"
        return f"account owner runs uv run --script {command}{action}"
    return None


def inspect_wrapper(config_path: Path, scripts: Path, live: bool = False) -> Inspection:
    config = _load_config(config_path)
    interface = "REST" if {"mint_scopes", "required_scopes"} & config.keys() else "modular" if {"env_file", "legacy_token", "repo_env"} & config.keys() else "readonly"
    config_dir = Path(os.environ.get("GWS_CONFIG_DIR") or config["config_dir"]).expanduser() if interface == "REST" else Path(config["config_dir"]).expanduser()
    expected = os.environ.get("GWS_EXPECTED_EMAIL") or config.get("expected_email") if interface == "REST" else config.get("expected_email")
    required_scopes = set(config.get("required_scopes") or config.get("scopes") or [])
    materials: dict[str, Any] = {}

    cloud = {name: os.environ.get(name) for name in CLOUD_VARS}
    if interface == "REST" and any(cloud.values()):
        missing = sorted(name for name, value in cloud.items() if not value)
        client = {"source": "cloud env" if not missing else "MISSING", "path": None, "client_id": _fingerprint(cloud["GWS_CLIENT_ID"]), "missing_variables": missing, "error": f"missing variables: {', '.join(missing)}" if missing else None}
        token = {"source": "cloud env", "path": None, "exists": None, "mode": None, "mode_ok": None, "symlink": False, "has_refresh_token": bool(cloud["GWS_REFRESH_TOKEN"]), "client_match": True if not missing else None, "missing_scopes": [], "error": client["error"]}
        if not missing:
            materials = {"refresh_token": cloud["GWS_REFRESH_TOKEN"], "client_id": cloud["GWS_CLIENT_ID"], "client_secret": cloud["GWS_CLIENT_SECRET"], "token_uri": TOKEN_URI}
    else:
        if interface == "modular":
            client, client_id, secret = _modular_client(config, scripts, config_dir)
        else:
            client, client_id, secret = _file_client(config_dir)
        token_path = config_dir / "token.json"
        source = "external"
        if not token_path.exists() and interface == "modular" and config.get("legacy_token"):
            token_path, source = scripts / config["legacy_token"], "legacy"
        if token_path.exists() or token_path.is_symlink():
            token, materials = _token_file(token_path, source, required_scopes, client_id, strict_symlinks=interface == "modular")
        elif interface == "modular" and config.get("offline_token_file"):
            token_path = Path(os.environ.get("GOOGLE_WORKSPACE_OFFLINE_TOKEN_FILE") or config["offline_token_file"]).expanduser()
            mode, mode_ok = _mode(token_path)
            symlink = _symlinked(token_path)
            exists = token_path.is_file() and not symlink
            refresh = token_path.read_text(encoding="utf-8").strip() if exists else None
            token = {"source": "offline-file", "path": str(token_path), "exists": exists, "mode": mode, "mode_ok": mode_ok, "symlink": symlink, "has_refresh_token": bool(refresh), "client_match": None, "missing_scopes": [], "error": "credential path contains a symlink" if symlink else None}
            materials = {"refresh_token": refresh, "client_id": client_id, "client_secret": secret, "token_uri": TOKEN_URI}
        else:
            token = {"source": "none", "path": str(config_dir / "token.json"), "exists": False, "mode": None, "mode_ok": None, "symlink": False, "has_refresh_token": False, "client_match": None, "missing_scopes": [], "error": None}
        if not materials.get("client_id"):
            materials["client_id"] = client_id
        if not materials.get("client_secret"):
            materials["client_secret"] = secret

    identity_url = "https://gmail.googleapis.com/gmail/v1/users/me/profile" if interface == "modular" and "https://www.googleapis.com/auth/userinfo.email" not in required_scopes else "https://openidconnect.googleapis.com/v1/userinfo"
    command = _command_script(scripts, interface, config_path)
    warnings = []
    if interface == "REST" and client["source"] == "MISSING":
        warnings.append("existing token can work, but mint/reauth needs client.json")
    if interface == "REST" and token.get("client_match") is False:
        warnings.append("cached client differs; existing token can work, but reauth uses client.json")
    facts: dict[str, Any] = {"wrapper": str(scripts.parent), "config": str(config_path), "interface": interface, "expected_account": expected, "client": client, "token": token, "warnings": warnings, "live": {"checked": False, "account_match": None, "stage": None, "http_status": None, "error_code": None, "error": None}, "healthy": False, "next": None}
    client_ok = client["source"] != "MISSING" or (interface == "REST" and token["source"] == "external")
    client_match_ok = token.get("client_match") is not False or interface == "REST"
    offline_ok = bool(expected) and client_ok and token["source"] != "none" and not token.get("error") and token.get("mode_ok") is not False and token.get("has_refresh_token") and client_match_ok and not token.get("missing_scopes")
    inspection = Inspection(facts, identity_url=identity_url, **{key: materials.get(key) for key in ("refresh_token", "client_id", "client_secret", "token_uri") if materials.get(key) is not None})
    if live and offline_ok:
        _live_check(inspection, str(expected or ""))
    facts["healthy"] = bool(offline_ok and (not live or facts["live"]["account_match"] is True))
    facts["next"] = _next_for(facts, command)
    return inspection


def _oauth_error_code(response: error.HTTPError) -> str | None:
    try:
        value = json.loads(response.read(4096)).get("error")
    except (AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, str) and OAUTH_ERROR.fullmatch(value) else None


def _live_check(inspection: Inspection, expected: str) -> None:
    live = inspection.facts["live"]
    live["checked"] = True
    live["stage"] = "refresh"
    payload = parse.urlencode({"grant_type": "refresh_token", "refresh_token": inspection.refresh_token, "client_id": inspection.client_id, "client_secret": inspection.client_secret}).encode()
    try:
        with request.urlopen(request.Request(inspection.token_uri, data=payload), timeout=30) as response:
            access_token = json.loads(response.read())["access_token"]
    except error.HTTPError as exc:
        live["http_status"] = exc.code
        if 400 <= exc.code < 500:
            live["error_code"] = _oauth_error_code(exc)
            suffix = f": {live['error_code']}" if live["error_code"] else f" (HTTP {exc.code})"
            live["error"] = f"refresh rejected{suffix}"
        else:
            live["error"] = "network or Google unavailable; retry"
        return
    except (OSError, KeyError, TypeError, ValueError, error.URLError):
        live["error"] = "network or Google unavailable; retry"
        return

    live["stage"] = "identity"
    try:
        req = request.Request(inspection.identity_url, headers={"Authorization": f"Bearer {access_token}"})
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
    live["account_match"] = actual == expected.lower()
    if not live["account_match"]:
        live["error"] = "authorized account does not match expected account"


def _failure(path: Path, message: str) -> Inspection:
    return Inspection({"wrapper": str(path), "config": str(path), "interface": None, "expected_account": None, "client": {"source": "MISSING", "error": message}, "token": {"source": "none"}, "warnings": [], "live": {"checked": False, "account_match": None, "stage": None, "http_status": None, "error_code": None, "error": None}, "healthy": False, "next": f"fix wrapper configuration at {path}"})


def _print_text(facts: dict[str, Any]) -> None:
    print(f"{facts['wrapper']} [{facts.get('interface') or 'unknown'}]")
    print(f"  expected account: {facts.get('expected_account') or 'MISSING'}")
    client = facts["client"]
    print(f"  client: {client.get('source')}" + (f" ({client['path']})" if client.get("path") else "") + (f" id {client['client_id']}" if client.get("client_id") else ""))
    if client.get("error"):
        print(f"  client error: {client['error']}")
    token = facts["token"]
    print(f"  token: {token.get('source')}" + (f" ({token['path']})" if token.get("path") else ""))
    if token.get("source") != "none":
        print(f"  checks: mode={token.get('mode') or 'n/a'} mode_ok={token.get('mode_ok')} symlink={token.get('symlink')} refresh={token.get('has_refresh_token')} client_match={token.get('client_match')} missing_scopes={token.get('missing_scopes', [])}")
        if token.get("error"):
            print(f"  token error: {token['error']}")
    if facts["live"]["checked"]:
        print(f"  live: account_match={facts['live']['account_match']}" + (f" ({facts['live']['error']})" if facts['live']['error'] else ""))
    for warning in facts.get("warnings", []):
        print(f"  warning: {warning}")
    print(f"  status: {'healthy' if facts['healthy'] else 'unhealthy'}")
    if facts["next"]:
        print(f"  next: {facts['next']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrappers", nargs="*", metavar="WRAPPER")
    parser.add_argument("--live", action="store_true", help="refresh in memory and verify account after offline checks pass")
    parser.add_argument("--json", action="store_true", help="emit the same redacted facts as JSON")
    args = parser.parse_args(argv)
    targets = [_resolve_wrapper(value) for value in args.wrappers] if args.wrappers else _discover()
    reports: list[Inspection] = []
    if not targets:
        reports.append(_failure(Path.cwd(), "no wrappers discovered"))
    for config_path, scripts in targets:
        try:
            reports.append(inspect_wrapper(config_path, scripts, args.live))
        except Exception:
            reports.append(_failure(config_path, "wrapper configuration could not be loaded"))
    if args.json:
        print(json.dumps({"wrappers": [report.facts for report in reports]}, indent=2, sort_keys=True))
    else:
        for index, report in enumerate(reports):
            if index:
                print()
            _print_text(report.facts)
    return 0 if reports and all(report.facts["healthy"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
