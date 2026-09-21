"""Explicitly configured offline OAuth for compatibility Workspace clients.

Executed in a repo-local auth module, whose WORKSPACE_CONFIG defines its account
boundary. Data access never starts browser consent. Legacy caches are read in place;
refreshes go to the configured external cache, never to an installed core copy.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import requests
from dotenv import dotenv_values
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

EXPECTED_EMAIL = WORKSPACE_CONFIG["expected_email"].lower()
CONFIG_DIR = Path(WORKSPACE_CONFIG["config_dir"]).expanduser()
TOKEN_PATH = CONFIG_DIR / "token.json"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = list(WORKSPACE_CONFIG["scopes"])
_LOCAL_SCRIPTS = Path(__file__).resolve().parent
REPO_ENV = _LOCAL_SCRIPTS.parents[3] / ".env"
_ENV_PATH = REPO_ENV if WORKSPACE_CONFIG.get("repo_env") else _LOCAL_SCRIPTS / WORKSPACE_CONFIG.get("env_file", ".env")
_LEGACY_TOKEN = _LOCAL_SCRIPTS / WORKSPACE_CONFIG["legacy_token"] if WORKSPACE_CONFIG.get("legacy_token") else None
OFFLINE_TOKEN_FILE = Path(os.environ.get("GOOGLE_WORKSPACE_OFFLINE_TOKEN_FILE") or WORKSPACE_CONFIG.get("offline_token_file") or "__unused_offline_token__").expanduser()


def _client_credentials() -> tuple[str, str]:
    values = dotenv_values(_ENV_PATH) if _ENV_PATH.exists() else {}
    client_id = os.environ.get("GOOGLE_WORKSPACE_CLIENT_ID") or values.get("GOOGLE_WORKSPACE_CLIENT_ID")
    secret = os.environ.get("GOOGLE_WORKSPACE_CLIENT_SECRET") or values.get("GOOGLE_WORKSPACE_CLIENT_SECRET")
    if not client_id or not secret:
        sys.exit("error: GOOGLE_WORKSPACE_CLIENT_ID / GOOGLE_WORKSPACE_CLIENT_SECRET must be set (environment or wrapper .env)")
    return client_id, secret


_client_creds = _client_credentials


def _client_config() -> dict:
    client_id, secret = _client_credentials()
    return {"installed": {"client_id": client_id, "client_secret": secret,
                          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                          "token_uri": TOKEN_URI, "redirect_uris": ["http://localhost"]}}


def _check_path(path: Path) -> None:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        sys.exit(f"error: credential path must not contain symlinks: {path}")


def _secure_existing_credentials() -> None:
    _check_path(TOKEN_PATH)
    if CONFIG_DIR.exists():
        CONFIG_DIR.chmod(0o700)
    if TOKEN_PATH.exists():
        TOKEN_PATH.chmod(0o600)


def _write_secret(path: Path, content: str) -> None:
    _check_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent == CONFIG_DIR:
        path.parent.chmod(0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _email_for_token(token: str) -> str:
    # Old Gmail-only tokens have no OpenID scope; do not demand new consent.
    use_openid = "https://www.googleapis.com/auth/userinfo.email" in SCOPES
    url = "https://openidconnect.googleapis.com/v1/userinfo" if use_openid else "https://gmail.googleapis.com/gmail/v1/users/me/profile"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    return str(response.json().get("email" if use_openid else "emailAddress", "")).lower()


def _granted_scopes_for_token(token: str) -> set[str]:
    response = requests.post("https://oauth2.googleapis.com/tokeninfo", data={"access_token": token}, timeout=30)
    response.raise_for_status()
    return set(str(response.json().get("scope", "")).split())


def _verify_account(credentials: Credentials) -> None:
    email = _email_for_token(credentials.token)
    if email != EXPECTED_EMAIL:
        sys.exit(f"error: authorized as {email or 'unknown'}, expected {EXPECTED_EMAIL}; nothing saved")


def _from_offline_file(client_id: str, client_secret: str) -> Credentials | None:
    if not WORKSPACE_CONFIG.get("offline_token_file"):
        return None
    _check_path(OFFLINE_TOKEN_FILE)
    if not OFFLINE_TOKEN_FILE.exists():
        return None
    refresh_token = OFFLINE_TOKEN_FILE.read_text().strip()
    if not refresh_token:
        return None
    credentials = Credentials(token=None, refresh_token=refresh_token, token_uri=TOKEN_URI,
                              client_id=client_id, client_secret=client_secret, scopes=SCOPES)
    credentials.refresh(Request())
    return credentials


def get_credentials() -> Credentials:
    """Return verified cached credentials; never opens a browser."""
    client_id, secret = _client_credentials()
    _secure_existing_credentials()
    source = TOKEN_PATH if TOKEN_PATH.exists() else _LEGACY_TOKEN
    credentials = None
    changed = False
    if source is not None and source.exists():
        # Legacy repo paths can themselves traverse a .claude skills symlink;
        # __file__.resolve() above follows it before selecting this cache.
        _check_path(source)
        try:
            credentials = Credentials.from_authorized_user_file(str(source))
        except (ValueError, KeyError, TypeError) as exc:
            sys.exit(f"error: unreadable token cache ({type(exc).__name__}); run auth --force")
        if credentials.client_id != client_id:
            sys.exit("error: OAuth client differs from the cached token; run auth --force")
        if set(SCOPES) - set(credentials.scopes or []):
            sys.exit("error: cached token is missing required scopes; run auth --force")
        if not credentials.refresh_token:
            sys.exit("error: cached token has no refresh token; run auth --force")
        if not credentials.valid:
            credentials.refresh(Request())
            changed = True
    else:
        credentials = _from_offline_file(client_id, secret)
        changed = credentials is not None
    if credentials is None:
        sys.exit(f"error: no usable offline token for {EXPECTED_EMAIL}; run auth explicitly")
    _verify_account(credentials)
    if changed:
        _write_secret(TOKEN_PATH, credentials.to_json() + "\n")
    return credentials


def authorize(force: bool = False) -> dict:
    """Explicit consent, with account/scope checks before replacing a token."""
    _secure_existing_credentials()
    if TOKEN_PATH.exists() and not force:
        return {"token": str(TOKEN_PATH), "status": "exists", "hint": "pass --force to re-consent"}
    flow = InstalledAppFlow.from_client_config(_client_config(), SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent", login_hint=EXPECTED_EMAIL)
    if not credentials.token or not credentials.refresh_token:
        sys.exit("error: Google returned no offline credentials; nothing saved")
    _verify_account(credentials)
    if set(SCOPES) - _granted_scopes_for_token(credentials.token):
        sys.exit("error: not every required scope was granted; nothing saved")
    _write_secret(TOKEN_PATH, credentials.to_json() + "\n")
    return {"token": str(TOKEN_PATH), "status": "authorized", "account": EXPECTED_EMAIL, "offline": True}


def export_offline_token(dest: Path) -> Path:
    """Export an offline token only when explicitly invoked by the caller."""
    credentials = get_credentials()
    dest = dest.expanduser()
    _write_secret(dest, credentials.refresh_token + "\n")
    return dest


def get_access_token() -> str:
    return get_credentials().token
