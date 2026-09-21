"""Credential sources, account verification and explicit consent.

Data commands never open a browser: they load an existing offline token, refresh it in
memory and verify the account before any API call. Only `auth mint` asks for consent.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials

from .config import WorkspaceConfig
from .errors import AuthError

TOKEN_URI = "https://oauth2.googleapis.com/token"
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL_PROFILE = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
CLIENT_VARS = ("GOOGLE_WORKSPACE_CLIENT_ID", "GOOGLE_WORKSPACE_CLIENT_SECRET")
CLOUD_VARS = ("GWS_REFRESH_TOKEN", "GWS_CLIENT_ID", "GWS_CLIENT_SECRET")
REAUTH = "run `gws.py --config <workspace.json> auth mint [--force]`"
OAUTH_ERROR = re.compile(r"^[a-z_]{1,40}$")


class MissingClient(AuthError):
    """No OAuth client is configured anywhere. A usable token can still refresh itself."""


@dataclass(frozen=True)
class ClientCredentials:
    client_id: str
    client_secret: str
    source: str


# --- filesystem safety ------------------------------------------------------

def _check_path(path: Path) -> None:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise AuthError(f"credential path must not contain symlinks: {path}")


def _secure(config: WorkspaceConfig) -> None:
    _check_path(config.config_dir)
    if config.config_dir.exists():
        config.config_dir.chmod(0o700)
    for path in (config.client_path, config.token_path):
        _check_path(path)
        if path.exists():
            path.chmod(0o600)


def write_secret(path: Path, content: str) -> None:
    """Atomically write an owner-only file inside an owner-only directory."""
    _check_path(path)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


# --- OAuth client -----------------------------------------------------------

def _from_env(values, source: str) -> ClientCredentials | None:
    client_id, secret = (values.get(name) for name in CLIENT_VARS)
    if client_id and secret:
        return ClientCredentials(str(client_id), str(secret), source)
    if client_id or secret:
        # Half a pair from one source silently mixed with the other's is how accounts get crossed.
        missing = ", ".join(name for name, value in zip(CLIENT_VARS, (client_id, secret)) if not value)
        raise AuthError(f"{source} sets only part of the OAuth client; missing {missing}")
    return None


def _from_client_json(path: Path) -> ClientCredentials | None:
    _check_path(path)
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        section = document.get("installed") or document.get("web")
        client_id, secret = section["client_id"], section["client_secret"]
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise AuthError(f"unusable OAuth client at {path} ({type(exc).__name__})") from exc
    if not isinstance(client_id, str) or not isinstance(secret, str):
        raise AuthError(f"unusable OAuth client at {path}: non-string fields")
    return ClientCredentials(client_id, secret, f"client.json ({path})")


def client_credentials(config: WorkspaceConfig) -> ClientCredentials:
    """Environment, then the wrapper's client env file(s), then <config_dir>/client.json."""
    found = _from_env(os.environ, "environment")
    if found:
        return found
    for env_file in config.client_env:
        if env_file.is_file():
            from dotenv import dotenv_values

            found = _from_env(dotenv_values(env_file), f"env file ({env_file})")
            if found:
                return found
    found = _from_client_json(config.client_path)
    if found:
        return found
    checked = ", ".join(str(path) for path in (*config.client_env, config.client_path))
    raise MissingClient(
        f"no OAuth client for {config.account}: set {' and '.join(CLIENT_VARS)} together, "
        f"or place an installed-app client.json at {config.client_path} (checked {checked})"
    )


# --- token ------------------------------------------------------------------

def _endpoint(url: str) -> str:
    """The URL without its query string: a query can carry the access token."""
    return url.split("?", 1)[0]


def _call(method: str, url: str, **kw) -> dict:
    """One OAuth/identity call whose failures never quote a URL, body or exception text.

    Uses `requests` (not httpx) so a caller importing only the auth layer keeps working.
    """
    import requests

    try:
        response = requests.request(method, url, timeout=30, **kw)
    except requests.RequestException:
        # The exception text can contain the prepared URL, and that can carry a token.
        raise AuthError(f"could not reach {_endpoint(url)}; check the network") from None
    if response.status_code >= 400:
        raise AuthError(f"{_endpoint(url)} refused the request (HTTP {response.status_code})")
    try:
        payload = response.json()
    except ValueError:
        raise AuthError(f"{_endpoint(url)} returned an unreadable response") from None
    if not isinstance(payload, dict):
        raise AuthError(f"{_endpoint(url)} returned an unexpected response")
    return payload


def _get(url: str, token: str) -> dict:
    return _call("GET", url, headers={"Authorization": f"Bearer {token}"})


def account_for_token(config: WorkspaceConfig, token: str) -> str:
    """Old Gmail-only tokens carry no OpenID scope; identify them via the Gmail profile."""
    if config.wants_openid:
        return str(_get(USERINFO, token).get("email", "")).lower()
    return str(_get(GMAIL_PROFILE, token).get("emailAddress", "")).lower()


def granted_scopes(token: str) -> set[str]:
    # POST, so the access token travels in the body instead of a loggable query string.
    return set(str(_call("POST", TOKENINFO, data={"access_token": token}).get("scope", "")).split())


def verify_account(config: WorkspaceConfig, credentials: Credentials) -> str:
    actual = account_for_token(config, credentials.token)
    if actual != config.account.lower():
        raise AuthError(f"authorized as {actual or 'unknown'}, expected {config.account}")
    return actual


def refresh(credentials: Credentials) -> None:
    """Refresh directly, so the auth layer needs no google-auth transport extra."""
    import requests

    url = credentials.token_uri or TOKEN_URI
    data = {
        "grant_type": "refresh_token",
        "refresh_token": credentials.refresh_token,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
    }
    try:
        response = requests.post(url, timeout=30, data=data)
    except requests.RequestException:
        raise AuthError(f"could not reach {_endpoint(url)} to refresh the token") from None
    if response.status_code >= 400:
        # Status plus Google's short error code only: the response body is never echoed.
        raise AuthError(f"token refresh failed (HTTP {response.status_code}"
                        f"{_oauth_error(response)}); {REAUTH}")
    try:
        payload = response.json()
        access_token = payload["access_token"]
    except (ValueError, KeyError, TypeError):
        raise AuthError(f"{_endpoint(url)} returned no usable access token; {REAUTH}") from None
    credentials.token = access_token
    # google-auth compares expiry against a naive UTC clock
    credentials.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=int(payload.get("expires_in", 3600))
    )


def _oauth_error(response) -> str:
    """Google's short error code, if the untrusted body carries a plausible one."""
    try:
        code = response.json().get("error")
    except (ValueError, AttributeError):
        return ""
    return f": {code}" if isinstance(code, str) and OAUTH_ERROR.fullmatch(code) else ""


def _cloud_credentials(config: WorkspaceConfig) -> Credentials | None:
    """Cloud runners pass the offline token as env vars; only opted-in wrappers accept it."""
    if not config.cloud_token_env:
        return None
    present = {name for name in CLOUD_VARS if os.environ.get(name)}
    if not present:
        return None
    if present != set(CLOUD_VARS):
        raise AuthError(f"set all of {', '.join(CLOUD_VARS)} (or none)")
    return Credentials(
        None,
        refresh_token=os.environ["GWS_REFRESH_TOKEN"],
        client_id=os.environ["GWS_CLIENT_ID"],
        client_secret=os.environ["GWS_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
    )


def _cached_credentials(config: WorkspaceConfig, path: Path) -> Credentials:
    _check_path(path)
    try:
        credentials = Credentials.from_authorized_user_file(str(path))
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError(f"unreadable token cache {path} ({type(exc).__name__}); {REAUTH}") from exc
    missing = set(config.scopes) - set(credentials.scopes or [])
    if missing:
        raise AuthError(f"token at {path} is missing required scopes: {', '.join(sorted(missing))}; {REAUTH}")
    if not credentials.refresh_token:
        raise AuthError(f"token at {path} is not offline-capable; {REAUTH}")
    return credentials


def _offline_file_credentials(config: WorkspaceConfig) -> Credentials | None:
    path = config.offline_token_file
    if not path:
        return None
    _check_path(path)
    if not path.is_file():
        return None
    refresh_token = path.read_text(encoding="utf-8").strip()
    if not refresh_token:
        return None
    client = client_credentials(config)
    return Credentials(
        None, refresh_token=refresh_token, token_uri=TOKEN_URI,
        client_id=client.client_id, client_secret=client.client_secret, scopes=list(config.scopes),
    )


def token_source(config: WorkspaceConfig) -> tuple[str, Path | None]:
    """Where this config's offline token comes from. Shared with `doctor` so they cannot drift."""
    if config.cloud_token_env and any(os.environ.get(name) for name in CLOUD_VARS):
        return "cloud env", None
    if config.token_path.exists():
        return "external", config.token_path
    if config.legacy_token and config.legacy_token.exists():
        return "legacy", config.legacy_token  # readable in place; refreshes externalize
    if config.offline_token_file and config.offline_token_file.is_file():
        return "offline file", config.offline_token_file
    return "none", None


def credentials(config: WorkspaceConfig) -> Credentials:
    """Verified, refreshed credentials for the configured account. Never opens a browser."""
    cloud = _cloud_credentials(config)
    if cloud is not None:
        refresh(cloud)
        verify_account(config, cloud)
        return cloud

    _secure(config)
    kind, source = token_source(config)
    cached_client = None
    if source is not None and kind in ("external", "legacy"):
        creds = _cached_credentials(config, source)
        cached_client = creds.client_id
    else:
        creds = _offline_file_credentials(config)
    if creds is None:
        raise AuthError(f"no offline token for {config.account} at {config.token_path}; {REAUTH}")
    changed = not creds.valid
    if changed:
        refresh(creds)
    verify_account(config, creds)
    if cached_client:
        _check_client_match(config, cached_client)
    if changed:
        write_secret(config.token_path, creds.to_json() + "\n")
    return creds


def _check_client_match(config: WorkspaceConfig, cached_client: str) -> None:
    """A configured client that disagrees with the cached token is refused, not warned about.

    Only a completely absent client is tolerated: an existing offline token carries its own
    client and can refresh. A partial or unusable client source still raises.
    """
    try:
        configured = client_credentials(config).client_id
    except MissingClient:
        return
    if configured != cached_client:
        raise AuthError(
            "the configured OAuth client differs from the cached token's client; "
            f"{REAUTH} with --force, or point this wrapper at the matching client")


def access_token(config: WorkspaceConfig) -> str:
    return credentials(config).token


# --- explicit consent and provisioning --------------------------------------

def mint(config: WorkspaceConfig, *, force: bool = False, port: int = 0) -> dict:
    """Interactive consent for the configured account. Saves nothing unless every check passes."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    _secure(config)
    if config.token_path.exists() and not force:
        raise AuthError(f"{config.token_path} exists; pass --force to replace it")
    client = client_credentials(config)
    if not port:
        import socket

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
    flow = InstalledAppFlow.from_client_config(
        {"installed": {
            "client_id": client.client_id, "client_secret": client.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": TOKEN_URI,
            "redirect_uris": [f"http://localhost:{port}/"],
        }},
        list(config.mint_scopes),
    )
    flow.redirect_uri = f"http://localhost:{port}/"
    # run_local_server mints its own OAuth state; a separately built authorization_url would
    # fail the CSRF check on callback. Let it print the URL itself.
    creds = flow.run_local_server(
        port=port, open_browser=False, timeout_seconds=1800,
        authorization_prompt_message=(
            f"Open this URL in a browser logged in as {config.account} and approve all scopes:"
            "\n\n{url}\n"
        ),
        access_type="offline", prompt="consent", login_hint=config.account,
    )
    if not creds.token or not creds.refresh_token:
        raise AuthError("Google returned no offline credentials; nothing saved")
    verify_account(config, creds)
    missing = sorted(set(config.mint_scopes) - granted_scopes(creds.token) - {"openid"})
    if missing:
        raise AuthError(f"scopes not granted: {', '.join(missing)}; nothing saved — redo and tick every box")
    write_secret(config.token_path, creds.to_json() + "\n")
    return {"token": str(config.token_path), "account": config.account,
            "client": client.source, "offline": True}


def configure(config: WorkspaceConfig, client_env: str | Path, *, force: bool = False) -> dict:
    """Import an installed-app OAuth client from a local .env into <config_dir>/client.json."""
    from dotenv import dotenv_values

    _secure(config)
    if config.client_path.exists() and not force:
        raise AuthError(f"{config.client_path} exists; pass --force to replace it")
    values = dotenv_values(Path(client_env).expanduser())
    client_id = values.get("GOOGLE_WORKSPACE_CLIENT_ID") or values.get("GOOGLE_CLIENT_ID")
    secret = (values.get("GOOGLE_WORKSPACE_CLIENT_SECRET") or values.get("GOOGLE_CLIENT_SECRET")
              or values.get("GOOGLE_SECRET_KEY"))
    if not client_id or not secret:
        raise AuthError("client env needs a supported Google client ID/secret pair")
    document = {"installed": {
        "client_id": client_id, "client_secret": secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": TOKEN_URI,
        "redirect_uris": ["http://localhost"],
    }}
    write_secret(config.client_path, json.dumps(document, indent=2) + "\n")
    return {"configured": str(config.client_path), "account": config.account}


def export_env(config: WorkspaceConfig) -> dict[str, str]:
    """Cloud provisioning triplet. The caller is responsible for never logging it."""
    _check_path(config.token_path)
    try:
        document = json.loads(config.token_path.read_text(encoding="utf-8"))
        return {"GWS_CLIENT_ID": document["client_id"],
                "GWS_CLIENT_SECRET": document["client_secret"],
                "GWS_REFRESH_TOKEN": document["refresh_token"]}
    except (OSError, KeyError, ValueError) as exc:
        raise AuthError(f"no exportable offline token at {config.token_path} ({exc}); {REAUTH}") from exc


def export_token(config: WorkspaceConfig, destination: Path) -> Path:
    """Write only the refresh token, owner-only, when the user explicitly asked for it."""
    creds = credentials(config)
    destination = Path(destination).expanduser()
    write_secret(destination, creds.refresh_token + "\n")
    return destination
