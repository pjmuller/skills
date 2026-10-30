"""How full is a thread's context window? Read-only over T3's store (`statev2.sqlite`).

A model can't sense its own context length; T3 records it per provider thread
(`contextUsage`, refreshed each turn) and logs every auto-compaction as a turn item.
Long-lived threads (a router) run this at each turn start: past the checkpoint
they persist lessons and suggest a fresh thread before compaction drops detail.
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
# Checkpoint before auto-compaction (observed at 82-93% on Codex): 60% leaves room for a
# 15-point turn plus the lessons pass. The absolute cap keeps 1M-token windows from
# growing unboundedly long before anyone notices; it's an operating margin, not a
# proven quality cliff.
CHECKPOINT_SHARE = 0.60
CHECKPOINT_CAP = 160_000
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
        compactions = db.execute(
            "SELECT count(*) FROM orchestration_v2_projection_turn_items"
            " WHERE thread_id = ? AND type = 'compaction'",
            (thread_id,),
        ).fetchone()[0]
    used, window, observed = row
    checkpoint = min(int(window * CHECKPOINT_SHARE), CHECKPOINT_CAP)
    return {"used": used, "max": window, "pct": round(100 * used / window),
            "checkpoint": checkpoint, "compactions": compactions, "observedAt": observed}


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


def first_notice(thread_id: str, compactions: int) -> bool:
    """True once per thread per compaction cycle; records the notice."""
    marker = NOTICE_DIR / hashlib.sha1(thread_id.encode()).hexdigest()[:16]
    if marker.exists() and marker.read_text().strip() == str(compactions):
        return False
    NOTICE_DIR.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(compactions))
    return True


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
    if usage["used"] < usage["checkpoint"]:
        usage["status"] = "ok"
    else:
        usage["status"] = "checkpoint" if first_notice(args.thread_id, usage["compactions"]) else "noticed"
    if args.json:
        print(json.dumps(usage))
        return 0
    line = (f"{args.thread_id[:24]} context {usage['pct']}% ({usage['used'] // 1000}k/{usage['max'] // 1000}k,"
            f" checkpoint {usage['checkpoint'] // 1000}k) · compactions {usage['compactions']} · {usage['status']}")
    if usage["status"] == "checkpoint":
        line += " → persist lessons now, then suggest a fresh thread (once this cycle)"
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
