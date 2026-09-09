#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).with_name("t3-fleet")
PARENT = "aaaaaaaa-0000-0000-0000-00000000aaaa"


def stamp(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


class FleetFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = Path(self.temp.name) / "state.sqlite"
        connection = sqlite3.connect(self.store)
        connection.executescript("""
            CREATE TABLE projection_projects (
              project_id TEXT PRIMARY KEY, title TEXT, workspace_root TEXT, deleted_at TEXT
            );
            CREATE TABLE projection_threads (
              thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, created_at TEXT,
              settled_override TEXT, deleted_at TEXT, archived_at TEXT
            );
            CREATE TABLE projection_thread_messages (
              message_id TEXT PRIMARY KEY, thread_id TEXT, role TEXT, text TEXT, created_at TEXT
            );
            CREATE TABLE projection_thread_sessions (
              thread_id TEXT PRIMARY KEY, status TEXT
            );
            INSERT INTO projection_projects VALUES ('p','fixture','/tmp/fixture',NULL);
            INSERT INTO projection_projects VALUES ('q','other','/tmp/other',NULL);
        """)
        now = datetime.now(timezone.utc)
        self.now = now

        def thread(
            thread_id: str,
            title: str,
            status: str,
            *,
            project: str = "p",
            settled: str | None = None,
            deleted: str | None = None,
            archived: str | None = None,
        ) -> None:
            connection.execute(
                "INSERT INTO projection_threads VALUES (?,?,?,?,?,?,?)",
                (
                    thread_id,
                    project,
                    title,
                    stamp(now - timedelta(days=9)),
                    settled,
                    deleted,
                    archived,
                ),
            )
            connection.execute(
                "INSERT INTO projection_thread_sessions VALUES (?,?)",
                (thread_id, status),
            )

        def message(
            message_id: str, thread_id: str, role: str, text: str, minutes_ago: float
        ) -> None:
            connection.execute(
                "INSERT INTO projection_thread_messages VALUES (?,?,?,?,?)",
                (
                    message_id,
                    thread_id,
                    role,
                    text,
                    stamp(now - timedelta(minutes=minutes_ago)),
                ),
            )

        # Orchestrator: got a ping back from `done` only.
        thread(PARENT, "🏓 orchestrator", "ready")
        message("m1", PARENT, "user", "kick off the fleet", 300)
        message("m2", PARENT, "user", "[ping from done] finished, landed on main", 20)

        brief = f"When finished: t3-ping-thread --thread {PARENT} --from {{label}} -- 'report'"
        for label, thread_id, status, minutes in (
            ("done", "bbbbbbbb-0000-0000-0000-00000000bbbb", "stopped", 22),
            ("dead", "cccccccc-0000-0000-0000-00000000cccc", "stopped", 30),
            ("busy", "dddddddd-0000-0000-0000-00000000dddd", "ready", 40),
        ):
            thread(thread_id, f"🏓 worker {label}", status)
            message(f"{label}-u", thread_id, "user", brief.format(label=label), 200)
            message(
                f"{label}-a", thread_id, "assistant", f"{label} summary line", minutes
            )

        # Orphan worker without a resolvable parent, plus filter fodder.
        thread("eeeeeeee-0000-0000-0000-00000000eeee", "orphan worker", "stopped")
        message(
            "orph-a",
            "eeeeeeee-0000-0000-0000-00000000eeee",
            "assistant",
            "no parent",
            60,
        )
        thread(
            "ffffffff-0000-0000-0000-00000000ffff", "elsewhere", "ready", project="q"
        )
        message(
            "else-a",
            "ffffffff-0000-0000-0000-00000000ffff",
            "assistant",
            "other project",
            90,
        )
        thread(
            "99999999-0000-0000-0000-000000009999",
            "old settled",
            "stopped",
            settled="settled",
        )
        message(
            "old-a",
            "99999999-0000-0000-0000-000000009999",
            "assistant",
            "ancient",
            60 * 96,
        )
        thread(
            "88888888-0000-0000-0000-000000008888",
            "trashed",
            "stopped",
            deleted=stamp(now),
        )
        message("tr-a", "88888888-0000-0000-0000-000000008888", "assistant", "gone", 10)
        connection.commit()
        connection.close()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(
        self, *args: str, env: dict[str, str] | None = None, expect: int = 0
    ) -> str:
        result = subprocess.run(
            [str(SCRIPT), "--store", str(self.store), *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expect, f"{result.stdout}\n{result.stderr}")
        return result.stdout

    def rows(self, *args: str) -> list[dict]:
        return json.loads(self.run_script("list", "--json", *args))

    def test_list_sorts_by_activity_and_hides_deleted(self) -> None:
        ids = [row["short_id"] for row in self.rows()]
        self.assertNotIn("88888888", ids)
        self.assertEqual(
            ids[:2], ["aaaaaaaa", "bbbbbbbb"]
        )  # most recent activity first
        self.assertEqual(ids[-1][:8], "99999999")  # 4-day-old settled thread last
        self.assertIn("88888888", [row["short_id"] for row in self.rows("--all")])

    def test_recent_title_prefix_and_project_filters(self) -> None:
        recent = {row["short_id"] for row in self.rows("--recent", "45m")}
        self.assertEqual(recent, {"bbbbbbbb", "cccccccc", "dddddddd", "aaaaaaaa"})
        prefixed = {row["short_id"] for row in self.rows("--title-prefix", "🏓")}
        self.assertNotIn("eeeeeeee", prefixed)
        self.assertEqual(
            [row["short_id"] for row in self.rows("--project", "/tmp/other")],
            ["ffffffff"],
        )
        self.assertEqual(
            {row["short_id"] for row in self.rows("--status", "ready")},
            {"aaaaaaaa", "dddddddd", "ffffffff"},
        )

    def test_parent_and_settled_filters(self) -> None:
        children = {row["short_id"] for row in self.rows("--parent", PARENT[:8])}
        self.assertEqual(children, {"bbbbbbbb", "cccccccc", "dddddddd"})
        self.assertEqual(
            [row["short_id"] for row in self.rows("--settled")], ["99999999"]
        )
        self.assertNotIn("99999999", [r["short_id"] for r in self.rows("--unsettled")])

    def test_stalled_needs_assistant_last_stopped_and_no_ping_back(self) -> None:
        stalled = {row["short_id"] for row in self.rows("--stalled")}
        self.assertIn("cccccccc", stalled)  # dead worker, parent never pinged
        self.assertNotIn("bbbbbbbb", stalled)  # pinged back with its own label
        self.assertNotIn("dddddddd", stalled)  # still ready
        self.assertIn("eeeeeeee", stalled)  # no parent -> assistant-last + stopped
        strict = {row["short_id"] for row in self.rows("--stalled=strict")}
        self.assertIn("cccccccc", strict)
        self.assertNotIn("eeeeeeee", strict)  # unknown-parent is not a proven corpse
        states = {row["short_id"]: row["stall_state"] for row in self.rows()}
        self.assertEqual(states["cccccccc"], "stalled")
        self.assertEqual(states["eeeeeeee"], "unknown-parent")
        self.assertIsNone(states["bbbbbbbb"])
        by_id = {row["short_id"]: row for row in self.rows()}
        self.assertTrue(by_id["bbbbbbbb"]["pinged_back"])
        self.assertEqual(by_id["bbbbbbbb"]["parent_id"], PARENT)
        self.assertEqual(
            sorted(by_id["aaaaaaaa"]["children"]),
            sorted(
                [
                    "bbbbbbbb-0000-0000-0000-00000000bbbb",
                    "cccccccc-0000-0000-0000-00000000cccc",
                    "dddddddd-0000-0000-0000-00000000dddd",
                ]
            ),
        )

    def test_terse_line_carries_columns(self) -> None:
        line = next(
            row
            for row in self.run_script("list", "--parent", PARENT).splitlines()
            if row.startswith("cccccccc")
        )
        for fragment in (
            "fixture",
            "🏓 worker dead",
            "stopped",
            "assistant: dead summary line",
        ):
            self.assertIn(fragment, line)

    def test_bulk_dry_run_expands_helper_commands(self) -> None:
        output = self.run_script(
            "ping",
            "--ids",
            "bbbbbbbb",
            "cccccccc",
            "--from",
            "orch",
            "--dry-run",
            "--",
            "status?",
        )
        self.assertIn(
            "t3-ping-thread --thread bbbbbbbb-0000-0000-0000-00000000bbbb "
            "--from orch -- status?",
            output,
        )
        self.assertIn("cccccccc-0000-0000-0000-00000000cccc", output)
        unsettle = self.run_script("unsettle", "--ids", "99999999", "--dry-run")
        self.assertIn(
            "t3-settle-thread --unsettle 99999999-0000-0000-0000-000000009999", unsettle
        )

    def test_bulk_continues_on_failure_and_exits_nonzero(self) -> None:
        bin_dir = Path(self.temp.name) / "bin"
        bin_dir.mkdir()
        capture = Path(self.temp.name) / "calls"
        helper = bin_dir / "t3-settle-thread"
        helper.write_text(
            '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$CAPTURE"\n'
            'case "$2" in *cccc) echo boom >&2; exit 3 ;; esac\n'
        )
        helper.chmod(0o755)
        env = os.environ | {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "CAPTURE": str(capture),
        }
        output = self.run_script(
            "unsettle", "--ids", "cccccccc", "bbbbbbbb", env=env, expect=1
        )
        self.assertIn("FAILED cccccccc", output)
        self.assertIn("ok     bbbbbbbb", output)
        self.assertEqual(len(capture.read_text().strip().splitlines()), 2)

    def test_ping_requires_a_message(self) -> None:
        result = subprocess.run(
            [str(SCRIPT), "--store", str(self.store), "ping", "--ids", "bbbbbbbb"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
