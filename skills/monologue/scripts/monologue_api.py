#!/usr/bin/env python3
# /// script
# dependencies = ["requests>=2.31,<3"]
# ///
"""Read-only Monologue API and Markdown helpers; project policy stays in callers."""
from __future__ import annotations

import argparse
import math
import os
import re
from datetime import date, datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import requests

API_BASE = "https://api.monologue.to/v1/public-api"
PAGE_SIZE = 100
PREVIEW_CHARS = 300


class MonologueError(RuntimeError):
    pass


def api_get(path: str, params: dict | None = None) -> dict:
    key = os.getenv("MONOLOGUE_API_KEY")
    if not key:
        raise MonologueError("MONOLOGUE_API_KEY unavailable; run through mise")
    try:
        response = requests.get(
            f"{API_BASE}{path}", params=params,
            headers={"Authorization": f"Bearer {key}"}, timeout=30,
        )
    except requests.RequestException as exc:
        raise MonologueError(f"Monologue request failed: {exc.__class__.__name__}") from None
    if response.status_code != 200:
        raise MonologueError(f"Monologue API returned HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise MonologueError("Monologue returned invalid JSON") from None
    if not isinstance(body, dict):
        raise MonologueError("Monologue returned an unexpected response")
    return body


def list_notes(day: date, query: str | None = None, tz=ZoneInfo("UTC"), *, get=api_get) -> list[dict]:
    start = datetime.combine(day, time.min, tz).astimezone(timezone.utc)
    end = datetime.combine(day.fromordinal(day.toordinal() + 1), time.min, tz).astimezone(timezone.utc)
    params = {
        "limit": PAGE_SIZE,
        "created_after": start.isoformat().replace("+00:00", "Z"),
        "created_before": end.isoformat().replace("+00:00", "Z"),
    }
    if query:
        params["q"] = query
    notes: list[dict] = []
    seen_ids: set[str] = set()
    seen_cursors: set[str] = set()
    while True:
        body = get("/notes", params)
        items = body.get("items")
        cursor = body.get("next_cursor")
        if not isinstance(items, list) or cursor is not None and not isinstance(cursor, str):
            raise MonologueError("Monologue returned an unexpected note list")
        for note in items:
            note_id = note.get("note_id") if isinstance(note, dict) else None
            if not isinstance(note_id, str) or not note_id:
                raise MonologueError("Monologue note list contains no ID")
            if note_id in seen_ids:
                raise MonologueError("Monologue pagination repeated a note")
            seen_ids.add(note_id)
            notes.append(note)
        if not cursor:
            return notes
        if cursor in seen_cursors:
            raise MonologueError("Monologue pagination repeated a cursor")
        seen_cursors.add(cursor)
        params["cursor"] = cursor


def get_note(note_id: str) -> dict:
    note_id = str(UUID(note_id))
    note = api_get(f"/notes/{note_id}")
    if note.get("note_id") != note_id:
        raise MonologueError("Monologue returned a different note UUID")
    return note


def recording_url(note: dict) -> str | None:
    """Temporary private URL, for immediate download only; never archive it."""
    url = note.get("recording_url")
    return url if isinstance(url, str) and url.startswith("https://") else None


def transcript_markdown(note: dict, speaker_names: dict[str, str] | None = None) -> str:
    """Render real seconds/speaker IDs, without guessing participant identity.

    Invalid structure fails closed: callers must not overwrite a good archive with
    a partially rendered transcript. Missing/empty segments use the flat text.
    """
    segments = note.get("transcript_segments")
    if not segments:
        text = note.get("transcript")
        return text.strip() if isinstance(text, str) else ""
    if not isinstance(segments, list):
        raise MonologueError("Unexpected transcript segments; archive not updated")
    names = {key: " ".join(value.split()) for key, value in (speaker_names or {}).items()
             if isinstance(value, str) and value.strip()}
    if len(names) != len(speaker_names or {}):
        raise MonologueError("Speaker names must be nonempty strings")
    first_names = [name.split()[0] for name in names.values()]
    turns = []
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
            raise MonologueError("Malformed transcript segment; archive not updated")
        text = segment["text"].strip()
        if not text:
            continue
        start = segment.get("start")
        end = segment.get("end")
        if (isinstance(start, bool) or not isinstance(start, (int, float))
                or not math.isfinite(start) or start < 0
                or isinstance(end, bool) or not isinstance(end, (int, float))
                or not math.isfinite(end) or end < start):
            raise MonologueError("Invalid transcript timing; archive not updated")
        seconds = int(start)
        stamp = f"{seconds // 60:02}:{seconds % 60:02}"
        speaker = segment.get("speaker_id")
        if speaker is None:
            speaker = "unknown speaker"
        elif not isinstance(speaker, str) or not re.fullmatch(r"[\w .-]+", speaker):
            raise MonologueError("Invalid speaker label; archive not updated")
        label = speaker
        if speaker in names:
            full_name = names[speaker]
            first = full_name.split()[0]
            label = full_name if first_names.count(first) > 1 else first
            label = re.sub(r"([\\`*_{}\[\]()#!|<>])", r"\\\1", label)
        turns.append(f"{stamp} {label}: {' '.join(text.split())}")
    if not turns and str(note.get("transcript") or "").strip():
        raise MonologueError("Empty segments but nonempty transcript; archive not updated")
    return "\n".join(turns)


def note_markdown(note: dict, speaker_names: dict[str, str] | None = None) -> str:
    """Generated sections only: preserve the caller's metadata/insights separately."""
    sections = []
    summary = note.get("summary")
    if isinstance(summary, str) and summary.strip():
        sections.append("## Monologue summary\n\n" + summary.strip())
    sections.append("## Transcript\n\n" + transcript_markdown(note, speaker_names))
    return "\n\n".join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("--date", required=True, type=date.fromisoformat)
    scan.add_argument("--timezone", default="UTC")
    scan.add_argument("--query")
    detail = commands.add_parser("get")
    detail.add_argument("note_id")
    args = parser.parse_args()
    try:
        if args.command == "get":
            print(note_markdown(get_note(args.note_id)))
        else:
            for note in list_notes(args.date, args.query, ZoneInfo(args.timezone)):
                print(note["note_id"], note.get("title") or "(untitled)")
    except (MonologueError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
