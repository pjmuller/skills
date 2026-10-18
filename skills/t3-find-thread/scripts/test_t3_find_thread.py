#!/usr/bin/env python3
"""Unit tests for t3-find-thread against a synthetic T3 statev2 store.

    uv run --with pytest pytest . -q
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
PID = "11111111-2222-3333-4444-555555555555"
REFERRAL = "aaaaaaaa-0000-4000-8000-000000000001"  # bare UUID (imported history)
STYLING = "mcp:bbbbbbbb-0000-4000-8000-000000000002"
WORK = f"thread:project:{PID}:cccccccc-0000-4000-8000-000000000003"
SUBAGENT = "thread:delegated-task:command%3Amcp%3Axyz"
PURGED = "mcp:dddddddd-0000-4000-8000-000000000004"


def make_archive(root: Path) -> Path:
    """The backup-archive reader contract (written by t3-maintenance's t3_archive.py)."""
    path = root / "backups" / "t3-archive.sqlite"
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE threads (thread_id TEXT PRIMARY KEY, id_key TEXT, subagent INTEGER, project_id TEXT,
          project_title TEXT, workspace_root TEXT, workspace_name TEXT, title TEXT, created_at TEXT,
          updated_at TEXT, archived_at TEXT, user_msgs INTEGER, assistant_msgs INTEGER, last_msg_at TEXT);
        CREATE VIRTUAL TABLE entries USING fts5(text, thread_id UNINDEXED, seq UNINDEXED, role UNINDEXED,
          tool UNINDEXED, created_at UNINDEXED, tokenize = "unicode61 remove_diacritics 2");
        CREATE VIRTUAL TABLE vocab USING fts5vocab(entries, 'row');
        """
    )
    db.execute(
        "INSERT INTO threads VALUES (?,?,0,'p1','Personal','/Users/x/code/personal','personal',"
        "'Kerberos keytab rotation','2026-03-01T09:00:00Z','2026-03-02T09:00:00Z',NULL,1,1,'2026-03-01T10:00:00Z')",
        (PURGED, "dddddddd-0000-4000-8000-000000000004"),
    )
    db.execute(  # an archived copy of a live thread must not shadow it
        "INSERT INTO threads VALUES (?,?,0,'p1','Personal','/Users/x/code/personal','personal',"
        "'Measure Tenant Referral Engagement','2026-08-27T11:40:32Z','2026-08-27T13:00:00Z',NULL,1,0,NULL)",
        (REFERRAL, REFERRAL),
    )
    entries = [
        ("rotate the kerberos keytab on the build host", PURGED, 0, "user", "", "2026-03-01T09:01:00Z"),
        ("Rotated after a snapshot; the old principal is revoked.", PURGED, 1, "assistant", "", "2026-03-01T09:30:00Z"),
        ("Bash: kadmin -q ktadd buildhost\nEntry for principal added", PURGED, 2, "tool", "Bash", "2026-03-01T09:10:00Z"),
        ("snapshot referral stats", REFERRAL, 0, "user", "", "2026-08-27T11:41:00Z"),
    ]
    db.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?)", entries)
    db.commit()
    db.close()
    return path


def add_message(db, message_id, thread_id, role, text, stamp):
    payload = json.dumps({"role": role, "text": text, "createdBy": "user" if role == "user" else "agent"})
    db.execute(
        "INSERT INTO orchestration_v2_projection_messages VALUES (?,?,?,?,?,?)",
        (message_id, thread_id, role, stamp, stamp, payload),
    )


def make_store(root: Path) -> Path:
    userdata = root / "userdata"
    userdata.mkdir(parents=True)
    store = userdata / "statev2.sqlite"
    db = sqlite3.connect(store)
    db.executescript(
        """
        CREATE TABLE projection_projects (project_id TEXT PRIMARY KEY, title TEXT NOT NULL,
          workspace_root TEXT NOT NULL, deleted_at TEXT);
        CREATE TABLE orchestration_v2_projection_threads (thread_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, archived_at TEXT, deleted_at TEXT, payload_json TEXT NOT NULL);
        CREATE TABLE orchestration_v2_projection_messages (message_id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, payload_json TEXT NOT NULL);
        """
    )
    db.execute("INSERT INTO projection_projects VALUES ('p1','Personal','/Users/x/code/personal', NULL)")
    db.execute(f"INSERT INTO projection_projects VALUES ('{PID}','Work','/Users/x/code/work', NULL)")
    threads = [
        (REFERRAL, "p1", "Measure Tenant Referral Engagement", "2026-08-27T11:40:32Z", "2026-08-27T13:00:00Z", None, None),
        (STYLING, "p1", "Fix button styling", "2026-05-01T09:00:00Z", "2026-05-01T10:00:00Z", "2026-05-02T00:00:00Z", None),
        (WORK, PID, "Ahoy events for patient emails", "2026-08-20T09:00:00Z", "2026-08-20T12:00:00Z", None, None),
        (SUBAGENT, PID, "Ahoy worker", "2026-08-21T09:00:00Z", "2026-08-21T12:00:00Z", None, "subagent"),
    ]
    for thread_id, project, title, created, updated, archived, relation in threads:
        payload = json.dumps({"lineage": {"relationshipToParent": relation, "parentThreadId": None}})
        db.execute(
            "INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?,?,?,?,NULL,?)",
            (thread_id, project, title, created, updated, archived, payload),
        )
    messages = [
        ("m1", REFERRAL, "user", "count ahoy_events per tenant from the rds snapshot for stats", "2026-08-27T11:41:00Z"),
        ("m2", REFERRAL, "assistant", "I restored the rds snapshot and queried ahoy_events. " + "detail " * 60, "2026-08-27T11:45:00Z"),
        ("m3", REFERRAL, "user", "yes use the snapshot", "2026-08-27T11:50:00Z"),
        ("m4", STYLING, "user", "the button padding is off", "2026-05-01T09:01:00Z"),
        ("m5", WORK, "assistant", "ahoy_events table has no rows for this tenant", "2026-08-20T09:30:00Z"),
        ("m6", SUBAGENT, "user", "ahoy_events worker brief", "2026-08-21T09:30:00Z"),
    ]
    for message in messages:
        add_message(db, *message)
    db.commit()
    db.close()
    return store


class FindThreadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.store = make_store(root / "t3")
        make_archive(root / "t3")
        os.environ["T3CODE_HOME"] = str(root / "t3")
        os.environ["T3_FIND_CACHE_DIR"] = str(root / "cache")
        loader = importlib.machinery.SourceFileLoader("t3findthread", str(HERE / "t3-find-thread"))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        cls.mod = module

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_cli(self, *argv) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.mod.main(list(argv))
        return buffer.getvalue()

    def search(self, *argv) -> list[dict]:
        return json.loads(self.run_cli("search", "--format", "json", *argv))["results"]

    # --- ids / index ---------------------------------------------------------

    def test_short_ids_use_the_embedded_uuid(self):
        self.assertEqual(self.mod.short_id(REFERRAL), "aaaaaaaa")
        self.assertEqual(self.mod.short_id(STYLING), "bbbbbbbb")
        self.assertEqual(self.mod.short_id(WORK), "cccccccc")
        self.assertEqual(len(self.mod.short_id(SUBAGENT)), 8)  # sha1 fallback

    def test_index_then_incremental_is_a_noop(self):
        self.assertEqual(self.mod.sync_index(self.store, rebuild=True)["threads_refreshed"], 4)
        self.assertEqual(self.mod.sync_index(self.store)["threads_refreshed"], 0)

    def test_cache_version_bump_forces_rebuild(self):
        self.mod.sync_index(self.store)
        with sqlite3.connect(self.mod.CACHE_DB) as cache:
            cache.execute("UPDATE meta SET value = 'old' WHERE key = 'version'")
        self.assertEqual(self.mod.sync_index(self.store)["threads_refreshed"], 4)

    def test_incremental_picks_up_a_new_message(self):
        self.mod.sync_index(self.store, rebuild=True)
        db = sqlite3.connect(self.store)
        add_message(db, "m9", STYLING, "user", "also fix the kerning", "2026-09-01T09:00:00Z")
        db.commit()
        self.assertEqual(self.mod.sync_index(self.store)["threads_refreshed"], 1)
        self.assertEqual(self.run_cli("search", "--format", "ids", "kerning").split(), ["bbbbbbbb"])
        db.execute("DELETE FROM orchestration_v2_projection_messages WHERE message_id='m9'")
        db.commit()
        db.close()
        self.mod.sync_index(self.store, rebuild=True)

    # --- search --------------------------------------------------------------

    def test_ranking_prefers_user_hits_and_more_terms(self):
        results = self.search("ahoy", "snapshot", "stats")
        self.assertEqual([r["thread_id"] for r in results], [REFERRAL, WORK])
        self.assertEqual(len(results[0]["terms_hit"]), 3)

    def test_subagents_hidden_unless_asked(self):
        self.assertNotIn(SUBAGENT, [r["thread_id"] for r in self.search("ahoy")])
        self.assertIn(SUBAGENT, [r["thread_id"] for r in self.search("--subagents", "ahoy")])

    def test_all_requires_every_term(self):
        self.assertEqual([r["thread_id"] for r in self.search("--all", "ahoy", "snapshot")], [REFERRAL])

    def test_project_fuzzy_and_typo(self):
        for needle in ("personal", "Persona"):
            self.assertEqual([r["thread_id"] for r in self.search("--project", needle, "ahoy")], [REFERRAL], needle)

    def test_date_and_archive_filters(self):
        self.assertEqual(len(self.search("--since", "2026-08-01", "ahoy")), 2)
        results = self.search("--until", "2026-06-01", "--title-only", "button")
        self.assertEqual([r["thread_id"] for r in results], [STYLING])
        self.assertTrue(results[0]["archived"])
        self.assertEqual(self.search("--no-archived", "--title-only", "button"), [])

    def test_fuzzy_expansion_catches_a_typo(self):
        self.assertEqual(self.search("snapshopt"), [])
        self.assertEqual([r["thread_id"] for r in self.search("--fuzzy", "snapshopt")], [REFERRAL])

    def test_md_table_links_titles_natively(self):
        out = self.run_cli("search", "--project", "work", "ahoy")
        self.assertIn(f"[Ahoy events for patient emails](t3-thread://v1/{WORK})", out)
        self.assertIn("| `cccccccc` |", out)

    # --- peek / grep ----------------------------------------------------------

    def test_peek_by_short_id_truncates_prompts_and_outlines(self):
        payload = json.loads(self.run_cli("--json", "peek", "aaaaaaaa", "--prompts", "1"))
        self.assertEqual(payload[0]["thread_id"], REFERRAL)
        self.assertEqual(len(payload[0]["prompts"]), 1)
        self.assertEqual(len(payload[0]["outline"]), 3)
        self.assertTrue(payload[0]["outline"][1]["head"].endswith("…"))

    def test_peek_accepts_full_and_comma_separated_ids(self):
        payload = json.loads(self.run_cli("--json", "peek", f"{WORK},bbbbbbbb"))
        self.assertEqual([p["thread_id"] for p in payload], [WORK, STYLING])

    def test_grep_returns_snippets_per_term(self):
        payload = json.loads(self.run_cli("--json", "grep", "aaaaaaaa", "-k", "snapshot", "-k", "restore"))
        self.assertEqual({s["term"] for s in payload["snippets"]}, {"snapshot", "restore"})

    # --- backup archive fallback ---------------------------------------------------

    def test_no_live_hit_falls_back_to_the_archive(self):
        results = self.search("ktadd")
        self.assertEqual([(r["thread_id"], r["backup"]) for r in results], [(PURGED, True)])
        out = self.run_cli("search", "keytab")
        self.assertIn("+backup (no live hit)", out)
        self.assertIn("Kerberos keytab rotation _(backup)_", out)
        self.assertNotIn(f"t3-thread://v1/{PURGED}", out)  # purged: no dead link

    def test_live_hit_skips_the_archive_unless_dates_predate_it(self):
        self.assertTrue(all(not r["backup"] for r in self.search("ahoy")))
        self.assertEqual([r["thread_id"] for r in self.search("snapshot")], [REFERRAL])  # live hit: archive not asked
        both = self.search("--since", "2026-01-01", "snapshot")  # archive joins; the live copy wins
        self.assertEqual(sorted((r["thread_id"], r["backup"]) for r in both), [(REFERRAL, False), (PURGED, True)])
        partial = self.search("snapshot", "keytab")  # live covers 1/2 terms: the archive joins and wins
        self.assertEqual([(r["thread_id"], len(r["terms_hit"])) for r in partial[:2]], [(PURGED, 2), (REFERRAL, 1)])
        self.assertEqual(self.search("--backup", "off", "ktadd"), [])

    def test_peek_and_grep_read_backup_threads(self):
        peek = json.loads(self.run_cli("--json", "peek", "dddddddd"))[0]
        self.assertTrue(peek["backup"])
        self.assertEqual([o["role"] for o in peek["outline"]], ["user", "assistant"])
        grep = json.loads(self.run_cli("--json", "grep", "dddddddd", "ktadd"))
        self.assertEqual(grep["snippets"][0]["role"], "Bash")
        self.assertEqual(grep["snippets"][0]["idx"], 2)  # same numbering as read --tools
        story = json.loads(self.run_cli("--json", "read", "dddddddd", "--tools", "--from", "1"))["entries"]
        self.assertEqual([(e["idx"], e["role"]) for e in story], [(1, "assistant"), (2, "Bash")])
        self.assertIn("revoked", self.run_cli("read", "dddddddd"))
        self.assertIn("--from 2 --tools --limit 1", self.run_cli("read", "dddddddd", "--tools", "--limit", "1", "--from", "1"))

    def test_short_id_must_be_long_enough(self):
        with self.assertRaises(SystemExit):
            self.run_cli("--json", "peek", "aaaa")


if __name__ == "__main__":
    unittest.main()
