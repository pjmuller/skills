"""How full is a thread's context window? Read-only over T3's store (`statev2.sqlite`).

A model can't sense its own context length; T3 records it per provider thread
(`contextUsage`, refreshed each turn) and logs every auto-compaction and user message
as a turn item. Long-lived threads (a router) run this at each turn start:
- `lessons` (past the token checkpoint, once per compaction cycle): persist lessons
  silently. Compaction alone is no reason to bother the user: it frees room well and
  routing rules are re-read afterwards.
- `reset` (once per thread, after RESET_AFTER_MESSAGES user messages): suggest a fresh thread.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

STORE = Path(os.environ.get("T3CODE_HOME", Path.home() / ".t3")) / "userdata" / "statev2.sqlite"
# Lessons checkpoint before auto-compaction (Codex compacts at 88-95%): 60% leaves room
# for a 15-point turn plus the lessons pass; the cap covers 1M-token windows.
CHECKPOINT_SHARE = 0.60
CHECKPOINT_CAP = 160_000
# Reset nudge: a user-chosen freshness interval, not a measured quality cliff. Routers
# ran 70 messages over 4 compactions (2026-10) without rising corrections, and each
# compaction left only 33-66k tokens.
RESET_AFTER_MESSAGES = 50
# One notice per compaction cycle; /tmp is writable from Codex's sandbox and a reboot
# only costs one repeated notice.
NOTICE_DIR = Path(os.environ.get("T3_CONTEXT_STATE", "/tmp/t3-context"))


def read_usage(store: Path, thread_id: str) -> dict | None:
    uri = f"file:{quote(str(store), safe='/')}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as db:
        row = db.execute(
            "SELECT json_extract(payload_json, '$.contextUsage.usedTokens'),"
            " json_extract(payload_json, '$.contextUsage.maxTokens'), updated_at"
            " FROM orchestration_v2_projection_provider_threads"
            " WHERE thread_id = ? AND json_extract(payload_json, '$.contextUsage') IS NOT NULL"
            " ORDER BY updated_at DESC LIMIT 1",
            (thread_id,),
        ).fetchone()
        if not row or not row[0] or not row[1]:
            return None
        compactions, messages = db.execute(
            "SELECT count(*) FILTER (WHERE type = 'compaction'), count(*) FILTER (WHERE type = 'user_message')"
            " FROM orchestration_v2_projection_turn_items WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
    used, window, observed = row
    checkpoint = min(int(window * CHECKPOINT_SHARE), CHECKPOINT_CAP)
    return {"used": used, "max": window, "pct": round(100 * used / window), "checkpoint": checkpoint,
            "compactions": compactions, "messages": messages, "observedAt": observed}


def pinned_router(store: Path) -> str | None:
    """Fallback when T3 sets no T3CODE_THREAD_ID (Codex sessions): the pinned, live 🧭 thread."""
    uri = f"file:{quote(str(store), safe='/')}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as db:
        row = db.execute(
            "SELECT thread_id FROM orchestration_v2_projection_threads"
            " WHERE title LIKE '🧭%' AND deleted_at IS NULL"
            " AND json_extract(payload_json, '$.pinnedAt') IS NOT NULL"
            " AND json_extract(payload_json, '$.settledOverride') IS NULL"
            " ORDER BY json_extract(payload_json, '$.pinnedAt') DESC LIMIT 1"
        ).fetchone()
    return row[0] if row else None


def classify(thread_id: str, usage: dict) -> str:
    """`reset` once per thread, `lessons` once per compaction cycle, else `ok`; records notices."""
    marker = NOTICE_DIR / hashlib.sha1(thread_id.encode()).hexdigest()[:16]
    try:
        seen = json.loads(marker.read_text())
    except (OSError, ValueError):
        seen = {}
    if not isinstance(seen, dict):  # pre-2026-10-30 marker: the compaction count of the last notice
        seen = {"lessons": seen}
    if usage["messages"] >= RESET_AFTER_MESSAGES and not seen.get("reset"):
        status = seen["reset"] = "reset"
        seen["lessons"] = usage["compactions"]  # the reset playbook runs the lessons pass first
    elif usage["used"] >= usage["checkpoint"] and seen.get("lessons") != usage["compactions"]:
        status, seen["lessons"] = "lessons", usage["compactions"]
    else:
        return "ok"
    NOTICE_DIR.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(seen))
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="t3-context", description=__doc__.splitlines()[0])
    parser.add_argument("thread_id", nargs="?", default=os.environ.get("T3CODE_THREAD_ID"),
                        help="default: T3CODE_THREAD_ID (Claude sessions), else the pinned 🧭 router")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--store", type=Path, default=STORE)
    args = parser.parse_args(argv)
    try:
        args.thread_id = args.thread_id or pinned_router(args.store)
        if not args.thread_id:
            print("context unknown: no thread id (pass one, or pin a 🧭 router)")
            return 0
        usage = read_usage(args.store, args.thread_id)
    except sqlite3.Error as error:
        usage, reason = None, f"store unreadable ({error})"
    else:
        reason = "no usage recorded yet"
    if usage is None:
        print(json.dumps({"status": "unknown", "reason": reason}) if args.json else f"context unknown: {reason}")
        return 0
    usage["status"] = classify(args.thread_id, usage)
    if args.json:
        print(json.dumps(usage))
        return 0
    line = (f"{args.thread_id[:24]} context {usage['pct']}% ({usage['used'] // 1000}k/{usage['max'] // 1000}k,"
            f" lessons at {usage['checkpoint'] // 1000}k) · messages {usage['messages']}/{RESET_AFTER_MESSAGES}"
            f" · compactions {usage['compactions']} · {usage['status']}")
    line += {"lessons": " → persist lessons now, silently (no reset line)",
             "reset": " → persist lessons, then suggest a fresh thread (once)"}.get(usage["status"], "")
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
