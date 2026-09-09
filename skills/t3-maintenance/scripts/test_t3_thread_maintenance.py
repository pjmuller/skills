#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import os
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).with_name("t3-thread-maintenance")


class ThreadMaintenanceFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = Path(self.temp.name) / "state.sqlite"
        connection = sqlite3.connect(self.store)
        connection.executescript("""
            CREATE TABLE projection_projects (
              project_id TEXT PRIMARY KEY, title TEXT, deleted_at TEXT
            );
            CREATE TABLE projection_threads (
              thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, created_at TEXT,
              latest_user_message_at TEXT, latest_turn_id TEXT, settled_override TEXT,
              settled_at TEXT, pinned_at TEXT, pending_approval_count INTEGER,
              pending_user_input_count INTEGER, deleted_at TEXT, archived_at TEXT
            );
            CREATE TABLE projection_thread_messages (
              message_id TEXT PRIMARY KEY, thread_id TEXT, created_at TEXT
            );
            CREATE TABLE projection_turns (
              thread_id TEXT, turn_id TEXT, requested_at TEXT, started_at TEXT, completed_at TEXT
            );
            CREATE TABLE projection_thread_sessions (
              thread_id TEXT PRIMARY KEY, status TEXT
            );
            CREATE TABLE orchestration_events (
              sequence INTEGER PRIMARY KEY, aggregate_kind TEXT, stream_id TEXT,
              event_type TEXT, command_id TEXT
            );
            INSERT INTO projection_projects VALUES ('p', 'Fixture', NULL);
        """)
        now = datetime.now(timezone.utc)
        rows = [
            (
                "old",
                "Old legacy",
                now - timedelta(days=40),
                None,
                None,
                None,
                "stopped",
            ),
            (
                "error",
                "Failed legacy",
                now - timedelta(days=45),
                None,
                None,
                None,
                "error",
            ),
            (
                "pinned",
                "Pinned legacy",
                now - timedelta(days=50),
                None,
                None,
                "yes",
                "stopped",
            ),
            (
                "auto",
                "Recent architecture",
                now - timedelta(days=7),
                "settled",
                now - timedelta(hours=1),
                None,
                "stopped",
            ),
            (
                "manual",
                "Manual settled",
                now - timedelta(days=6),
                "settled",
                now - timedelta(hours=1),
                None,
                "stopped",
            ),
        ]
        for thread_id, title, activity, override, settled_at, pinned_at, status in rows:
            activity_iso = activity.isoformat().replace("+00:00", "Z")
            settled_iso = (
                settled_at.isoformat().replace("+00:00", "Z") if settled_at else None
            )
            connection.execute(
                "INSERT INTO projection_threads VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
                (
                    thread_id,
                    "p",
                    title,
                    activity_iso,
                    activity_iso,
                    None,
                    override,
                    settled_iso,
                    pinned_at,
                    0,
                    0,
                ),
            )
            connection.execute(
                "INSERT INTO projection_thread_sessions VALUES (?, ?)",
                (thread_id, status),
            )
        connection.execute(
            "INSERT INTO orchestration_events VALUES (1,'thread','auto','thread.settled','server:auto-settle:auto:x')"
        )
        connection.execute(
            "INSERT INTO orchestration_events VALUES (2,'thread','manual','thread.settled','client:manual')"
        )
        connection.commit()
        connection.close()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, *args: str, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(
            [str(SCRIPT), "--store", str(self.store), *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            self.fail(
                f"command failed ({result.returncode}):\n{result.stdout}\n{result.stderr}"
            )
        return result.stdout

    def test_settle_old_excludes_pinned_and_settled(self) -> None:
        output = self.run_script("settle-old", "--older-than", "30", "--format", "ids")
        self.assertIn("old", output)
        self.assertNotIn("pinned", output)
        self.assertNotIn("error", output)
        self.assertNotIn("auto", output)

    def test_apply_revalidates_and_never_waits_for_fresh_work(self) -> None:
        bin_dir = Path(self.temp.name) / "bin"
        bin_dir.mkdir()
        capture = Path(self.temp.name) / "helper-args"
        helper = bin_dir / "t3-settle-thread"
        helper.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$CAPTURE"\n'
            "sqlite3 \"$FIXTURE_STORE\" \"UPDATE projection_threads SET settled_override='settled' WHERE thread_id='$1'\"\n"
        )
        helper.chmod(0o755)
        env = os.environ | {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "T3_MAINTENANCE_STATE_DIR": str(Path(self.temp.name) / "actions"),
            "CAPTURE": str(capture),
            "FIXTURE_STORE": str(self.store),
        }
        self.run_script(
            "settle-old",
            "--older-than",
            "30",
            "--title",
            "Old legacy",
            "--apply",
            env=env,
        )
        self.assertEqual(capture.read_text().strip(), "old")

    def test_revive_auto_requires_server_auto_settle_event(self) -> None:
        since = (
            (datetime.now(timezone.utc) - timedelta(hours=2))
            .isoformat()
            .replace("+00:00", "Z")
        )
        output = self.run_script(
            "revive-auto",
            "--since",
            since,
            "--newer-than",
            "14",
            "--format",
            "ids",
        )
        self.assertIn("auto", output)
        self.assertNotIn("manual", output)

    def test_audit_json_counts_both_anomaly_classes(self) -> None:
        output = self.run_script("audit", "--format", "json")
        self.assertIn('"legacy_active_candidates": 1', output)
        self.assertIn('"recent_auto_settled": 1', output)


if __name__ == "__main__":
    unittest.main()
