#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Download a ClickUp SyncUp's recording, AI notes and notetaker transcript.

    uv run syncup.py <chat message | chat channel | doc URL> [--out DIR] [--no-media]
    uv run syncup.py <chat channel URL> --list

Writes DIR (default /tmp/clickup-syncup-<doc_id>/, private, must be git-ignored inside a repo):
    source.json      workspace, channel, message, doc, media URLs, local files
    notes.md         the AI Notes page(s)
    transcript.md    ClickUp's "Meeting Transcript" page: untimed, possibly partial
    recording.<ext>  the call recording (audio-only for calls over ~1 h)

A channel URL resolves to its most recent SyncUp with AI notes. Needs only
CLICKUP_API_PERSONAL_TOKEN; the workspace comes from the URL, no clickup.toml.
Exit 75 (retry later) when the AI notes or recording link do not exist yet.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://api.clickup.com/api/v3/workspaces"
MSG_RE = re.compile(r"app\.clickup\.com/(\d+)/chat/r/([\w-]+)(?:/t/(\d+))?")
DOC_RE = re.compile(r"app\.clickup\.com/(\d+)/(?:docs|v/dc)/([\w]+-\d+)(?:/([\w]+-\d+))?")
MEDIA_RE = re.compile(r"https://[\w.-]*clickup-attachments\.com/[^\s)\]\"'<>]+?"
                      r"\.(mp4|webm|mov|mkv|m4a|mp3|aac|wav|ogg|opus)\b", re.I)
SCAN_LIMIT = 200  # recent channel messages inspected for SyncUps
EX_TEMPFAIL = 75
TRANSCRIPT_NOTE = ("> ClickUp's live notetaker transcript: no timestamps and possibly partial (cut off when the "
                   "notetaker stopped). For a complete timed transcript, transcribe recording.* locally.\n\n")


def parse_url(url: str) -> dict:
    if m := DOC_RE.search(url):
        return {"kind": "doc", "ws": m[1], "doc_id": m[2]}
    if m := MSG_RE.search(url):
        return {"kind": "message" if m[3] else "channel", "ws": m[1], "channel": m[2], "message_id": m[3]}
    raise ValueError(f"not a ClickUp chat or doc URL: {url}")


def get(path: str, token: str, **params) -> dict:
    for attempt in range(3):
        r = requests.get(f"{API}{path}", headers={"Authorization": token}, params=params, timeout=30)
        if r.status_code != 429 or attempt == 2:
            break
        time.sleep(min(30, 2 ** (attempt + 2)))
    if not r.ok:
        sys.exit(f"HTTP {r.status_code} on GET {path}\n{r.text[:500]}")
    return r.json()


def notes_doc(replies: list[dict]) -> tuple[str, str] | None:
    """(ws, doc_id) of the ClickUp AI bot's notes link; the bot posts as user -4."""
    for reply in sorted(replies, key=lambda r: r.get("user_id") != "-4"):
        if m := DOC_RE.search(reply.get("content") or ""):
            return m[1], m[2]
    return None


def recent_syncups(ws: str, channel: str, token: str):
    """Yield (message, (ws, doc_id) | None) for SyncUp root messages, newest first."""
    cursor, seen = None, 0
    while seen < SCAN_LIMIT:
        params = {"limit": 50, "content_format": "text/plain"} | ({"cursor": cursor} if cursor else {})
        page = get(f"/{ws}/chat/channels/{channel}/messages", token, **params)
        for msg in page.get("data", []):
            seen += 1
            if msg.get("replies_count") and "syncup" in (msg.get("content") or "").lower():
                replies = get(f"/{ws}/chat/messages/{msg['id']}/replies", token, content_format="text/md")
                yield msg, notes_doc(replies.get("data", []))
        cursor = page.get("next_cursor")
        if not cursor:
            return


def split_pages(pages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Flatten nested pages; the notetaker transcript page is named 'Meeting Transcript'."""
    flat, stack = [], list(reversed(pages))
    while stack:
        p = stack.pop()
        flat.append(p)
        stack.extend(reversed(p.get("pages") or []))
    transcript = [p for p in flat if "transcript" in (p.get("name") or "").lower()]
    return [p for p in flat if p not in transcript], transcript


def media_links(text: str) -> list[tuple[str, str]]:
    return list(dict.fromkeys((m[0], m[1].lower()) for m in MEDIA_RE.finditer(text or "")))


def render(pages: list[dict]) -> str:
    return "\n\n".join(f"# {p.get('name') or p['id']}\n\n{(p.get('content') or '').strip()}" for p in pages) + "\n"


def download(url: str, dest: Path, token: str) -> None:
    """Attachment URLs are normally pre-signed; only a 401/403 earns a retry with the token."""
    for headers in ({}, {"Authorization": token}):
        r = requests.get(url, headers=headers, stream=True, timeout=60)
        if r.status_code not in (401, 403):
            break
    r.raise_for_status()
    part = dest.with_suffix(dest.suffix + ".part")
    with part.open("wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    part.rename(dest)


def private_dir(out: Path) -> Path:
    out = out.expanduser().resolve()
    os.umask(0o077)
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    in_git = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=out, capture_output=True).returncode == 0
    if in_git and subprocess.run(["git", "check-ignore", "-q", str(out / "source.json")], cwd=out).returncode:
        sys.exit(f"{out} is inside a git work tree and not ignored; add it to .git/info/exclude first")
    return out


def iso(ms) -> str | None:
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).isoformat(timespec="seconds") if ms else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("url", help="ClickUp chat message, chat channel or doc URL")
    ap.add_argument("--out", type=Path, help="output dir (default /tmp/clickup-syncup-<doc_id>)")
    ap.add_argument("--no-media", action="store_true", help="skip the recording download")
    ap.add_argument("--list", action="store_true", help="channel URL: print recent SyncUps as JSON lines")
    a = ap.parse_args()
    token = os.environ.get("CLICKUP_API_PERSONAL_TOKEN", "").strip()
    if not token:
        sys.exit("CLICKUP_API_PERSONAL_TOKEN missing (raw pk_ personal token)")
    try:
        src = parse_url(a.url)
    except ValueError as exc:
        sys.exit(str(exc))
    ws = src["ws"]
    if a.list:
        if src["kind"] != "channel":
            sys.exit("--list needs a chat channel URL")
        for msg, doc in recent_syncups(ws, src["channel"], token):
            print(json.dumps({"date": iso(msg.get("date")), "message_id": msg["id"],
                              "doc_url": doc and f"https://app.clickup.com/{doc[0]}/docs/{doc[1]}"}))
        return
    if src["kind"] == "message":
        replies = get(f"/{ws}/chat/messages/{src['message_id']}/replies", token, content_format="text/md")
        doc = notes_doc(replies.get("data", []))
    elif src["kind"] == "channel":
        msg, doc = next(((m, d) for m, d in recent_syncups(ws, src["channel"], token) if d), (None, None))
        src["message_id"] = msg and msg["id"]
    else:
        doc = (ws, src["doc_id"])
    if not doc:
        print("no AI Notes reply found yet (notes arrive a few minutes after the call); retry later", file=sys.stderr)
        sys.exit(EX_TEMPFAIL)
    ws, doc_id = doc
    meta = get(f"/{ws}/docs/{doc_id}", token)
    notes, transcript = split_pages(get(f"/{ws}/docs/{doc_id}/pages", token, content_format="text/md"))
    out = private_dir(a.out or Path(f"/tmp/clickup-syncup-{doc_id}"))
    (out / "notes.md").write_text(render(notes))
    if transcript:
        (out / "transcript.md").write_text(TRANSCRIPT_NOTE + render(transcript))
    media = media_links("\n".join(p.get("content") or "" for p in notes))
    files = []
    if not a.no_media:
        for i, (url, ext) in enumerate(media, 1):
            dest = out / f"recording{'' if i == 1 else f'-{i}'}.{ext}"
            if not dest.exists():
                download(url, dest, token)
            files.append(dest.name)
    summary = {"workspace_id": ws, "channel_id": src.get("channel"), "message_id": src.get("message_id"),
               "doc_id": doc_id, "doc_url": f"https://app.clickup.com/{ws}/docs/{doc_id}", "doc_name": meta.get("name"),
               "doc_created": iso(meta.get("date_created")), "media_urls": [u for u, _ in media],
               "files": ["notes.md"] + (["transcript.md"] if transcript else []) + files, "dir": str(out)}
    (out / "source.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not media and not a.no_media:
        print("no recording link in the notes yet (ClickUp transcodes 5-10 min after the call); retry later",
              file=sys.stderr)
        sys.exit(EX_TEMPFAIL)


if __name__ == "__main__":
    main()
