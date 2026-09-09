#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("t3-my-prompts")


class PromptFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name)
        db = home / "userdata" / "state.sqlite"
        db.parent.mkdir()
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE projection_projects (
              project_id TEXT PRIMARY KEY, title TEXT, workspace_root TEXT, deleted_at TEXT
            );
            CREATE TABLE projection_threads (
              thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT,
              created_at TEXT, deleted_at TEXT, archived_at TEXT
            );
            CREATE TABLE projection_thread_messages (
              message_id TEXT PRIMARY KEY, thread_id TEXT, turn_id TEXT, role TEXT,
              text TEXT, is_streaming INTEGER, created_at TEXT, updated_at TEXT,
              attachments_json TEXT
            );
            INSERT INTO projection_projects VALUES ('p', 'Fixture', '/work/fixture', NULL);
            INSERT INTO projection_threads VALUES ('live-thread', 'p', 'Live', '', NULL, NULL);
            INSERT INTO projection_threads VALUES ('agent-thread', 'p', 'Worker', '', NULL, NULL);
            INSERT INTO projection_threads VALUES ('deleted-thread', 'p', 'Deleted secret', '', 'yes', NULL);
        """)
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        rows = [
            ("1", "agent-thread", "Read ai/CLAUDE.md first and do exactly that. AGENT SECRET"),
            ("1b", "agent-thread", "user-looking follow-up inside worker thread"),
            ("2", "live-thread", "the user request\n````python\n```\nCODE SECRET\n````\nkeep this"),
            ("2b", "live-thread", "[ping from worker] MANUAL-THREAD AGENT SECRET"),
            ("3", "deleted-thread", "DELETED SECRET"),
        ]
        for offset, (mid, thread, text) in enumerate(rows):
            at = (now + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO projection_thread_messages VALUES (?,?,?,?,?,0,?,?,NULL)",
                (mid, thread, mid, "user", text, at, at),
            )
        for i in range(20):
            at = (now + timedelta(seconds=10 + i)).isoformat().replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO projection_thread_messages VALUES (?,?,?,?,?,0,?,?,NULL)",
                (f"long-{i}", "live-thread", f"long-{i}", "user", "long the user text " + "x" * 300, at, at),
            )
        conn.commit()
        conn.close()
        self.env = os.environ | {"T3CODE_HOME": self.tmp.name}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_script(self, *args: str) -> str:
        return subprocess.run(
            [str(SCRIPT), *args], env=self.env, text=True, capture_output=True, check=True
        ).stdout

    def test_agent_ping_filtered(self) -> None:
        output = self.run_script("--days", "1", "--budget", "20000")
        self.assertNotIn("AGENT SECRET", output)
        self.assertNotIn("user-looking follow-up", output)
        self.assertIn("dropped 2 row(s) from 1 agent-spawned thread", output)
        self.assertIn("1 ping row(s) inside manual threads", output)

    def test_code_block_stripped(self) -> None:
        output = self.run_script("--days", "1", "--budget", "20000")
        self.assertIn("[code ", output)
        self.assertNotIn("CODE SECRET", output)
        self.assertIn("keep this", output)

    def test_budget_is_hard_cap(self) -> None:
        output = self.run_script("--days", "1", "--budget", "700")
        self.assertLessEqual(len(output), 700)
        self.assertIn("Cuts:", output)
        self.assertIn("budget dropped", output)

    def test_deleted_thread_excluded(self) -> None:
        output = self.run_script("--days", "1", "--budget", "20000")
        self.assertNotIn("DELETED SECRET", output)
        self.assertNotIn("Deleted secret", output)
        self.assertIn("1 deleted-thread row", output)


if __name__ == "__main__":
    unittest.main()
