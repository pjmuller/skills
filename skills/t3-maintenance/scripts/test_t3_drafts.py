#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

SCRIPT = Path(__file__).with_name("t3-drafts")


def load_cli():
    """The CLI has no .py suffix; import it by path to unit-test helpers."""
    loader = SourceFileLoader("t3drafts", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


ENV = "env0"
IDS = {
    "recent": "aaaaaaaa-0000-0000-0000-000000000001",
    "old": "bbbbbbbb-0000-0000-0000-000000000002",
    "archived": "cccccccc-0000-0000-0000-000000000003",
    "limited": "dddddddd-0000-0000-0000-000000000004",
    "empty": "eeeeeeee-0000-0000-0000-000000000005",
    "gone": "ffffffff-0000-0000-0000-000000000006",
    "twin_a": "12345678-0000-0000-0000-00000000000a",
    "twin_b": "12345678-0000-0000-0000-00000000000b",
}
PNG = base64.b64encode(b"pretend-image").decode()


class DraftsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_cli()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Path(self.temp.name) / "state.sqlite"
        now = datetime.now(timezone.utc)
        self.now = now
        connection = sqlite3.connect(self.store)
        connection.executescript("""
            CREATE TABLE projection_projects (
              project_id TEXT PRIMARY KEY, title TEXT
            );
            CREATE TABLE projection_threads (
              thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT,
              created_at TEXT, updated_at TEXT, deleted_at TEXT, archived_at TEXT,
              model_selection_json TEXT
            );
            CREATE TABLE projection_thread_messages (
              message_id TEXT PRIMARY KEY, thread_id TEXT, role TEXT, text TEXT,
              created_at TEXT
            );
            INSERT INTO projection_projects VALUES ('p','fixture');
        """)

        def thread(key, title, *, profile, hours, archived=False):
            connection.execute(
                "INSERT INTO projection_threads VALUES (?,?,?,?,?,?,?,?)",
                (
                    IDS[key],
                    "p",
                    title,
                    stamp(now - timedelta(days=30)),
                    stamp(now - timedelta(hours=hours)),
                    None,
                    stamp(now) if archived else None,
                    json.dumps({"instanceId": profile}),
                ),
            )

        thread("recent", "recent work", profile="claudeAgent_work", hours=1)
        thread("old", "old work", profile="claudeAgent_personal", hours=24 * 20)
        thread("archived", "archived work", profile="codex", hours=2, archived=True)
        thread("limited", "blocked work", profile="claudeAgent_work", hours=3)
        thread("empty", "no draft", profile="codex", hours=1)
        thread("twin_a", "twin a", profile="codex", hours=4)
        thread("twin_b", "twin b", profile="codex", hours=5)
        connection.execute(
            "INSERT INTO projection_thread_messages VALUES (?,?,?,?,?)",
            (
                "m1",
                IDS["limited"],
                "assistant",
                "You've hit your session limit · resets 8pm (Europe/Brussels)",
                stamp(now - timedelta(hours=3)),
            ),
        )
        connection.commit()
        connection.close()

        self.state = {
            "draftsByThreadKey": {
                f"{ENV}:{IDS['recent']}": {
                    "prompt": "  TODO read code follow ups\nsecond line  ",
                    "attachments": [
                        {
                            "id": "1",
                            "name": "shot.png",
                            "mimeType": "image/png",
                            "sizeBytes": "13",
                            "dataUrl": f"data:image/png;base64,{PNG}",
                        }
                    ],
                },
                f"{ENV}:{IDS['old']}": {"prompt": "DONE", "attachments": []},
                f"{ENV}:{IDS['archived']}": {"prompt": "stale", "attachments": []},
                f"{ENV}:{IDS['limited']}": {
                    "prompt": "then continue",
                    "attachments": [],
                },
                f"{ENV}:{IDS['empty']}": {"prompt": "   ", "attachments": []},
                f"{ENV}:{IDS['gone']}": {"prompt": "orphan", "attachments": []},
                f"{ENV}:{IDS['twin_a']}": {"prompt": "twin a draft", "attachments": []},
                f"{ENV}:{IDS['twin_b']}": {"prompt": "twin b draft", "attachments": []},
            },
            "draftThreadsByThreadKey": {},
        }

    def build(self):
        module = self.module
        return module.enrich(
            module.extract_drafts(self.state),
            module.load_threads(self.store),
            module.load_limited_ids(self.store),
        )

    def run_cli(self, *args: str, expect: int = 0):
        """Run main() in-process with the LevelDB loader swapped for the fixture."""
        module = self.module
        original = module.load_state
        module.load_state = lambda _path: self.state
        out, err = self.temp.name + "/out", self.temp.name + "/err"
        try:
            with open(out, "w") as stdout, open(err, "w") as stderr:
                old = sys.stdout, sys.stderr
                sys.stdout, sys.stderr = stdout, stderr
                try:
                    code = module.main(["--store", str(self.store), *args])
                except SystemExit as exit_error:
                    code = 1 if exit_error.code else 0
                    print(exit_error, file=stderr)
                finally:
                    sys.stdout, sys.stderr = old
        finally:
            module.load_state = original
        self.assertEqual(code, expect)
        return Path(out).read_text(), Path(err).read_text()

    def rows(self, *args: str) -> list[dict]:
        stdout, _ = self.run_cli("list", "--json", *args)
        return json.loads(stdout)

    def test_empty_and_orphan_drafts_are_dropped(self) -> None:
        drafts, orphans = self.build()
        self.assertEqual(orphans, 1)  # IDS['gone'] is not in the store
        ids = [draft.thread_id for draft in drafts]
        self.assertNotIn(IDS["empty"], ids)
        self.assertNotIn(IDS["gone"], ids)
        self.assertEqual(ids[0], IDS["recent"])  # newest thread first

    def test_list_filters(self) -> None:
        shorts = [row["short_id"] for row in self.rows()]
        self.assertEqual(
            shorts, ["aaaaaaaa", "dddddddd", "12345678", "12345678", "bbbbbbbb"]
        )
        self.assertNotIn("cccccccc", shorts)  # archived hidden by default
        self.assertIn(
            "cccccccc", [row["short_id"] for row in self.rows("--include-archived")]
        )
        self.assertEqual(
            [row["short_id"] for row in self.rows("--profile", "WORK")],
            ["aaaaaaaa", "dddddddd"],
        )
        self.assertEqual(
            [row["short_id"] for row in self.rows("--project", "fixture")], shorts
        )
        self.assertNotIn(
            "bbbbbbbb", [row["short_id"] for row in self.rows("--since", "7d")]
        )
        self.assertEqual(
            [row["short_id"] for row in self.rows("--limited")], ["dddddddd"]
        )

    def test_orphan_note_on_stderr_and_first_line_only(self) -> None:
        stdout, stderr = self.run_cli("list")
        self.assertIn("1 draft(s) for threads missing from the store", stderr)
        self.assertIn("TODO read code follow ups", stdout)
        self.assertNotIn("second line", stdout)

    def test_show_requires_unambiguous_prefix(self) -> None:
        _, err = self.run_cli("show", "1234", expect=1)
        self.assertIn("at least 8", err)
        _, err = self.run_cli("show", "12345678", expect=1)
        self.assertIn("ambiguous", err)
        _, err = self.run_cli("show", "99999999", expect=1)
        self.assertIn("no draft", err)
        stdout, _ = self.run_cli("show", "aaaaaaaa")
        self.assertIn("second line", stdout)
        self.assertIn("shot.png  13 bytes", stdout)

    def test_show_saves_attachments(self) -> None:
        target = Path(self.temp.name) / "att"
        self.run_cli("show", "aaaaaaaa", "--save-attachments", str(target))
        saved = target / "aaaaaaaa-shot.png"
        self.assertEqual(saved.read_bytes(), b"pretend-image")

    def test_save_skips_non_data_urls(self) -> None:
        module = self.module
        draft = module.Draft(
            IDS["recent"], "x", [{"name": "bad.png", "dataUrl": "https://nope"}]
        )
        target = Path(self.temp.name) / "att2"
        with contextlib.redirect_stderr(io.StringIO()):
            module.save_attachments(draft, target)
        self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
