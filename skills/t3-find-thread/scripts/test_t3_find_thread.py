#!/usr/bin/env python3
"""Unit tests for t3-find-thread against a synthetic T3 store.

    python3 -m unittest discover -s scripts -p 'test_*.py'
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent


def make_store(root: Path) -> Path:
    userdata = root / "userdata"
    userdata.mkdir(parents=True)
    store = userdata / "state.sqlite"
    db = sqlite3.connect(store)
    db.executescript(
        """
        CREATE TABLE projection_projects (project_id TEXT PRIMARY KEY, title TEXT NOT NULL,
          workspace_root TEXT NOT NULL, created_at TEXT, updated_at TEXT, deleted_at TEXT);
        CREATE TABLE projection_threads (thread_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
          title TEXT NOT NULL, branch TEXT, worktree_path TEXT, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, deleted_at TEXT, archived_at TEXT, latest_user_message_at TEXT);
        CREATE TABLE projection_thread_messages (message_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL,
          role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        """
    )
    db.execute("INSERT INTO projection_projects VALUES ('p1','Personal','/Users/x/code/personal','','', NULL)")
    db.execute("INSERT INTO projection_projects VALUES ('p2','Work','/Users/x/code/work','','', NULL)")
    threads = [
        ("t-referral-1234", "p1", "Measure Tenant Referral Engagement", "2026-08-27T11:40:32Z", "2026-08-27T13:00:00Z", None),
        ("t-styling-5678", "p1", "Fix button styling", "2026-05-01T09:00:00Z", "2026-05-01T10:00:00Z", "2026-05-02T00:00:00Z"),
        ("t-work-9012", "p2", "Ahoy events for patient emails", "2026-08-20T09:00:00Z", "2026-08-20T12:00:00Z", None),
    ]
    for thread_id, project, title, created, updated, archived in threads:
        db.execute(
            "INSERT INTO projection_threads VALUES (?,?,?,NULL,NULL,?,?,NULL,?,?)",
            (thread_id, project, title, created, updated, archived, updated),
        )
    messages = [
        ("m1", "t-referral-1234", "user", "count ahoy_events per tenant from the rds snapshot for stats", "2026-08-27T11:41:00Z"),
        ("m2", "t-referral-1234", "assistant", "I restored the rds snapshot and queried ahoy_events. " + "detail " * 60, "2026-08-27T11:45:00Z"),
        ("m3", "t-referral-1234", "user", "yes use the snapshot", "2026-08-27T11:50:00Z"),
        ("m4", "t-styling-5678", "user", "the button padding is off", "2026-05-01T09:01:00Z"),
        ("m5", "t-work-9012", "assistant", "ahoy_events table has no rows for this tenant", "2026-08-20T09:30:00Z"),
    ]
    for message_id, thread_id, role, text, stamp in messages:
        db.execute(
            "INSERT INTO projection_thread_messages VALUES (?,?,?,?,?,?)",
            (message_id, thread_id, role, text, stamp, stamp),
        )
    db.commit()
    db.close()
    return store


class FindThreadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.store = make_store(root / "t3")
        os.environ["T3CODE_HOME"] = str(root / "t3")
        os.environ["T3_FIND_CACHE_DIR"] = str(root / "cache")
        spec = importlib.util.spec_from_loader(
            "t3findthread", importlib.machinery.SourceFileLoader("t3findthread", str(HERE / "t3-find-thread"))
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.fetch_environment_id = lambda: "env-test"  # no live T3 server in tests
        cls.mod = module

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_cli(self, *argv) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.mod.main(list(argv))
        return buffer.getvalue()

    # --- index ---------------------------------------------------------------

    def test_index_then_incremental_is_a_noop(self):
        first = self.mod.sync_index(self.store, rebuild=True)
        self.assertEqual(first["threads_indexed"], 3)
        self.assertEqual(first["threads_refreshed"], 3)
        second = self.mod.sync_index(self.store)
        self.assertEqual(second["threads_refreshed"], 0)
        self.assertTrue(second["fts5"], "FTS5 expected in this interpreter")

    def test_incremental_picks_up_a_new_message(self):
        self.mod.sync_index(self.store, rebuild=True)
        db = sqlite3.connect(self.store)
        db.execute(
            "INSERT INTO projection_thread_messages VALUES "
            "('m9','t-styling-5678','user','also fix the kerning','2026-09-01T09:00:00Z','2026-09-01T09:00:00Z')"
        )
        db.commit()
        db.close()
        self.assertEqual(self.mod.sync_index(self.store)["threads_refreshed"], 1)
        out = self.run_cli("search", "--format", "ids", "kerning")
        self.assertIn("t-styli", out)
        db = sqlite3.connect(self.store)
        db.execute("DELETE FROM projection_thread_messages WHERE message_id='m9'")
        db.commit()
        db.close()
        self.mod.sync_index(self.store, rebuild=True)

    # --- search --------------------------------------------------------------

    def test_ranking_prefers_user_hits_and_more_terms(self):
        out = self.run_cli("search", "--format", "json", "ahoy", "snapshot", "stats")
        results = self.mod.json.loads(out)["results"]
        self.assertEqual(results[0]["thread_id"], "t-referral-1234")
        self.assertEqual(len(results[0]["terms_hit"]), 3)
        self.assertGreater(results[0]["score"], results[1]["score"])
        self.assertEqual(results[1]["thread_id"], "t-work-9012")  # assistant-only hit ranks lower

    def test_underscore_token_matches_bare_word(self):
        results = self.mod.json.loads(self.run_cli("search", "--format", "json", "ahoy"))["results"]
        self.assertEqual({r["thread_id"] for r in results}, {"t-referral-1234", "t-work-9012"})

    def test_all_requires_every_term(self):
        results = self.mod.json.loads(self.run_cli("search", "--format", "json", "--all", "ahoy", "snapshot"))["results"]
        self.assertEqual([r["thread_id"] for r in results], ["t-referral-1234"])

    def test_project_fuzzy_and_typo(self):
        for needle in ("personal", "Persona"):
            results = self.mod.json.loads(self.run_cli("search", "--format", "json", "--project", needle, "ahoy"))["results"]
            self.assertEqual([r["thread_id"] for r in results], ["t-referral-1234"], needle)

    def test_date_filters(self):
        results = self.mod.json.loads(self.run_cli("search", "--format", "json", "--since", "2026-08-01", "ahoy"))["results"]
        self.assertEqual(len(results), 2)
        results = self.mod.json.loads(
            self.run_cli("search", "--format", "json", "--until", "2026-06-01", "--title-only", "button")
        )["results"]
        self.assertEqual([r["thread_id"] for r in results], ["t-styling-5678"])

    def test_archived_flag_and_exclusion(self):
        results = self.mod.json.loads(self.run_cli("search", "--format", "json", "--title-only", "button"))["results"]
        self.assertTrue(results[0]["archived"])
        self.assertEqual(self.mod.json.loads(self.run_cli("search", "--format", "json", "--no-archived", "--title-only", "button"))["results"], [])

    def test_fuzzy_expansion_catches_a_typo(self):
        self.assertEqual(self.mod.json.loads(self.run_cli("search", "--format", "json", "snapshopt"))["results"], [])
        results = self.mod.json.loads(self.run_cli("search", "--format", "json", "--fuzzy", "snapshopt"))["results"]
        self.assertEqual([r["thread_id"] for r in results], ["t-referral-1234"])

    def test_md_table_shows_id_not_links(self):
        """Links never work inside T3 chat, so the table carries the id + a CLI hint."""
        out = self.run_cli("search", "--project", "personal", "ahoy")
        self.assertIn("| # | created | project |", out)
        self.assertIn("| `t-referr` |", out)
        self.assertNotIn("http://127.0.0.1:3773/", out)
        self.assertIn("Open in app: t3-open-thread <id>", out)

    def test_web_links_flag_adds_browser_url(self):
        out = self.run_cli("search", "--project", "personal", "--web-links", "ahoy")
        self.assertIn("[web](http://127.0.0.1:3773/env-test/t-referral-1234)", out)

    # --- peek / grep ----------------------------------------------------------

    def test_peek_truncates_prompts_and_outlines(self):
        payload = self.mod.json.loads(self.run_cli("--json", "peek", "t-referral-1234", "--prompts", "1"))
        self.assertEqual(len(payload[0]["prompts"]), 1)
        self.assertEqual(payload[0]["prompts"][0]["idx"], 0)
        self.assertEqual(len(payload[0]["outline"]), 3)
        long_line = payload[0]["outline"][1]["head"]
        self.assertLessEqual(len(long_line), 100)
        self.assertTrue(long_line.endswith("…"))

    def test_peek_accepts_comma_separated_ids(self):
        payload = self.mod.json.loads(self.run_cli("--json", "peek", "t-referral-1234,t-work-9012"))
        self.assertEqual([p["thread_id"] for p in payload], ["t-referral-1234", "t-work-9012"])

    def test_grep_returns_snippets_per_term(self):
        payload = self.mod.json.loads(self.run_cli("--json", "grep", "t-referral-1234", "-k", "snapshot", "-k", "restore"))
        terms = [s["term"] for s in payload["snippets"]]
        self.assertIn("snapshot", terms)
        self.assertIn("restore", terms)
        self.assertTrue(all("snapshot" in s["text"].lower() or "restore" in s["text"].lower() for s in payload["snippets"]))

    def test_short_id_must_be_long_enough(self):
        with self.assertRaises(SystemExit):
            self.run_cli("--json", "peek", "t-ref")


if __name__ == "__main__":
    unittest.main()
