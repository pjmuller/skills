"""Parsing of user-supplied ids, files and JSON payloads."""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .errors import WorkspaceError

ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def extract_id(value: str) -> str:
    """Accept a bare id or any Google URL (/d/<id>/…, /folders/<id>, ?id=<id>)."""
    candidate = str(value).strip()
    if "/" in candidate:  # bare ids never contain "/", so a scheme is optional
        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        by_query = parse_qs(parsed.query).get("id", [])
        if by_query:
            candidate = by_query[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            for marker in ("d", "folders"):
                if marker in parts and parts.index(marker) + 1 < len(parts):
                    candidate = parts[parts.index(marker) + 1]
                    break
    if candidate == "root":
        return candidate
    if not ID_RE.fullmatch(candidate):
        raise WorkspaceError(f"no Google file id found in {value!r}")
    return candidate


def read_text(source: str) -> str:
    """FILE or - for stdin."""
    if source == "-":
        return sys.stdin.read()
    try:
        return Path(source).expanduser().read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise WorkspaceError(f"cannot read UTF-8 file {source!r}: {exc}") from exc


def read_json(source: str) -> Any:
    raw = read_text(source)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkspaceError(f"{source} is not valid JSON: {exc}") from exc


def read_requests(source: str) -> dict:
    """batchUpdate body: accept a bare list of requests or the full {requests:[…]}."""
    body = read_json(source)
    return body if isinstance(body, dict) else {"requests": body}


def parse_json_arg(value: str, what: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise WorkspaceError(f"{what} is not valid JSON: {exc}") from exc


def parse_values(values: str | None, csv_path: str | None) -> list[list]:
    """Sheet values from a JSON array of arrays (or inline JSON) or a CSV file."""
    if csv_path:
        with Path(csv_path).expanduser().open(encoding="utf-8", newline="") as handle:
            return list(csv.reader(handle))
    if values is None:
        raise WorkspaceError("pass --values or --csv")
    parsed = parse_json_arg(values, "--values")
    if not isinstance(parsed, list) or not all(isinstance(row, list) for row in parsed):
        raise WorkspaceError("--values must be a JSON array of arrays")
    return parsed


def protected_write(path: Path, content: str, overwrite: bool) -> Path:
    """Owner-only output that refuses to follow a symlink or clobber without --force."""
    target = Path(path).expanduser()
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise WorkspaceError(f"output exists: {target}; pass --force to replace it") from exc
    except OSError as exc:
        raise WorkspaceError(f"cannot write {target}: {exc}") from exc
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
    return target.resolve()
