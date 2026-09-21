#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth>=2.0.0", "google-auth-oauthlib>=1.0.0", "httpx>=0.27.0"]
# ///
"""Explicit offline OAuth consent for the wrapper's configured account.

Mint: gws_auth.py [--force] [--port PORT]
Cloud provisioning: gws_auth.py export
WARNING: export prints refresh-token and client secrets. Never paste its output
in chat, logs or a repository. Data commands use gws.py and never open consent.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

import httpx
from google_auth_oauthlib.flow import InstalledAppFlow

CONFIG_DIR = Path(os.environ.get("GWS_CONFIG_DIR") or WORKSPACE_CONFIG["config_dir"]).expanduser()
CLIENT_PATH = CONFIG_DIR / "client.json"
TOKEN_PATH = CONFIG_DIR / "token.json"
SCOPES = WORKSPACE_CONFIG["mint_scopes"]
EXPECTED_EMAIL = os.environ.get("GWS_EXPECTED_EMAIL") or WORKSPACE_CONFIG["expected_email"]


def _write_secret(path: Path, content: str) -> None:
    CONFIG_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def mint(email: str, force: bool, port: int) -> None:
    if CONFIG_DIR.is_symlink() or TOKEN_PATH.is_symlink() or CLIENT_PATH.is_symlink():
        sys.exit("error: credential paths must not be symlinks")
    if TOKEN_PATH.exists() and not force:
        sys.exit(f"error: {TOKEN_PATH} exists; pass --force to replace it")
    if not CLIENT_PATH.exists():
        sys.exit(f"error: missing {CLIENT_PATH} (OAuth desktop client JSON for the configured account)")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_PATH), SCOPES)
    flow.redirect_uri = f"http://localhost:{port}/"
    # run_local_server mints its own OAuth state; a URL built separately via authorization_url()
    # would fail the CSRF check on callback. Let it print the URL itself.
    creds = flow.run_local_server(
        port=port, open_browser=False, timeout_seconds=1800,
        authorization_prompt_message=f"Open this URL in a browser logged in as {email} and approve all scopes:\n\n{{url}}\n",
        access_type="offline", prompt="consent", login_hint=email,
    )
    auth = {"Authorization": f"Bearer {creds.token}"}
    got_email = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", headers=auth, timeout=30).json().get("email", "")
    granted = set(httpx.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": creds.token}, timeout=30).json().get("scope", "").split())
    missing = sorted(set(SCOPES) - granted - {"openid"})
    if got_email.lower() != email.lower():
        sys.exit(f"error: consent was given as {got_email or 'unknown'}, expected {email}; nothing saved")
    if missing:
        sys.exit(f"error: scopes not granted: {missing}; nothing saved — redo and tick every box")
    if not creds.refresh_token:
        sys.exit("error: Google returned no refresh token; nothing saved")
    _write_secret(TOKEN_PATH, creds.to_json() + "\n")
    print(f"saved {TOKEN_PATH} for {got_email} ({len(granted)} scopes)")


def export() -> None:
    d = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    for k, v in (("GWS_CLIENT_ID", d["client_id"]), ("GWS_CLIENT_SECRET", d["client_secret"]), ("GWS_REFRESH_TOKEN", d["refresh_token"])):
        print(f"{k}={v}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", nargs="?", default="mint", choices=["mint", "export"])
    p.add_argument("--email", default=EXPECTED_EMAIL)
    p.add_argument("--force", action="store_true")
    p.add_argument("--port", type=int, default=0, help="redirect port (default: random free port)")
    a = p.parse_args()
    if a.action == "export":
        export()
        return
    port = a.port
    if not port:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
    mint(a.email, a.force, port)

