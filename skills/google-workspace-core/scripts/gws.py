#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth>=2.0.0", "httpx>=0.27.0"]
# ///
"""Google Workspace REST commands. Account configuration is supplied by a local wrapper."""

from __future__ import annotations

import argparse
import base64
import html
from email.message import EmailMessage
from email.policy import SMTP
from html.parser import HTMLParser
import csv
import json
import mimetypes
import os
import re
import sys
import uuid
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx
from google.oauth2.credentials import Credentials

# Explicit wrapper configuration; no account or credential location is inferred.
EXPECTED_EMAIL = os.environ.get("GWS_EXPECTED_EMAIL") or WORKSPACE_CONFIG["expected_email"]
CONFIG_DIR = Path(os.environ.get("GWS_CONFIG_DIR") or WORKSPACE_CONFIG["config_dir"]).expanduser()
TOKEN_PATH = CONFIG_DIR / "token.json"
REAUTH = "run the repository's gws_auth.py to mint a new offline token"
REQUIRED_SCOPES = set(WORKSPACE_CONFIG["required_scopes"])
FEATURES = set(WORKSPACE_CONFIG.get("features", []))

DRIVE = "https://www.googleapis.com/drive/v3"
DOCS = "https://docs.googleapis.com/v1/documents"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
SLIDES = "https://slides.googleapis.com/v1/presentations"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
HOSTS = {  # shorthand path prefix -> API host, for the generic `api` passthrough
    "/gmail/": "https://gmail.googleapis.com",
    "/drive/": "https://www.googleapis.com",
    "/upload/": "https://www.googleapis.com",
    "/v1/documents": "https://docs.googleapis.com",
    "/v1/presentations": "https://slides.googleapis.com",
    "/v4/spreadsheets": "https://sheets.googleapis.com",
}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
FILE_FIELDS = "id,name,mimeType,size,parents,webViewLink,modifiedTime,driveId,trashed"
EXPORT_MIME = {
    "pdf": "application/pdf",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "html": "text/html",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "epub": "application/epub+zip",
    "odt": "application/vnd.oasis.opendocument.text",
}

CLIENT: httpx.Client | None = None


# --- auth -------------------------------------------------------------------

def _secure_existing_credentials() -> None:
    """Refuse symlinked credential paths; force owner-only permissions."""
    if CONFIG_DIR.is_symlink():
        sys.exit(f"error: credential directory must not be a symlink: {CONFIG_DIR}")
    if not CONFIG_DIR.exists():
        sys.exit(f"error: no Google credentials at {CONFIG_DIR}; {REAUTH}")
    CONFIG_DIR.chmod(0o700)
    if TOKEN_PATH.is_symlink():
        sys.exit(f"error: credential file must not be a symlink: {TOKEN_PATH}")
    if TOKEN_PATH.exists():
        TOKEN_PATH.chmod(0o600)


def _write_secret(path: Path, content: str) -> None:
    """Atomically write a 0600 file inside the 0700 credential dir."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=CONFIG_DIR, delete=False) as fh:
        fh.write(content)
        tmp = Path(fh.name)
    tmp.chmod(0o600)
    tmp.replace(path)


def credentials() -> Credentials:
    """Load (and refresh) the offline token from env or file. Never opens a browser."""
    env = {k: os.environ.get(f"GWS_{k}") for k in ("REFRESH_TOKEN", "CLIENT_ID", "CLIENT_SECRET")}
    if any(env.values()):
        if not all(env.values()):
            sys.exit("error: set all of GWS_REFRESH_TOKEN, GWS_CLIENT_ID, GWS_CLIENT_SECRET (or none)")
        creds = Credentials(None, refresh_token=env["REFRESH_TOKEN"], client_id=env["CLIENT_ID"],
                            client_secret=env["CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
        refresh(creds)
        verify_identity(creds)
        return creds
    _secure_existing_credentials()
    if not TOKEN_PATH.exists():
        sys.exit(f"error: missing {TOKEN_PATH}; {REAUTH}")
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    except (KeyError, TypeError, ValueError) as exc:
        sys.exit(f"error: unreadable token file ({exc}); {REAUTH}")
    if REQUIRED_SCOPES - set(creds.scopes or []):
        sys.exit(f"error: token is missing required scopes; {REAUTH}")
    if not creds.refresh_token:
        sys.exit(f"error: token is not offline-capable; {REAUTH}")
    changed = not creds.valid
    if changed:
        refresh(creds)
    verify_identity(creds)
    if changed:
        _write_secret(TOKEN_PATH, creds.to_json() + "\n")
    return creds


def verify_identity(creds: Credentials) -> None:
    """Validate the actual account before API use or persisting a refreshed token."""
    response = httpx.get("https://openidconnect.googleapis.com/v1/userinfo",
                         headers={"Authorization": f"Bearer {creds.token}"}, timeout=30)
    if not response.is_success:
        sys.exit(f"error: could not verify configured Google account (HTTP {response.status_code})")
    email = response.json().get("email", "")
    if email.lower() != EXPECTED_EMAIL.lower():
        sys.exit(f"error: authorized as {email or 'unknown'}, expected {EXPECTED_EMAIL}")


def refresh(creds: Credentials) -> None:
    """Refresh over httpx; google-auth's own transport would pull in `requests`."""
    r = httpx.post(creds.token_uri, timeout=30, data={
        "grant_type": "refresh_token",
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    })
    if not r.is_success:
        sys.exit(f"error: token refresh failed ({r.status_code} {r.text[:200]}); {REAUTH}")
    payload = r.json()
    creds.token = payload["access_token"]
    # google-auth compares expiry against a naive UTC clock
    creds.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=int(payload.get("expires_in", 3600)))


def client() -> httpx.Client:
    global CLIENT
    if CLIENT is None:
        CLIENT = httpx.Client(
            headers={"Authorization": f"Bearer {credentials().token}"}, timeout=120
        )
    return CLIENT


# --- transport --------------------------------------------------------------

def request(method: str, url: str, **kw) -> httpx.Response:
    if url.startswith(f"{DRIVE}/"):  # shared drives are opt-in on every Drive call
        kw.setdefault("params", {})
        kw["params"] = {"supportsAllDrives": "true", **kw["params"]}
    r = client().request(method.upper(), url, **kw)
    if not r.is_success:
        detail = r.text
        try:  # Google wraps the useful line in {"error":{"message":...}}
            detail = r.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        sys.exit(f"Google API {r.status_code} on {method.upper()} {url}: {detail}")
    return r


def api(method: str, url: str, **kw) -> Any:
    r = request(method, url, **kw)
    return r.json() if r.content else {}


def extract_id(value: str) -> str:
    """Accept a bare id or any Google URL (/d/<id>/…, /folders/<id>, ?id=<id>)."""
    candidate = value.strip()
    if "/" in candidate:  # bare ids never contain "/", so a scheme is optional
        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        by_query = parse_qs(parsed.query).get("id", [])
        if by_query:
            candidate = by_query[0]
        else:
            parts = [p for p in parsed.path.split("/") if p]
            for marker in ("d", "folders"):
                if marker in parts and parts.index(marker) + 1 < len(parts):
                    candidate = parts[parts.index(marker) + 1]
                    break
    if candidate == "root":
        return candidate
    if not ID_RE.fullmatch(candidate):
        sys.exit(f"error: no Google file id found in {value!r}")
    return candidate


# --- output -----------------------------------------------------------------

def out(data: Any, as_json: bool, human: str | None = None) -> None:
    if as_json or human is None:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(human)


def trunc(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def table(rows: list[list[str]]) -> str:
    widths = [max((len(str(r[i])) for r in rows if i < len(r)), default=0) for i in range(max((len(r) for r in rows), default=0))]
    return "\n".join(
        "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)).rstrip() for r in rows
    )


def write_out(path: str, content: bytes | str) -> str:
    target = Path(path).expanduser()
    if isinstance(content, str):
        target.write_text(content, encoding="utf-8")
    else:
        target.write_bytes(content)
    return f"{target.resolve()} ({len(content)} {'chars' if isinstance(content, str) else 'bytes'})"


def read_body(source: str) -> Any:
    raw = sys.stdin.read() if source == "-" else Path(source).expanduser().read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.exit(f"error: --body is not valid JSON: {exc}")


def read_text(source: str) -> str:
    return sys.stdin.read() if source == "-" else Path(source).expanduser().read_text(encoding="utf-8")


def requests_body(source: str) -> dict:
    """batchUpdate body: accept a bare list of requests or the full {requests:[…]}."""
    body = read_body(source)
    return body if isinstance(body, dict) else {"requests": body}


def report_replies(result: dict, as_json: bool) -> None:
    replies = [r for r in result.get("replies", []) if r]
    ids = [
        v.get("objectId")
        for r in replies
        for v in r.values()
        if isinstance(v, dict) and v.get("objectId")
    ]
    out(result, as_json, f"ok — {len(result.get('replies', []))} replies" + (f"; object ids: {', '.join(ids)}" if ids else ""))


# --- generic ----------------------------------------------------------------

def cmd_whoami(a):
    creds = credentials()
    me = api("GET", "https://openidconnect.googleapis.com/v1/userinfo")
    email = str(me.get("email", "")).lower()
    if email != EXPECTED_EMAIL:
        sys.exit(f"error: token belongs to {email or 'unknown'}, expected {EXPECTED_EMAIL}")
    # env-var creds carry no scope list; ask Google what the access token actually grants
    info = httpx.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": creds.token}, timeout=30).json()
    scopes = sorted(s.rstrip("/").rsplit("/", 1)[-1] for s in info.get("scope", "").split())
    data = {"email": email, "token_expiry": str(creds.expiry), "scopes": scopes}
    out(data, a.json, f"{email}  (token valid until {creds.expiry} UTC; scopes: {', '.join(scopes)})")


def cmd_token(a):
    print(credentials().token)


def cmd_api(a):
    url = a.url
    if url.startswith(("http://", "https://")):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or not (
            parsed.hostname == "www.googleapis.com" or parsed.hostname.endswith(".googleapis.com")
        ) or parsed.port not in (None, 443):
            sys.exit("error: absolute api URLs must be HTTPS on a *.googleapis.com host")
    else:
        host = next((h for p, h in HOSTS.items() if url.startswith(p)), "https://www.googleapis.com")
        url = host + url
    params = {}
    for kv in a.param or []:
        key, _, value = kv.partition("=")
        params[key] = value
    kw: dict = {"params": params}
    if a.body:
        kw["json"] = read_body(a.body)
    out(api(a.method, url, **kw), True)


# --- drive ------------------------------------------------------------------

def drive_files(query: str, limit: int) -> list[dict]:
    files: list[dict] = []
    page: str | None = None
    while len(files) < limit:
        params = {
            "q": query,
            "pageSize": min(1000, limit - len(files)),
            "fields": f"nextPageToken,files({FILE_FIELDS})",
            "includeItemsFromAllDrives": "true",
            "supportsAllDrives": "true",
            "corpora": "allDrives",
            "orderBy": "folder,name_natural",
        }
        if page:
            params["pageToken"] = page
        data = api("GET", f"{DRIVE}/files", params=params)
        files += data.get("files", [])
        page = data.get("nextPageToken")
        if not page:
            break
    return files[:limit]


def file_rows(files: list[dict]) -> str:
    rows = [["ID", "NAME", "TYPE", "MODIFIED"]]
    for f in files:
        rows.append([
            f["id"],
            trunc(f.get("name", ""), 60),
            f.get("mimeType", "").replace("application/vnd.google-apps.", "g."),
            (f.get("modifiedTime") or "")[:10],
        ])
    return table(rows) + f"\n\n{len(files)} file(s)"


def cmd_drive_list(a):
    files = drive_files(f"'{extract_id(a.folder)}' in parents and trashed=false", a.max)
    out(files, a.json, file_rows(files))


def cmd_drive_search(a):
    files = drive_files(f"({a.query}) and trashed=false", a.max)
    out(files, a.json, file_rows(files))


def cmd_drive_get(a):
    fields = f"{FILE_FIELDS},owners(displayName,emailAddress),createdTime,md5Checksum"
    f = api("GET", f"{DRIVE}/files/{extract_id(a.file)}", params={"fields": fields})
    human = "\n".join(f"{k}: {v}" for k, v in f.items() if k != "owners")
    out(f, a.json, human)


def cmd_drive_copy(a):
    body: dict = {"name": a.name}
    if a.parent:
        body["parents"] = [extract_id(a.parent)]
    f = api("POST", f"{DRIVE}/files/{extract_id(a.file)}/copy",
            params={"fields": FILE_FIELDS}, json=body)
    out(f, a.json, f"copied -> {f['id']}  {f['name']}\n{f.get('webViewLink')}")


def drive_upload(path: str, name: str | None = None, parent: str | None = None, mime: str | None = None) -> dict:
    """Multipart upload of a local file. Works into shared drives (supportsAllDrives)."""
    src = Path(path).expanduser()
    if not src.is_file():
        sys.exit(f"error: no such file: {src}")
    meta: dict = {"name": name or src.name}
    if parent:
        meta["parents"] = [extract_id(parent)]
    mime = mime or mimetypes.guess_type(src.name)[0] or "application/octet-stream"
    boundary = uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
        json.dumps(meta).encode(),
        f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode(),
        src.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return api("POST", "https://www.googleapis.com/upload/drive/v3/files",
               params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": FILE_FIELDS},
               content=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"})


def cmd_drive_upload(a):
    f = drive_upload(a.file, a.name, a.parent, a.mime)
    out(f, a.json, f"uploaded -> {f['id']}  {f['name']}\n{f.get('webViewLink')}")


def cmd_drive_trash(a):
    f = api("PATCH", f"{DRIVE}/files/{extract_id(a.file)}",
            params={"fields": "id,name,trashed"}, json={"trashed": True})
    out(f, a.json, f"trashed {f['id']}  {f['name']}")


def cmd_drive_export(a):
    fid = extract_id(a.file)
    mime = EXPORT_MIME.get(a.format.lower())
    if not mime:
        sys.exit(f"error: unknown --format {a.format!r}; use {'/'.join(sorted(EXPORT_MIME))}")
    r = request("GET", f"{DRIVE}/files/{fid}/export", params={"mimeType": mime})
    out({"id": fid, "out": a.out, "bytes": len(r.content)}, a.json,
        f"exported -> {write_out(a.out, r.content)}")


# --- docs -------------------------------------------------------------------

def cmd_doc_read(a):
    r = request("GET", f"{DRIVE}/files/{extract_id(a.doc)}/export", params={"mimeType": "text/markdown"})
    markdown = r.content.decode("utf-8-sig")
    if a.out:
        print(f"wrote {write_out(a.out, markdown)}")
    else:
        sys.stdout.write(markdown)


def cmd_doc_outline(a):
    doc = api("GET", f"{DOCS}/{extract_id(a.doc)}",
              params={"fields": "title,body.content,revisionId"})
    rows = [["RANGE", "STYLE", "TEXT"]]
    for el in doc.get("body", {}).get("content", []):
        span = f"{el.get('startIndex', 0)}-{el.get('endIndex', 0)}"
        if "paragraph" in el:
            p = el["paragraph"]
            style = p.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
            if p.get("bullet"):
                style += "+bullet"
            bits = []
            for pe in p.get("elements", []):
                if "textRun" in pe:
                    bits.append(pe["textRun"].get("content", ""))
                elif "inlineObjectElement" in pe:
                    bits.append(f"<image {pe['inlineObjectElement'].get('inlineObjectId')}>")
                elif "pageBreak" in pe:
                    bits.append("<page-break>")
            rows.append([span, style, trunc("".join(bits), 80)])
        elif "table" in el:
            t = el["table"]
            rows.append([span, f"table {t.get('rows')}x{t.get('columns')}", ""])
        else:
            rows.append([span, next(iter(set(el) - {"startIndex", "endIndex"}), "?"), ""])
    out(doc.get("body", {}).get("content", []), a.json,
        f"{doc.get('title')}  (rev {doc.get('revisionId')})\n" + table(rows))


def cmd_doc_replace(a):
    req = {"replaceAllText": {
        "containsText": {"text": a.find, "matchCase": bool(a.match_case)},
        "replaceText": a.replace}}
    res = api("POST", f"{DOCS}/{extract_id(a.doc)}:batchUpdate", json={"requests": [req]})
    n = res["replies"][0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    out(res, a.json, f"replaced {n} occurrence(s)")


def cmd_doc_insert(a):
    if a.end:
        req = {"insertText": {"endOfSegmentLocation": {}, "text": a.text}}
    elif a.index is not None:
        req = {"insertText": {"location": {"index": a.index}, "text": a.text}}
    else:
        sys.exit("error: pass --index N or --end")
    res = api("POST", f"{DOCS}/{extract_id(a.doc)}:batchUpdate", json={"requests": [req]})
    out(res, a.json, f"inserted {len(a.text)} chars (rev {res.get('writeControl', {}).get('requiredRevisionId', '?')})")


def cmd_doc_batch(a):
    res = api("POST", f"{DOCS}/{extract_id(a.doc)}:batchUpdate", json=requests_body(a.body))
    report_replies(res, a.json)


# --- sheets -----------------------------------------------------------------

def cmd_sheet_meta(a):
    data = api("GET", f"{SHEETS}/{extract_id(a.sheet)}",
               params={"fields": "spreadsheetId,properties.title,sheets.properties"})
    rows = [["TAB", "SHEET_ID", "ROWS", "COLS"]]
    for tab in data.get("sheets", []):
        p = tab["properties"]
        grid = p.get("gridProperties", {})
        rows.append([p["title"], p["sheetId"], grid.get("rowCount"), grid.get("columnCount")])
    out(data, a.json, f"{data['properties']['title']}  ({data['spreadsheetId']})\n" + table(rows))


def cmd_sheet_read(a):
    data = api("GET", f"{SHEETS}/{extract_id(a.sheet)}/values/{quote(a.range, safe='')}",
               params={"majorDimension": "ROWS", "valueRenderOption": "FORMATTED_VALUE"})
    values = data.get("values", [])
    out(data, a.json, f"{data.get('range')}\n" + table([[trunc(str(c), 40) for c in row] for row in values])
        + f"\n\n{len(values)} row(s)")


def parse_values(a) -> list[list]:
    if a.csv:
        with Path(a.csv).expanduser().open(encoding="utf-8", newline="") as fh:
            return [row for row in csv.reader(fh)]
    try:
        values = json.loads(a.values)
    except json.JSONDecodeError as exc:
        sys.exit(f"error: --values is not valid JSON: {exc}")
    if not isinstance(values, list) or not all(isinstance(r, list) for r in values):
        sys.exit("error: --values must be a JSON array of arrays")
    return values


def cmd_sheet_write(a):
    res = api("PUT", f"{SHEETS}/{extract_id(a.sheet)}/values/{quote(a.range, safe='')}",
              params={"valueInputOption": "USER_ENTERED"}, json={"values": parse_values(a)})
    out(res, a.json, f"wrote {res.get('updatedCells')} cell(s) in {res.get('updatedRange')}")


def cmd_sheet_append(a):
    res = api("POST", f"{SHEETS}/{extract_id(a.sheet)}/values/{quote(a.range, safe='')}:append",
              params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
              json={"values": parse_values(a)})
    upd = res.get("updates", {})
    out(res, a.json, f"appended {upd.get('updatedRows')} row(s) at {upd.get('updatedRange')}")


def cmd_sheet_batch(a):
    res = api("POST", f"{SHEETS}/{extract_id(a.sheet)}:batchUpdate", json=requests_body(a.body))
    report_replies(res, a.json)


# --- gmail -----------------------------------------------------------------

GMAIL_HEADERS = ("Date", "From", "To", "Cc", "Subject", "Message-ID", "References")


class _HTMLText(HTMLParser):
    """Small HTML-to-text fallback for messages without a text/plain part."""

    BLOCKS = frozenset({"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "li":
            self.parts.append("\n- ")
        elif tag.lower() in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCKS - {"br"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(source: str) -> str:
    parser = _HTMLText()
    parser.feed(source)
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def decode_websafe(data: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        return raw.decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def gmail_headers(payload: dict) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}


def gmail_bodies(payload: dict, message_id: str) -> tuple[str, str]:
    """Return the first inline plain and HTML bodies, ignoring attachments."""
    plain: list[str] = []
    rich: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        part_body = part.get("body") or {}
        data = part_body.get("data")
        if not data and not part.get("filename") and mime in ("text/plain", "text/html") and part_body.get("attachmentId"):
            attached = api("GET", f"{GMAIL}/messages/{message_id}/attachments/{part_body['attachmentId']}")
            data = attached.get("data")
        if not part.get("filename") and data:
            if mime == "text/plain":
                plain.append(decode_websafe(data))
            elif mime == "text/html":
                rich.append(decode_websafe(data))
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    return (next((x for x in plain if x), ""), next((x for x in rich if x), ""))


def clean_message_body(source: str) -> str:
    """Trim quoted reply chains and signature delimiters for compact agent input."""
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    markers = (
        r"^On .{1,400}? wrote:\s*$",
        r"^Op .{1,400}? schreef.{0,200}?:\s*$",
        r"^Le .{1,400}? a écrit\s*:\s*$",
        r"^Am .{1,400}? schrieb.{0,200}?:\s*$",
        r"^-{2,}\s*(?:Original Message|Forwarded message)\s*-{2,}\s*$",
        r"^_{5,}\s*$",
        r"^\*?(?:From|Van|Sent|Verzonden):\*?\s",
    )
    cut = len(text)
    for marker in markers:
        match = re.search(marker, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            cut = min(cut, match.start())
    text = text[:cut]
    text = "".join(line for line in text.splitlines(keepends=True) if not line.lstrip().startswith(">"))
    signature = re.search(r"^--\s*$", text, flags=re.MULTILINE)
    if signature:
        text = text[:signature.start()]
    return re.sub(r"[ \t]+$", "", re.sub(r"\n{3,}", "\n\n", text), flags=re.MULTILINE).strip()


def gmail_attachments(payload: dict) -> list[dict]:
    found: list[dict] = []

    def walk(part: dict) -> None:
        body = part.get("body") or {}
        if part.get("filename") or (body.get("attachmentId") and not part.get("mimeType", "").startswith("text/")):
            found.append({
                "filename": part.get("filename") or "(unnamed)",
                "mimeType": part.get("mimeType", "application/octet-stream"),
                "size": body.get("size", 0),
                "attachmentId": body.get("attachmentId"),
            })
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    return found


def gmail_message_view(message: dict) -> dict:
    payload = message.get("payload") or {}
    headers = gmail_headers(payload)
    plain, rich = gmail_bodies(payload, message.get("id", ""))
    body = clean_message_body(plain or html_to_text(rich))
    return {
        "id": message.get("id"),
        "threadId": message.get("threadId"),
        "labelIds": message.get("labelIds", []),
        "headers": {name: headers.get(name.lower(), "") for name in GMAIL_HEADERS if headers.get(name.lower())},
        "snippet": message.get("snippet", ""),
        "body": body,
        "attachments": gmail_attachments(payload),
    }


def format_gmail_message(view: dict, max_chars: int, heading: bool = False) -> str:
    lines = [f"## {view['headers'].get('Subject', '(no subject)')}" if heading else view["headers"].get("Subject", "(no subject)")]
    lines += [f"id: {view['id']}", f"thread: {view['threadId']}"]
    for name in GMAIL_HEADERS:
        if name == "Subject":
            continue
        if value := view["headers"].get(name):
            lines.append(f"{name}: {value}")
    if view["attachments"]:
        lines.append("attachments:")
        for item in view["attachments"]:
            lines.append(f"- {item['filename']} ({item['mimeType']}, {item['size']} bytes, id={item['attachmentId'] or '-'})")
    body = view["body"]
    if len(body) > max_chars:
        body = body[:max_chars] + "\n…[truncated]"
    lines += ["", body or "(no text body)"]
    return "\n".join(lines)


def gmail_get_message(message_id: str) -> dict:
    return api("GET", f"{GMAIL}/messages/{message_id}", params={"format": "full"})


def cmd_gmail_search(a):
    listing = api("GET", f"{GMAIL}/messages", params={"q": a.query, "maxResults": a.max})
    messages: list[dict] = []
    rows = [["DATE", "FROM", "SUBJECT", "ID"]]
    for stub in listing.get("messages", []):
        msg = api("GET", f"{GMAIL}/messages/{stub['id']}", params={
            "format": "metadata", "metadataHeaders": ["Date", "From", "Subject"]})
        headers = gmail_headers(msg.get("payload") or {})
        item = {
            "id": msg.get("id"),
            "threadId": msg.get("threadId"),
            "date": headers.get("date", ""),
            "from": headers.get("from", ""),
            "subject": headers.get("subject", ""),
        }
        messages.append(item)
        rows.append([trunc(item["date"], 28), trunc(item["from"], 42), trunc(item["subject"], 70), item["id"]])
    out(messages, a.json, table(rows) + f"\n\n{len(messages)} message(s)")


def cmd_gmail_get(a):
    message = gmail_get_message(a.id)
    view = gmail_message_view(message)
    out(message, a.json, format_gmail_message(view, a.max_chars))


def cmd_gmail_thread(a):
    thread = api("GET", f"{GMAIL}/threads/{a.id}", params={"format": "full"})
    views = [gmail_message_view(msg) for msg in thread.get("messages", [])]
    human = "\n\n---\n\n".join(format_gmail_message(view, a.max_chars, heading=True) for view in views)
    out(thread, a.json, human or "(empty thread)")


def reply_context(message_id: str) -> tuple[dict, str]:
    original = gmail_get_message(message_id)
    view = gmail_message_view(original)
    headers = gmail_headers(original.get("payload") or {})
    message_header = headers.get("message-id")
    if not message_header:
        sys.exit(f"error: message {message_id} has no Message-ID header; cannot create a threaded reply")
    return view, message_header


def normalized_reply_subject(subject: str) -> str:
    """Gmail threads common reply/forward prefixes but not a changed topic."""
    return re.sub(r"^(?:(?:re|fw|fwd|aw|sv):\s*)+", "", subject.strip(), flags=re.IGNORECASE).casefold()


def build_gmail_draft(a) -> tuple[str, str | None]:
    body = read_text(a.body)
    message = EmailMessage()
    message["From"] = EXPECTED_EMAIL
    message["To"] = a.to
    message["Subject"] = a.subject
    thread_id: str | None = None
    quote_plain = ""
    quote_html = ""
    if a.reply_to_message:
        original, message_header = reply_context(a.reply_to_message)
        thread_id = original["threadId"]
        old_headers = original["headers"]
        if normalized_reply_subject(a.subject) != normalized_reply_subject(old_headers.get("Subject", "")):
            sys.exit(
                "error: reply subject must match the original (an added Re: prefix is allowed) "
                f"to preserve Gmail threading; original: {old_headers.get('Subject', '(no subject)')!r}"
            )
        message["In-Reply-To"] = message_header
        message["References"] = " ".join(filter(None, [old_headers.get("References"), message_header]))
        lead = f"On {old_headers.get('Date', '?')}, {old_headers.get('From', '?')} wrote:"
        quoted = "\n".join(f"> {line}" if line else ">" for line in original["body"].splitlines())
        quote_plain = f"\n\n{lead}\n{quoted}"
        quote_html = (
            f'<br><br><div class="gmail_quote">{html.escape(lead)}'
            f'<blockquote style="margin:0 0 0 .8ex;border-left:1px #ccc solid;padding-left:1ex">'
            f'{html.escape(original["body"]).replace(chr(10), "<br>")}</blockquote></div>'
        )
    if a.html:
        message.set_content(html_to_text(body) + quote_plain)
        message.add_alternative(body + quote_html, subtype="html")
    else:
        message.set_content(body + quote_plain)
    raw = base64.urlsafe_b64encode(message.as_bytes(policy=SMTP)).decode("ascii")
    return raw, thread_id


def cmd_gmail_draft(a):
    raw, thread_id = build_gmail_draft(a)
    gmail_message: dict = {"raw": raw}
    if thread_id:
        gmail_message["threadId"] = thread_id
    draft = api("POST", f"{GMAIL}/drafts", json={"message": gmail_message})
    human = f"draft created: {draft['id']}"
    if draft.get("message"):
        human += f"  message={draft['message'].get('id')}  thread={draft['message'].get('threadId')}"
    out(draft, a.json, human)


def gmail_labels() -> list[dict]:
    return api("GET", f"{GMAIL}/labels").get("labels", [])


def cmd_gmail_labels(a):
    labels = sorted(gmail_labels(), key=lambda item: (item.get("type", ""), item.get("name", "").casefold()))
    rows = [["ID", "NAME", "TYPE"]] + [[item.get("id", ""), item.get("name", ""), item.get("type", "")] for item in labels]
    out(labels, a.json, table(rows))


def requested_labels(values: list[str] | None, known: list[dict]) -> list[str]:
    if not values:
        return []
    by_id = {item["id"]: item["id"] for item in known}
    by_name = {item.get("name", "").casefold(): item["id"] for item in known}
    resolved: list[str] = []
    for value in values:
        for label in (part.strip() for part in value.split(",")):
            if not label:
                continue
            label_id = by_id.get(label) or by_name.get(label.casefold())
            if not label_id:
                sys.exit(f"error: unknown Gmail label {label!r}; run gmail-labels")
            if label_id not in resolved:
                resolved.append(label_id)
    return resolved


def cmd_gmail_label(a):
    known = gmail_labels()
    add = requested_labels(a.add, known)
    remove = requested_labels(a.remove, known)
    if not add and not remove:
        sys.exit("error: pass --add LABEL or --remove LABEL")
    result = api("POST", f"{GMAIL}/messages/{a.id}/modify", json={"addLabelIds": add, "removeLabelIds": remove})
    out(result, a.json, f"updated {a.id}: +{','.join(add) or '-'}  -{','.join(remove) or '-'}")


# --- slides -----------------------------------------------------------------

# Compact mask: enough for one line per slide, cheap on a 163-slide deck.
OUTLINE_FIELDS = (
    "presentationId,title,"
    "layouts(objectId,layoutProperties.displayName),"
    "slides(objectId,slideProperties.layoutObjectId,"
    "slideProperties.notesPage(pageElements(shape(text(textElements(textRun(content)))))),"
    "pageElements(objectId,shape(shapeType,placeholder,text(textElements(textRun(content)))),"
    "table(rows,columns),image(contentUrl),elementGroup(children(objectId,"
    "shape(text(textElements(textRun(content))))))))"
)
ELEMENT_KINDS = ("shape", "table", "image", "video", "line", "elementGroup", "sheetsChart", "wordArt")


def element_text(el: dict) -> str:
    """All text inside a page element, recursing into groups and table cells."""
    parts: list[str] = []

    def text_of(container: dict) -> None:
        for te in (container.get("text") or {}).get("textElements", []):
            run = te.get("textRun") or te.get("autoText")
            if run:
                parts.append(run.get("content", ""))

    def walk(e: dict) -> None:
        if "shape" in e:
            text_of(e["shape"])
        for row in (e.get("table") or {}).get("tableRows", []):
            for cell in row.get("tableCells", []):
                text_of(cell)
                parts.append("\t")
        for child in (e.get("elementGroup") or {}).get("children", []):
            walk(child)

    walk(el)
    return "".join(parts)


def element_kind(el: dict) -> str:
    kind = next((k for k in ELEMENT_KINDS if k in el), "unknown")
    if kind == "elementGroup":
        return "group"
    if kind == "shape":
        return f"shape/{el['shape'].get('shapeType', '?')}".lower()
    return kind


def notes_text(page: dict) -> str:
    notes = (page.get("slideProperties") or {}).get("notesPage") or {}
    return "".join(element_text(e) for e in notes.get("pageElements", [])).strip()


def placeholder_type(el: dict) -> str:
    return ((el.get("shape") or {}).get("placeholder") or {}).get("type", "")


def slide_title(slide: dict) -> str:
    """First TITLE/CENTERED_TITLE placeholder, else the first non-empty text."""
    texts = []
    for el in slide.get("pageElements", []):
        text = element_text(el).strip()
        if not text or placeholder_type(el) == "SLIDE_NUMBER":
            continue
        if placeholder_type(el) in ("TITLE", "CENTERED_TITLE"):
            return text
        texts.append(text)
    return texts[0] if texts else ""


def presentation(pres: str, fields: str | None = None) -> dict:
    params = {"fields": fields} if fields else {}
    return api("GET", f"{SLIDES}/{extract_id(pres)}", params=params)


def resolve_page(deck: dict, ref: str) -> tuple[int, dict]:
    """`ref` is a 1-based slide number or a slide objectId."""
    slides = deck.get("slides", [])
    if ref.isdigit():
        index = int(ref)
        if not 1 <= index <= len(slides):
            sys.exit(f"error: slide {index} out of range (deck has {len(slides)})")
        return index, slides[index - 1]
    for i, slide in enumerate(slides, 1):
        if slide["objectId"] == ref:
            return i, slide
    sys.exit(f"error: no slide {ref!r} in this presentation")


def cmd_slides_outline(a):
    deck = presentation(a.pres, OUTLINE_FIELDS)
    layouts = {l["objectId"]: l.get("layoutProperties", {}).get("displayName", "?")
               for l in deck.get("layouts", [])}
    rows = [["#", "OBJECT_ID", "LAYOUT", "EL", "TITLE / FIRST TEXT", "NOTES"]]
    for i, slide in enumerate(deck.get("slides", []), 1):
        layout = layouts.get((slide.get("slideProperties") or {}).get("layoutObjectId"), "-")
        rows.append([
            i, slide["objectId"], trunc(layout, 22), len(slide.get("pageElements", [])),
            trunc(slide_title(slide), 60), trunc(notes_text(slide), 24),
        ])
    out(deck.get("slides", []), a.json,
        f"{deck.get('title')}  ({deck.get('presentationId')})  {len(deck.get('slides', []))} slides\n"
        + table(rows))


def cmd_slides_slide(a):
    deck = presentation(a.pres, "presentationId,title,slides(objectId),layouts(objectId,layoutProperties.displayName)")
    index, stub = resolve_page(deck, a.slide)
    page = api("GET", f"{SLIDES}/{extract_id(a.pres)}/pages/{stub['objectId']}")
    if a.json:
        return out(page, True)
    layouts = {l["objectId"]: l.get("layoutProperties", {}).get("displayName", "?")
               for l in deck.get("layouts", [])}
    layout = layouts.get((page.get("slideProperties") or {}).get("layoutObjectId"), "-")
    print(f"slide {index}  objectId={page['objectId']}  layout={layout}  "
          f"elements={len(page.get('pageElements', []))}")
    for el in page.get("pageElements", []):
        ph = ((el.get("shape") or {}).get("placeholder") or {})
        # `type` is omitted from the JSON when it is the NONE default (inherited placeholders)
        label = f" placeholder={ph.get('type', 'NONE')}" + (f"#{ph['index']}" if ph.get("index") else "") if ph else ""
        print(f"\n  [{el['objectId']}] {element_kind(el)}{label}")
        if "table" in el:
            t = el["table"]
            print(f"    table {t.get('rows')}x{t.get('columns')}")
            for row in t.get("tableRows", []):
                cells = ["".join(
                    (te.get("textRun") or {}).get("content", "")
                    for te in (c.get("text") or {}).get("textElements", [])).strip()
                    for c in row.get("tableCells", [])]
                print("    | " + " | ".join(trunc(c, 30) for c in cells))
            continue
        if "image" in el:
            print(f"    contentUrl: {el['image'].get('contentUrl', '')[:160]}")
        text = element_text(el).replace("\v", "\n").rstrip()
        if text:
            body = text if len(text) <= a.max_chars else text[: a.max_chars] + "\n    …[truncated]"
            print("\n".join(f"    {line}" for line in body.split("\n")))
    notes = (page.get("slideProperties") or {}).get("notesPage") or {}
    notes_id = (notes.get("notesProperties") or {}).get("speakerNotesObjectId")
    body = notes_text(page)
    print(f"\n  notes [{notes_id}]: {body if body else '(none)'}")


def cmd_slides_text(a):
    deck = presentation(a.pres, "title,slides(objectId,pageElements,slideProperties.notesPage(pageElements))")
    slides = deck.get("slides", [])
    start, end = a.from_ or 1, a.to or len(slides)
    lines = [f"# {deck.get('title')}", ""]
    for i, slide in enumerate(slides[start - 1:end], start):
        lines.append(f"## Slide {i} — {slide_title(slide) or '(no title)'}   `{slide['objectId']}`")
        for el in slide.get("pageElements", []):
            if placeholder_type(el) == "SLIDE_NUMBER":
                continue
            text = element_text(el).replace("\v", "\n").strip()
            for line in (l.strip() for l in text.split("\n")):
                if line:
                    lines.append(f"- {line}")
        notes = notes_text(slide)
        if notes:
            lines.append(f"> notes: {notes}")
        lines.append("")
    body = "\n".join(lines)
    if a.out:
        print(f"wrote {write_out(a.out, body)}")
    else:
        print(body)


def cmd_slides_replace(a):
    req: dict = {"replaceAllText": {
        "containsText": {"text": a.find, "matchCase": bool(a.match_case)},
        "replaceText": a.replace}}
    if a.slides:
        req["replaceAllText"]["pageObjectIds"] = [s.strip() for s in a.slides.split(",") if s.strip()]
    res = api("POST", f"{SLIDES}/{extract_id(a.pres)}:batchUpdate", json={"requests": [req]})
    n = res["replies"][0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    out(res, a.json, f"replaced {n} occurrence(s)")


def cmd_slides_set_text(a):
    # No API keeps the old run styling: deleteText(ALL) drops it, the new run inherits
    # the shape/placeholder defaults. Restyle explicitly afterwards if it matters.
    requests: list[dict] = []
    if a.text:
        requests.append({"deleteText": {"objectId": a.element, "textRange": {"type": "ALL"}}})
        requests.append({"insertText": {"objectId": a.element, "insertionIndex": 0, "text": a.text}})
    else:
        requests.append({"deleteText": {"objectId": a.element, "textRange": {"type": "ALL"}}})
    res = api("POST", f"{SLIDES}/{extract_id(a.pres)}:batchUpdate", json={"requests": requests})
    out(res, a.json, f"set text on {a.element} ({len(a.text)} chars)")


def cmd_slides_batch(a):
    res = api("POST", f"{SLIDES}/{extract_id(a.pres)}:batchUpdate", json=requests_body(a.body))
    report_replies(res, a.json)


def cmd_slides_thumbnail(a):
    deck = presentation(a.pres, "slides(objectId)")
    index, slide = resolve_page(deck, a.slide)
    meta = api("GET", f"{SLIDES}/{extract_id(a.pres)}/pages/{slide['objectId']}/thumbnail",
               params={"thumbnailProperties.thumbnailSize": "LARGE",
                       "thumbnailProperties.mimeType": "PNG"})
    url = meta.get("contentUrl")
    if not url:
        sys.exit(f"error: Slides returned no thumbnail contentUrl for slide {index}")
    png = httpx.get(url, timeout=120)  # pre-signed, no Authorization header
    if not png.is_success:
        sys.exit(f"error: thumbnail download failed ({png.status_code})")
    out({"slide": index, "objectId": slide["objectId"], "out": a.out}, a.json,
        f"slide {index} -> {write_out(a.out, png.content)}")


def cmd_slides_export_pdf(a):
    r = request("GET", f"{DRIVE}/files/{extract_id(a.pres)}/export",
                params={"mimeType": "application/pdf"})
    out({"out": a.out, "bytes": len(r.content)}, a.json, f"exported -> {write_out(a.out, r.content)}")



# --- slides: structure edits (add / notes / delete / move) -------------------

LAYOUT_FIELDS = "layouts(objectId,layoutProperties.displayName,layoutProperties.name,pageElements(objectId,shape(placeholder)))"
TITLE_TYPES = ("TITLE", "CENTERED_TITLE")
BODY_TYPES = ("BODY", "SUBTITLE")


def find_layout(deck: dict, name: str) -> dict:
    """Match a layout by display name ("Title and body"), API name (TITLE_AND_BODY) or objectId."""
    wanted = name.strip().lower()
    for layout in deck.get("layouts", []):
        props = layout.get("layoutProperties", {})
        if wanted in (layout["objectId"].lower(), props.get("displayName", "").lower(), props.get("name", "").lower()):
            return layout
    names = ", ".join(l.get("layoutProperties", {}).get("displayName", "?") for l in deck.get("layouts", []))
    sys.exit(f"error: no layout {name!r}; this deck has: {names}")


def layout_placeholder(layout: dict, types: tuple[str, ...]) -> dict | None:
    for el in layout.get("pageElements", []):
        ph = ((el.get("shape") or {}).get("placeholder") or {})
        if ph.get("type") in types:
            return {"type": ph["type"], "index": ph.get("index", 0)}
    return None


def run_colors(pres_id: str, slide_id: str) -> dict[str, dict]:
    """Foreground colour of the first text run in the TITLE and BODY placeholders of a slide.
    Decks usually carry their colours as explicit run styles, which a fresh placeholder
    (layout defaults) does not inherit; copying them keeps new slides visually consistent."""
    page = api("GET", f"{SLIDES}/{pres_id}/pages/{slide_id}",
               params={"fields": "pageElements(shape(placeholder,text(textElements(textRun(style)))))"})
    colors: dict[str, dict] = {}
    for el in page.get("pageElements", []):
        kind = placeholder_type(el)
        key = "title" if kind in TITLE_TYPES else "body" if kind in BODY_TYPES else None
        if not key or key in colors:
            continue
        for te in (el["shape"].get("text") or {}).get("textElements", []):
            color = ((te.get("textRun") or {}).get("style") or {}).get("foregroundColor")
            if color:
                colors[key] = color
                break
    return colors


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def slide_requests(layout: dict, spec: dict, insertion_index: int, colors: dict | None = None) -> tuple[str, list[dict]]:
    """createSlide + fill TITLE/BODY placeholders. Body lines become bullets; leading
    tabs = nesting level (that is how the API decides bullet depth). Single-paragraph
    bodies stay plain unless `bullets` is forced."""
    slide_id = new_id("s")
    mappings, requests = [], []
    title, body = spec.get("title"), spec.get("body")
    title_ph = layout_placeholder(layout, TITLE_TYPES) if title else None
    # drop_body: instantiate the layout's body placeholder only to delete it (keeps the layout's
    # title position/logo while leaving a clean canvas for hand-placed shapes).
    drop_body = bool(spec.get("drop_body")) and not body
    body_ph = layout_placeholder(layout, BODY_TYPES) if (body or drop_body) else None
    title_id = body_id = None
    if title and not title_ph:
        sys.exit(f"error: layout {layout['layoutProperties'].get('displayName')!r} has no title placeholder")
    if body and not body_ph:
        sys.exit(f"error: layout {layout['layoutProperties'].get('displayName')!r} has no body placeholder")
    if title_ph:
        title_id = new_id("t")
        mappings.append({"layoutPlaceholder": title_ph, "objectId": title_id})
    if body_ph:
        body_id = new_id("b")
        mappings.append({"layoutPlaceholder": body_ph, "objectId": body_id})
    requests.append({"createSlide": {
        "objectId": slide_id, "insertionIndex": insertion_index,
        "slideLayoutReference": {"layoutId": layout["objectId"]},
        "placeholderIdMappings": mappings}})
    colors = colors or {}
    if title_id:
        requests.append({"insertText": {"objectId": title_id, "insertionIndex": 0, "text": title}})
        if colors.get("title"):
            requests.append({"updateTextStyle": {"objectId": title_id, "textRange": {"type": "ALL"},
                                                 "style": {"foregroundColor": colors["title"]}, "fields": "foregroundColor"}})
    if body_id and drop_body:
        requests.append({"deleteObject": {"objectId": body_id}})
    elif body_id:
        requests.append({"insertText": {"objectId": body_id, "insertionIndex": 0, "text": body}})
        if colors.get("body"):
            requests.append({"updateTextStyle": {"objectId": body_id, "textRange": {"type": "ALL"},
                                                 "style": {"foregroundColor": colors["body"]}, "fields": "foregroundColor"}})
        bullets = spec.get("bullets", "\n" in body.strip())
        if bullets:
            requests.append({"createParagraphBullets": {
                "objectId": body_id, "textRange": {"type": "ALL"},
                "bulletPreset": spec.get("bullet_preset", "BULLET_DISC_CIRCLE_SQUARE")}})
    return slide_id, requests


def set_notes(pres_id: str, slide_id: str, text: str) -> None:
    page = api("GET", f"{SLIDES}/{pres_id}/pages/{slide_id}",
               params={"fields": "slideProperties.notesPage(notesProperties,pageElements)"})
    notes = (page.get("slideProperties") or {}).get("notesPage") or {}
    notes_id = (notes.get("notesProperties") or {}).get("speakerNotesObjectId")
    if not notes_id:
        sys.exit(f"error: slide {slide_id} has no speaker-notes shape")
    requests = []
    if notes_text(page):
        requests.append({"deleteText": {"objectId": notes_id, "textRange": {"type": "ALL"}}})
    if text:
        requests.append({"insertText": {"objectId": notes_id, "insertionIndex": 0, "text": text}})
    if requests:
        api("POST", f"{SLIDES}/{pres_id}:batchUpdate", json={"requests": requests})


def cmd_slides_add(a):
    pres_id = extract_id(a.pres)
    if a.spec:
        specs = read_body(a.spec)
        if isinstance(specs, dict):
            specs = [specs]
    else:
        if not (a.title or a.body):
            sys.exit("error: pass --title/--body or --spec FILE")
        specs = [{"layout": a.layout, "title": a.title, "body": a.body, "notes": a.notes}]
    deck = presentation(pres_id, "slides(objectId)," + LAYOUT_FIELDS)
    after = len(deck.get("slides", [])) if a.after in (None, "end") else resolve_page(deck, a.after)[0]
    like = a.like or (a.after if a.after not in (None, "end") else None)
    colors = run_colors(pres_id, resolve_page(deck, like)[1]["objectId"]) if like and like != "none" else {}
    requests, created = [], []
    for i, spec in enumerate(specs):
        layout = find_layout(deck, spec.get("layout") or a.layout)
        slide_id, reqs = slide_requests(layout, spec, after + i, colors)
        requests.extend(reqs)
        created.append((slide_id, spec))
    api("POST", f"{SLIDES}/{pres_id}:batchUpdate", json={"requests": requests})
    for slide_id, spec in created:
        if spec.get("notes"):
            set_notes(pres_id, slide_id, spec["notes"])
    out([{"objectId": sid, "position": after + i + 1, "title": sp.get("title")} for i, (sid, sp) in enumerate(created)],
        a.json, "\n".join(f"slide {after + i + 1}  {sid}  {trunc(sp.get('title') or '', 60)}" for i, (sid, sp) in enumerate(created)))


def cmd_slides_notes(a):
    deck = presentation(a.pres, "slides(objectId)")
    index, slide = resolve_page(deck, a.slide)
    set_notes(extract_id(a.pres), slide["objectId"], a.text or "")
    out({"slide": index, "objectId": slide["objectId"]}, a.json, f"notes set on slide {index} ({len(a.text or '')} chars)")


def cmd_slides_delete(a):
    deck = presentation(a.pres, "slides(objectId)")
    targets = [resolve_page(deck, ref) for ref in a.slides]
    if not a.yes:
        listing = ", ".join(f"{i} ({s['objectId']})" for i, s in targets)
        sys.exit(f"refusing without --yes: would delete slide(s) {listing}")
    requests = [{"deleteObject": {"objectId": s["objectId"]}} for _, s in targets]
    api("POST", f"{SLIDES}/{extract_id(a.pres)}:batchUpdate", json={"requests": requests})
    out([s["objectId"] for _, s in targets], a.json, f"deleted {len(targets)} slide(s)")


def cmd_slides_move(a):
    deck = presentation(a.pres, "slides(objectId)")
    ids = [resolve_page(deck, ref)[1]["objectId"] for ref in a.slides]
    # updateSlidesPosition's insertionIndex is a 0-based position in the deck *before* the move,
    # moved slides still counted. "Become slide N" = exactly N-1 non-moved slides precede the
    # block, so insert right after the (N-1)th non-moved slide of the current arrangement.
    moved = set(ids)
    insertion, seen = 0, 0
    for i, s in enumerate(deck["slides"], 1):
        if seen == a.to - 1:
            break
        if s["objectId"] not in moved:
            seen += 1
            insertion = i
    api("POST", f"{SLIDES}/{extract_id(a.pres)}:batchUpdate",
        json={"requests": [{"updateSlidesPosition": {"slideObjectIds": ids, "insertionIndex": insertion}}]})
    out({"moved": ids, "to": a.to}, a.json, f"moved {len(ids)} slide(s) to position {a.to}")


# --- slides: images ---------------------------------------------------------

EMU_PER_PT = 12700


def _create_image(pres_id: str, req: dict) -> tuple[bool, Any]:
    """createImage without api()'s sys.exit, so the caller can retry after opening up access."""
    r = client().request("POST", f"{SLIDES}/{pres_id}:batchUpdate", json={"requests": [req]})
    return (True, r.json()) if r.is_success else (False, r.text)


def scale_image(pres_id: str, page_id: str, img_id: str, w_pt: float | None, h_pt: float | None,
                x_pt: float, y_pt: float) -> None:
    """Uniformly scale a natural-size image to the one given dimension (aspect ratio kept)."""
    page = api("GET", f"{SLIDES}/{pres_id}/pages/{page_id}", params={"fields": "pageElements(objectId,size)"})
    natural = next((e.get("size") for e in page.get("pageElements", []) if e["objectId"] == img_id), None)
    if not natural:
        return
    target = (w_pt or h_pt) * EMU_PER_PT
    scale = target / natural["width" if w_pt else "height"]["magnitude"]
    api("POST", f"{SLIDES}/{pres_id}:batchUpdate", json={"requests": [{"updatePageElementTransform": {
        "objectId": img_id, "applyMode": "ABSOLUTE",
        "transform": {"scaleX": scale, "scaleY": scale, "unit": "EMU",
                      "translateX": x_pt * EMU_PER_PT, "translateY": y_pt * EMU_PER_PT}}}]})


def cmd_slides_image(a):
    pres_id = extract_id(a.pres)
    index, slide = resolve_page(presentation(pres_id, "slides(objectId)"), a.slide)
    url, file_id = a.url, None
    if a.file:
        parent = a.parent
        if not parent:  # default: drop the image next to the deck itself
            parent = next(iter(api("GET", f"{DRIVE}/files/{pres_id}", params={"fields": "parents"}).get("parents") or []), None)
        file_id = drive_upload(a.file, a.name, parent)["id"]
        url = f"https://drive.google.com/uc?id={file_id}"
    props = {"pageObjectId": slide["objectId"],
             "transform": {"scaleX": 1, "scaleY": 1, "unit": "EMU",
                           "translateX": a.x * EMU_PER_PT, "translateY": a.y * EMU_PER_PT}}
    # `size` needs both dimensions (a half-filled one fails as "Unknown dimension unit
    # UNIT_UNSPECIFIED"). With only --w or only --h we create at natural size and rescale after.
    if a.w and a.h:
        props["size"] = {"width": {"magnitude": a.w * EMU_PER_PT, "unit": "EMU"},
                         "height": {"magnitude": a.h * EMU_PER_PT, "unit": "EMU"}}
    img_id = new_id("img")
    req = {"createImage": {"objectId": img_id, "url": url, "elementProperties": props}}
    ok, res = _create_image(pres_id, req)
    if not ok and file_id:
        # Slides fetches the URL itself, without our credentials, so a private Drive file is
        # invisible to it — in practice this always fires for a fresh upload. Open it up for the
        # duration of the call only (Slides copies the pixels into the deck).
        perm = api("POST", f"{DRIVE}/files/{file_id}/permissions", json={"role": "reader", "type": "anyone"})
        try:
            ok, res = _create_image(pres_id, req)
        finally:
            request("DELETE", f"{DRIVE}/files/{file_id}/permissions/{perm['id']}")
    if not ok:
        sys.exit(f"Google API error on createImage: {res}")
    if not (a.w and a.h):
        scale_image(pres_id, slide["objectId"], img_id, a.w or (None if a.h else 660), a.h, a.x, a.y)
    out({"objectId": img_id, "slide": index, "driveFileId": file_id}, a.json,
        f"image {img_id} on slide {index}" + (f" (drive file {file_id})" if file_id else ""))


# --- argparse ---------------------------------------------------------------

def main() -> None:
    g = argparse.ArgumentParser(add_help=False)
    g.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="raw API JSON")

    p = argparse.ArgumentParser(
        description=f"Google Workspace CLI as {EXPECTED_EMAIL} (Drive/Docs/Sheets/Slides{'/Gmail' if 'gmail' in FEATURES else ''}).",
        parents=[g],
    )
    sub = p.add_subparsers(dest="cmd", required=True,
                           parser_class=lambda **kw: argparse.ArgumentParser(parents=[g], **kw))

    def add(name: str, fn, help_: str):
        s = sub.add_parser(name, help=help_, description=help_)
        s.set_defaults(fn=fn)
        return s

    add("whoami", cmd_whoami, "show the authenticated Google account")
    add("token", cmd_token, "print the short-lived access token (for ad-hoc curl)")

    s = add("api", cmd_api, "authenticated raw call; path may be a full URL or e.g. /drive/v3/files")
    s.add_argument("method")
    s.add_argument("url")
    s.add_argument("--body", help="JSON request body: FILE or - for stdin")
    s.add_argument("--param", action="append", metavar="k=v", help="query parameter (repeatable)")

    s = add("drive-list", cmd_drive_list, "list a Drive folder")
    s.add_argument("folder")
    s.add_argument("-n", "--max", type=int, default=100)

    s = add("drive-search", cmd_drive_search, "search Drive (Drive query syntax)")
    s.add_argument("query")
    s.add_argument("-n", "--max", type=int, default=50)

    s = add("drive-get", cmd_drive_get, "file metadata")
    s.add_argument("file")

    s = add("drive-copy", cmd_drive_copy, "copy a file (use before risky bulk edits)")
    s.add_argument("file")
    s.add_argument("--name", required=True)
    s.add_argument("--parent", help="target folder id/url (default: same parents)")

    if "upload" in FEATURES:
        s = add("drive-upload", cmd_drive_upload, "upload a local file to Drive (multipart)")
        s.add_argument("file", help="local path")
        s.add_argument("--name", help="Drive name (default: the file name)")
        s.add_argument("--parent", help="target folder id/url (default: My Drive root)")
        s.add_argument("--mime", help="MIME type (default: guessed)")

    s = add("drive-trash", cmd_drive_trash, "move a file to the trash (never permanent)")
    s.add_argument("file")

    s = add("drive-export", cmd_drive_export, "export a Google file to a local path")
    s.add_argument("file")
    s.add_argument("--format", required=True, help="/".join(sorted(EXPORT_MIME)))
    s.add_argument("--out", required=True)

    s = add("doc-read", cmd_doc_read, "export a Google Doc as Markdown")
    s.add_argument("doc")
    s.add_argument("--out")

    s = add("doc-outline", cmd_doc_outline, "structural elements with indexes (find edit positions)")
    s.add_argument("doc")

    s = add("doc-replace", cmd_doc_replace, "replaceAllText in a Doc")
    s.add_argument("doc")
    s.add_argument("--find", required=True)
    s.add_argument("--replace", required=True)
    s.add_argument("--match-case", action="store_true")

    s = add("doc-insert", cmd_doc_insert, "insert text at an index or at the end")
    s.add_argument("doc")
    s.add_argument("--text", required=True)
    s.add_argument("--index", type=int)
    s.add_argument("--end", action="store_true")

    s = add("doc-batch", cmd_doc_batch, "raw documents.batchUpdate")
    s.add_argument("doc")
    s.add_argument("--body", required=True, help="FILE or -")

    s = add("sheet-meta", cmd_sheet_meta, "spreadsheet + tab metadata")
    s.add_argument("sheet")

    s = add("sheet-read", cmd_sheet_read, "read an A1 range")
    s.add_argument("sheet")
    s.add_argument("range")

    s = add("sheet-write", cmd_sheet_write, "write an A1 range (USER_ENTERED)")
    s.add_argument("sheet")
    s.add_argument("range")
    s.add_argument("--values", help="JSON array of arrays")
    s.add_argument("--csv", help="CSV file instead of --values")

    s = add("sheet-append", cmd_sheet_append, "append rows below a tab's data")
    s.add_argument("sheet")
    s.add_argument("range", help="tab name or A1 range")
    s.add_argument("--values")
    s.add_argument("--csv")

    s = add("sheet-batch", cmd_sheet_batch, "raw spreadsheets.batchUpdate")
    s.add_argument("sheet")
    s.add_argument("--body", required=True, help="FILE or -")

    if "gmail" in FEATURES:
        s = add("gmail-search", cmd_gmail_search, "search Gmail; one compact line per message")
        s.add_argument("query", help="Gmail search query")
        s.add_argument("-n", "--max", type=int, default=25)

        s = add("gmail-get", cmd_gmail_get, "message headers, compact text body and attachments")
        s.add_argument("id", help="message id")
        s.add_argument("--max-chars", type=int, default=12000)

        s = add("gmail-thread", cmd_gmail_thread, "all messages in a thread, compacted")
        s.add_argument("id", help="thread id")
        s.add_argument("--max-chars", type=int, default=12000)

        s = add("gmail-draft", cmd_gmail_draft, "create a draft (never sends)")
        s.add_argument("--to", required=True)
        s.add_argument("--subject", required=True)
        s.add_argument("--body", required=True, help="UTF-8 body: FILE or -")
        s.add_argument("--reply-to-message", help="message id to thread and quote; subject must match")
        s.add_argument("--html", action="store_true", help="body is HTML; also create a plain-text alternative")

        add("gmail-labels", cmd_gmail_labels, "list Gmail labels and ids")

        s = add("gmail-label", cmd_gmail_label, "add/remove labels on a message")
        s.add_argument("id", help="message id")
        s.add_argument("--add", action="append", help="label id/name (repeatable or comma-separated)")
        s.add_argument("--remove", action="append", help="label id/name (repeatable or comma-separated)")

    s = add("slides-outline", cmd_slides_outline, "one compact line per slide")
    s.add_argument("pres")

    s = add("slides-slide", cmd_slides_slide, "every element + notes of one slide")
    s.add_argument("pres")
    s.add_argument("slide", help="1-based slide number or objectId")
    s.add_argument("--max-chars", type=int, default=2000)

    s = add("slides-text", cmd_slides_text, "markdown-ish dump of all slide text")
    s.add_argument("pres")
    s.add_argument("--from", dest="from_", type=int)
    s.add_argument("--to", type=int)
    s.add_argument("--out")

    s = add("slides-replace", cmd_slides_replace, "replaceAllText across (some) slides")
    s.add_argument("pres")
    s.add_argument("--find", required=True)
    s.add_argument("--replace", required=True)
    s.add_argument("--slides", help="comma-separated slide objectIds (default: whole deck)")
    s.add_argument("--match-case", action="store_true")

    s = add("slides-set-text", cmd_slides_set_text, "replace a shape's whole text (styling is lost)")
    s.add_argument("pres")
    s.add_argument("element", help="page element objectId (see slides-slide)")
    s.add_argument("--text", required=True)

    s = add("slides-batch", cmd_slides_batch, "raw presentations.batchUpdate")
    s.add_argument("pres")
    s.add_argument("--body", required=True, help="FILE or -")

    s = add("slides-add", cmd_slides_add, "insert new slide(s) after a slide; --spec = JSON list of {layout,title,body,notes}")
    s.add_argument("pres")
    s.add_argument("--after", help="1-based slide number or objectId; default: end of deck")
    s.add_argument("--layout", default="Title and body", help="layout display name / API name / id")
    s.add_argument("--title")
    s.add_argument("--body", help="lines become bullets; leading tabs nest")
    s.add_argument("--notes", help="speaker notes")
    s.add_argument("--spec", help="JSON FILE or - : one object or a list, inserted in order")
    s.add_argument("--like", help="copy title/body text colours from this slide (default: the --after slide; 'none' to skip)")

    s = add("slides-notes", cmd_slides_notes, "replace a slide's speaker notes")
    s.add_argument("pres")
    s.add_argument("slide", help="1-based slide number or objectId")
    s.add_argument("--text", required=True, help="new notes ('' clears)")

    s = add("slides-delete", cmd_slides_delete, "delete slide(s) (needs --yes)")
    s.add_argument("pres")
    s.add_argument("slides", nargs="+", help="1-based numbers or objectIds")
    s.add_argument("--yes", action="store_true")

    s = add("slides-move", cmd_slides_move, "move slide(s) so the first becomes slide N")
    s.add_argument("pres")
    s.add_argument("slides", nargs="+", help="1-based numbers or objectIds")
    s.add_argument("--to", type=int, required=True, help="target 1-based position")

    if "images" in FEATURES:
        s = add("slides-image", cmd_slides_image, "insert an image on a slide (local file or public URL)")
        s.add_argument("pres")
        s.add_argument("slide", help="1-based slide number or objectId")
        g2 = s.add_mutually_exclusive_group(required=True)
        g2.add_argument("--file", help="local image; uploaded to Drive first")
        g2.add_argument("--url", help="publicly fetchable image URL")
        s.add_argument("--x", type=float, default=30, help="left offset in pt (slide is 720x405 pt)")
        s.add_argument("--y", type=float, default=110, help="top offset in pt")
        s.add_argument("--w", type=float, help="width in pt (default 660 if no --h)")
        s.add_argument("--h", type=float, help="height in pt; give only one of --w/--h to keep the ratio")
        s.add_argument("--name", help="Drive name for the uploaded image")
        s.add_argument("--parent", help="Drive folder for the upload (default: the deck's own folder)")

    s = add("slides-thumbnail", cmd_slides_thumbnail, "render one slide to PNG (LARGE)")
    s.add_argument("pres")
    s.add_argument("slide", help="1-based slide number or objectId")
    s.add_argument("--out", required=True)

    s = add("slides-export-pdf", cmd_slides_export_pdf, "export the whole deck to PDF")
    s.add_argument("pres")
    s.add_argument("--out", required=True)

    a = p.parse_args()
    a.json = getattr(a, "json", False)
    if getattr(a, "values", None) is None and getattr(a, "csv", None) is None and a.cmd in ("sheet-write", "sheet-append"):
        sys.exit("error: pass --values or --csv")
    try:
        a.fn(a)
    except httpx.RequestError as exc:
        sys.exit(f"error: network failure talking to Google: {exc}")
    except BrokenPipeError:  # `| head` is a normal way to use this CLI
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except (OSError, ValueError) as exc:
        sys.exit(f"error: {exc}")
    finally:
        if CLIENT is not None:
            CLIENT.close()

