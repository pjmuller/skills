"""Minimal synthetic `statev2.sqlite` for the t3-maintenance tests (only the
columns the CLIs read)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

NOW = datetime.now(UTC)

SCHEMA = """
CREATE TABLE projection_projects (project_id TEXT PRIMARY KEY, title TEXT,
  workspace_root TEXT, deleted_at TEXT);
CREATE TABLE orchestration_v2_projection_threads (thread_id TEXT PRIMARY KEY,
  project_id TEXT, title TEXT, created_at TEXT, updated_at TEXT, archived_at TEXT,
  deleted_at TEXT, payload_json TEXT, provider_instance_id TEXT);
CREATE TABLE orchestration_v2_projection_messages (message_id TEXT PRIMARY KEY,
  thread_id TEXT, run_id TEXT, role TEXT, created_at TEXT, updated_at TEXT, payload_json TEXT);
CREATE TABLE orchestration_v2_projection_runs (run_id TEXT PRIMARY KEY, thread_id TEXT,
  ordinal INTEGER, status TEXT);
CREATE TABLE orchestration_v2_projection_subagents (subagent_id TEXT PRIMARY KEY,
  thread_id TEXT, child_thread_id TEXT, origin TEXT, status TEXT, payload_json TEXT);
CREATE TABLE orchestration_v2_projection_runtime_requests (runtime_request_id TEXT PRIMARY KEY,
  thread_id TEXT, status TEXT);
CREATE TABLE orchestration_v2_projection_provider_threads (provider_thread_id TEXT PRIMARY KEY,
  thread_id TEXT, payload_json TEXT);
CREATE TABLE orchestration_events (sequence INTEGER PRIMARY KEY, stream_id TEXT, payload_json TEXT);
CREATE TABLE scheduled_tasks (task_id TEXT PRIMARY KEY, title TEXT, enabled INTEGER, thread_id TEXT);
INSERT INTO projection_projects VALUES ('p', 'fixture', '/tmp/fixture', NULL);
INSERT INTO projection_projects VALUES ('q', 'other', '/tmp/other', NULL);
"""


def stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ago(minutes: float) -> str:
    return stamp(NOW - timedelta(minutes=minutes))


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self._n = 0

    def thread(self, tid: str, title: str, *, project: str = "p", minutes: float = 0,
               parent: str | None = None, fork: bool = False, settled: bool = False, pinned: bool = False,
               archived: bool = False, deleted: bool = False, run: str | None = None,
               instance: str = "claudeAgent") -> None:
        payload = {
            "settledOverride": "settled" if settled else None,
            "pinnedAt": ago(1) if pinned else None,
            "lineage": {"parentThreadId": parent,
                        "relationshipToParent": ("fork" if fork else "subagent") if parent else None,
                        "rootThreadId": parent or tid},
        }
        self.db.execute(
            "INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?,?,?,?,?,?,?)",
            (tid, project, title, ago(minutes + 60), ago(minutes),
             ago(minutes) if archived else None, ago(minutes) if deleted else None,
             json.dumps(payload), instance),
        )
        if run:
            self.db.execute("INSERT INTO orchestration_v2_projection_runs VALUES (?,?,1,?)",
                            (f"run:{tid}", tid, run))

    def message(self, tid: str, role: str, text: str, minutes: float, *,
                by: str = "user", sender: str | None = None, attachments=()) -> None:
        self._n += 1
        payload = {"text": text, "createdBy": by if role == "user" else "agent",
                   "senderThreadId": sender, "attachments": [{"id": a} for a in attachments]}
        self.db.execute(
            "INSERT INTO orchestration_v2_projection_messages VALUES (?,?,NULL,?,?,?,?)",
            (f"m{self._n:04d}", tid, role, ago(minutes), ago(minutes), json.dumps(payload)),
        )

    def task(self, parent: str, child: str, status: str, delivery: str | None = None,
             origin: str = "app_owned") -> None:
        self.db.execute(
            "INSERT INTO orchestration_v2_projection_subagents VALUES (?,?,?,?,?,?)",
            (f"sub:{child}", parent, child, origin, status,
             json.dumps({"completionDelivery": {"state": delivery} if delivery else None})),
        )

    def close(self) -> Path:
        self.db.commit()
        self.db.close()
        return self.path
