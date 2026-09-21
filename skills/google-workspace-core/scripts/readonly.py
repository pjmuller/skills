#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "google-auth>=2.0.0",
#   "google-auth-oauthlib>=1.0.0",
#   "httpx>=0.27.0",
#   "python-dotenv>=1.0.0",
# ]
# ///
"""Account-configured read-only Google Drive, Docs, and Sheets facade."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx
from dotenv import dotenv_values
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Supplied by the account wrapper before executing this module. No identity defaults.
EXPECTED_EMAIL = WORKSPACE_CONFIG["expected_email"]
CONFIG_DIR = Path(WORKSPACE_CONFIG["config_dir"]).expanduser()
CLIENT_PATH = CONFIG_DIR / "client.json"
TOKEN_PATH = CONFIG_DIR / "token.json"
SCOPES = list(WORKSPACE_CONFIG["scopes"])
DRIVE_API = "https://www.googleapis.com/drive/v3"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,}$")
FILE_FIELDS = (
    "id,name,mimeType,size,md5Checksum,parents,webViewLink,createdTime,modifiedTime"
)


def _secure_existing_credentials() -> None:
    if CONFIG_DIR.is_symlink():
        raise RuntimeError(f"credential directory must not be a symlink: {CONFIG_DIR}")
    if not CONFIG_DIR.exists():
        return
    CONFIG_DIR.chmod(0o700)
    for path in (CLIENT_PATH, TOKEN_PATH):
        if path.is_symlink():
            raise RuntimeError(f"credential file must not be a symlink: {path}")
        if path.exists():
            path.chmod(0o600)


def _write_secret(path: Path, content: str) -> None:
    if CONFIG_DIR.is_symlink():
        raise RuntimeError(f"credential directory must not be a symlink: {CONFIG_DIR}")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_DIR.chmod(0o700)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=CONFIG_DIR, delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def _configure(client_env: str, force: bool) -> dict[str, str]:
    _secure_existing_credentials()
    if CLIENT_PATH.exists() and not force:
        raise RuntimeError(f"{CLIENT_PATH} exists; pass --force to replace it")
    values = dotenv_values(client_env)
    client_id = values.get("GOOGLE_WORKSPACE_CLIENT_ID") or values.get(
        "GOOGLE_CLIENT_ID"
    )
    client_secret = (
        values.get("GOOGLE_WORKSPACE_CLIENT_SECRET")
        or values.get("GOOGLE_CLIENT_SECRET")
        or values.get("GOOGLE_SECRET_KEY")
    )
    if not client_id or not client_secret:
        raise RuntimeError("client env needs a supported Google client ID/secret pair")
    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    _write_secret(CLIENT_PATH, json.dumps(config, indent=2) + "\n")
    return {"configured": str(CLIENT_PATH), "account": EXPECTED_EMAIL}


def _email_for_token(token: str) -> str:
    response = httpx.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    return str(response.json().get("email", "")).lower()


def _granted_scopes_for_token(token: str) -> set[str]:
    response = httpx.post(
        "https://oauth2.googleapis.com/tokeninfo",
        data={"access_token": token},
        timeout=30,
    )
    response.raise_for_status()
    return set(str(response.json().get("scope", "")).split())


def _credentials(force_reauth: bool = False, *, allow_auth: bool = False) -> Credentials:
    _secure_existing_credentials()
    if not CLIENT_PATH.exists():
        raise RuntimeError(
            f"missing {CLIENT_PATH}; run configure --client-env <oauth-client.env>"
        )

    credentials: Credentials | None = None
    changed = False
    if TOKEN_PATH.exists() and not force_reauth:
        try:
            credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH))
            client_config = json.loads(CLIENT_PATH.read_text(encoding="utf-8"))
            installed_config = client_config["installed"]
            if not isinstance(installed_config, dict):
                raise TypeError("installed OAuth configuration must be an object")
            configured_client_id = installed_config["client_id"]
            if not isinstance(configured_client_id, str):
                raise TypeError("OAuth client ID must be a string")
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError(
                "invalid OAuth client/token cache; reconfigure or run auth --force"
            ) from exc
        missing_scopes = set(SCOPES) - set(credentials.scopes or [])
        if missing_scopes:
            raise RuntimeError(
                "cached token is missing required Workspace scopes; run auth --force"
            )
        if credentials.client_id != configured_client_id:
            raise RuntimeError("OAuth client changed; run auth --force")
        if not credentials.refresh_token:
            raise RuntimeError("cached token is not offline-capable; run auth --force")

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        changed = True
    elif not credentials or not credentials.valid:
        if not allow_auth:
            raise RuntimeError("no valid offline credentials; run auth explicitly")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_PATH), SCOPES)
        credentials = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
            login_hint=EXPECTED_EMAIL,
            authorization_prompt_message=(
                "Authorize Google Workspace access as "
                f"{EXPECTED_EMAIL}: {{url}}"
            ),
            success_message="Google Workspace authorization received. You may close this tab.",
        )
        if not credentials.refresh_token:
            raise RuntimeError(
                "Google did not return an offline refresh token; rerun auth --force"
            )
        if not credentials.token:
            raise RuntimeError(
                "Google did not return an access token; rerun auth --force"
            )
        missing_scopes = set(SCOPES) - _granted_scopes_for_token(credentials.token)
        if missing_scopes:
            raise RuntimeError(
                "Google did not grant every required Workspace scope; "
                "rerun auth --force"
            )
        changed = True

    email = _email_for_token(credentials.token)
    if email != EXPECTED_EMAIL:
        raise RuntimeError(
            f"authorized as {email or 'unknown'}, expected {EXPECTED_EMAIL}; "
            "run auth --force and choose the requested account"
        )
    if changed or not TOKEN_PATH.exists():
        _write_secret(TOKEN_PATH, credentials.to_json() + "\n")
    return credentials


def _extract_id(value: str) -> str:
    candidate = value.strip()
    if "://" in candidate:
        parsed = urlparse(candidate)
        query_id = parse_qs(parsed.query).get("id", [])
        if query_id:
            candidate = query_id[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            for marker in ("d", "folders"):
                if marker in parts and parts.index(marker) + 1 < len(parts):
                    candidate = parts[parts.index(marker) + 1]
                    break
    if candidate == "root":
        return candidate
    if not ID_PATTERN.fullmatch(candidate):
        raise ValueError(f"could not extract a Google file/folder ID from {value!r}")
    return candidate


def _api_client() -> httpx.Client:
    token = _credentials().token
    return httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=60)


def _json(response: httpx.Response) -> Any:
    response.raise_for_status()
    return response.json()


def _drive_files(query: str, max_results: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page_token: str | None = None
    with _api_client() as client:
        while len(files) < max_results:
            params = {
                "q": query,
                "spaces": "drive",
                "pageSize": min(1000, max_results - len(files)),
                "fields": f"nextPageToken,incompleteSearch,files({FILE_FIELDS})",
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
                "orderBy": "folder,name_natural",
            }
            if page_token:
                params["pageToken"] = page_token
            data = _json(client.get(f"{DRIVE_API}/files", params=params))
            if data.get("incompleteSearch"):
                raise RuntimeError("Drive search was incomplete; narrow the query")
            files.extend(data.get("files", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return files


def _drive_list(folder: str, max_results: int) -> list[dict[str, Any]]:
    folder_id = _extract_id(folder)
    return _drive_files(f"'{folder_id}' in parents and trashed=false", max_results)


def _drive_search(query: str, max_results: int) -> list[dict[str, Any]]:
    return _drive_files(f"({query}) and trashed=false", max_results)


def _drive_get(value: str) -> dict[str, Any]:
    file_id = _extract_id(value)
    fields = f"{FILE_FIELDS},owners(displayName,emailAddress),driveId,trashed"
    with _api_client() as client:
        return _json(
            client.get(
                f"{DRIVE_API}/files/{file_id}",
                params={"fields": fields, "supportsAllDrives": "true"},
            )
        )


def _write_document(path: Path, content: str, overwrite: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(
            f"output exists: {path}; pass --force to replace it"
        ) from exc
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)


def _doc_read(
    value: str, output: str | None, overwrite: bool = False
) -> dict[str, Any] | None:
    file_id = _extract_id(value)
    with _api_client() as client:
        metadata = _json(
            client.get(
                f"{DRIVE_API}/files/{file_id}",
                params={"fields": "id,name,mimeType", "supportsAllDrives": "true"},
            )
        )
        if metadata.get("mimeType") != "application/vnd.google-apps.document":
            raise RuntimeError(
                f"{file_id} is {metadata.get('mimeType')}, not a Google Doc"
            )
        response = client.get(
            f"{DRIVE_API}/files/{file_id}/export",
            params={"mimeType": "text/markdown"},
        )
        response.raise_for_status()
    markdown = response.content.decode("utf-8-sig")
    if output:
        destination = Path(output).expanduser()
        _write_document(destination, markdown, overwrite)
        return {
            "id": file_id,
            "name": metadata.get("name"),
            "output": str(destination.resolve()),
            "bytes": len(response.content),
        }
    sys.stdout.write(markdown)
    return None


def _sheet_meta(value: str) -> dict[str, Any]:
    sheet_id = _extract_id(value)
    with _api_client() as client:
        data = _json(
            client.get(
                f"{SHEETS_API}/{sheet_id}",
                params={
                    "includeGridData": "false",
                    "fields": "spreadsheetId,properties.title,sheets.properties",
                },
            )
        )
    return {
        "id": data.get("spreadsheetId"),
        "title": data.get("properties", {}).get("title"),
        "tabs": [
            {
                "id": tab.get("properties", {}).get("sheetId"),
                "name": tab.get("properties", {}).get("title"),
                "rows": tab.get("properties", {})
                .get("gridProperties", {})
                .get("rowCount"),
                "columns": tab.get("properties", {})
                .get("gridProperties", {})
                .get("columnCount"),
            }
            for tab in data.get("sheets", [])
        ],
    }


def _sheet_read(value: str, cell_range: str) -> dict[str, Any]:
    sheet_id = _extract_id(value)
    encoded_range = quote(cell_range, safe="")
    with _api_client() as client:
        return _json(
            client.get(
                f"{SHEETS_API}/{sheet_id}/values/{encoded_range}",
                params={
                    "majorDimension": "ROWS",
                    "valueRenderOption": "FORMATTED_VALUE",
                    "dateTimeRenderOption": "FORMATTED_STRING",
                },
            )
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Read-only Google Workspace CLI for {EXPECTED_EMAIL}"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    configure = commands.add_parser(
        "configure", help="import an installed-app OAuth client"
    )
    configure.add_argument("--client-env", required=True)
    configure.add_argument("--force", action="store_true")

    auth = commands.add_parser("auth", help="mint/verify the offline token")
    auth.add_argument("--force", action="store_true", help="replace the cached token")

    commands.add_parser("whoami", help="show the authenticated account")

    drive_list = commands.add_parser("drive-list", help="list a Drive folder")
    drive_list.add_argument("folder")
    drive_list.add_argument("-n", "--max", type=int, default=100)

    drive_search = commands.add_parser("drive-search", help="search Drive query syntax")
    drive_search.add_argument("query")
    drive_search.add_argument("-n", "--max", type=int, default=50)

    drive_get = commands.add_parser("drive-get", help="read Drive file metadata")
    drive_get.add_argument("file")

    doc_read = commands.add_parser("doc-read", help="export a Google Doc as Markdown")
    doc_read.add_argument("document")
    doc_read.add_argument("-o", "--output")
    doc_read.add_argument(
        "--force", action="store_true", help="replace an existing output file"
    )

    sheet_meta = commands.add_parser("sheet-meta", help="read spreadsheet/tab metadata")
    sheet_meta.add_argument("spreadsheet")

    sheet_read = commands.add_parser("sheet-read", help="read a Sheet A1 range")
    sheet_read.add_argument("spreadsheet")
    sheet_read.add_argument("range")
    return parser


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main() -> None:
    args = _parser().parse_args()
    try:
        result: Any = None
        if args.command == "configure":
            result = _configure(args.client_env, args.force)
        elif args.command == "auth":
            credentials = _credentials(args.force, allow_auth=True)
            result = {"email": _email_for_token(credentials.token), "offline": True}
        elif args.command == "whoami":
            credentials = _credentials()
            result = {"email": _email_for_token(credentials.token)}
        elif args.command == "drive-list":
            if args.max < 1:
                raise ValueError("--max must be positive")
            result = _drive_list(args.folder, args.max)
        elif args.command == "drive-search":
            if args.max < 1:
                raise ValueError("--max must be positive")
            result = _drive_search(args.query, args.max)
        elif args.command == "drive-get":
            result = _drive_get(args.file)
        elif args.command == "doc-read":
            result = _doc_read(args.document, args.output, args.force)
        elif args.command == "sheet-meta":
            result = _sheet_meta(args.spreadsheet)
        elif args.command == "sheet-read":
            result = _sheet_read(args.spreadsheet, args.range)
        if result is not None:
            _print_json(result)
    except httpx.HTTPStatusError as exc:
        message = exc.response.text
        try:
            payload = exc.response.json()
            message = payload.get("error", {}).get("message", message)
        except (ValueError, AttributeError):
            pass
        sys.exit(f"Google API {exc.response.status_code}: {message}")
    except (OSError, RefreshError, RuntimeError, ValueError, httpx.RequestError) as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
