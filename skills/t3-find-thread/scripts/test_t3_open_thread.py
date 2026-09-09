#!/usr/bin/env python3
"""Unit tests for t3-open-thread (id/URL parsing + AppleScript escaping)."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load():
    loader = importlib.machinery.SourceFileLoader("t3_open_thread", str(HERE / "t3-open-thread"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


mod = load()
FULL = "2ac7596e-e879-41dd-a1fa-584a85ae1ed2"


class ParseIdent(unittest.TestCase):
    def test_forms(self):
        for arg, expected in [
            (FULL, FULL),
            (f"http://127.0.0.1:3773/env-123/{FULL}", FULL),
            (f"http://127.0.0.1:3773/env-123/{FULL}?x=1#y", FULL),
            ("2AC7596E", "2ac7596e"),
        ]:
            self.assertEqual(mod.parse_ident(arg), expected, arg)

    def test_rejects_garbage(self):
        with self.assertRaises(SystemExit):
            mod.parse_ident("not-an-id!!")


class Escaping(unittest.TestCase):
    def test_quote(self):
        self.assertEqual(mod.applescript_quote('a "b" c\\d'), 'a \\"b\\" c\\\\d')

    def test_ascii_title_is_typed(self):
        script = mod.palette_script('Fix "RDS" \\ snapshot')
        self.assertIn('keystroke "Fix \\"RDS\\" \\\\ snapshot"', script)
        self.assertIn('keystroke "k" using command down', script)
        self.assertIn("key code 36", script)

    def test_non_ascii_title_is_pasted(self):
        with mock.patch.object(mod.subprocess, "run") as run:
            script = mod.palette_script("Café ✅ thread")
        self.assertIn('keystroke "v" using command down', script)
        self.assertEqual(run.call_args.args[0], ["pbcopy"])
        self.assertEqual(run.call_args.kwargs["input"], "Café ✅ thread".encode())


if __name__ == "__main__":
    unittest.main()
