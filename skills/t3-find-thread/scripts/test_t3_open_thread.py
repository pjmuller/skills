#!/usr/bin/env python3
"""Unit tests for t3-open-thread (id resolution + link formats) against a synthetic statev2 store."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
UUID = "c811b689-7c9e-45d1-b3db-4e96979e254a"
MCP = "mcp:1ba7627e-55f7-48bb-8acf-a59f71c43091"
DELEGATED = "thread:delegated-task:command%3Amcp%3Axyz"


def load():
    loader = importlib.machinery.SourceFileLoader("t3_open_thread", str(HERE / "t3-open-thread"))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class OpenThread(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        store = Path(cls.tmp.name) / "statev2.sqlite"
        db = sqlite3.connect(store)
        db.execute("CREATE TABLE orchestration_v2_projection_threads (thread_id TEXT, title TEXT, deleted_at TEXT)")
        db.executemany(
            "INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?)",
            [(UUID, "Simplify [native] T3 workers", None), (MCP, "Worker", None), (DELEGATED, "Delegated", None),
             ("c811b689-0000-4000-8000-00000000dead", "Deleted twin", "2026-10-01")],
        )
        db.commit()
        db.close()
        cls.mod = load()
        cls.mod.STORE = store

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_resolution(self):
        self.assertEqual(self.mod.lookup("C811B689")[0], UUID)  # deleted twin ignored
        self.assertEqual(self.mod.lookup("1ba7627e")[0], MCP)
        self.assertEqual(self.mod.lookup(DELEGATED)[0], DELEGATED)
        for bad in ("c811", "deadbeef"):
            with self.assertRaises(SystemExit):
                self.mod.lookup(bad)

    def test_links(self):
        self.assertEqual(self.mod.markdown_link("Simplify [native] T3 workers", MCP),
                         f"[Simplify (native) T3 workers](t3-thread://v1/{MCP})")
        self.assertEqual(self.mod.desktop_url("env-1", MCP),
                         "t3code://threads/env-1/mcp%3A1ba7627e-55f7-48bb-8acf-a59f71c43091")


if __name__ == "__main__":
    unittest.main()
