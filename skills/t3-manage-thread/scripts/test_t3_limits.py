"""Unit tests for the t3-limits helper (no network, no Keychain).

python3 -m unittest scripts/test_t3_limits.py
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_loader(
    "t3_limits",
    importlib.machinery.SourceFileLoader(
        "t3_limits", str(Path(__file__).resolve().parent / "t3-limits")
    ),
)
t3_limits = importlib.util.module_from_spec(SPEC)
sys.modules["t3_limits"] = t3_limits
SPEC.loader.exec_module(t3_limits)

NOW = datetime(2026, 9, 5, 7, 5, tzinfo=timezone.utc)

CLAUDE_PAYLOAD = {
    "five_hour": {
        "utilization": 100.0,
        "resets_at": "2026-09-05T08:10:00.158842+00:00",
    },
    "seven_day": {"utilization": 16.0, "resets_at": "2026-09-05T15:00:00.158867+00:00"},
    "extra_usage": {
        "is_enabled": True,
        "monthly_limit": 6750,
        "used_credits": 1271.0,
        "utilization": 18.82962962962963,
        "currency": "EUR",
        "decimal_places": 2,
        "spend_limit_reached": False,
    },
    "limits": [
        {
            "kind": "session",
            "percent": 100,
            "resets_at": "2026-09-05T08:10:00.158842+00:00",
            "scope": None,
        },
        {
            "kind": "weekly_all",
            "percent": 16,
            "resets_at": "2026-09-05T15:00:00.158867+00:00",
            "scope": None,
        },
        {
            "kind": "weekly_scoped",
            "percent": 19,
            "resets_at": "2026-09-05T15:00:00.159102+00:00",
            "scope": {"model": {"id": None, "display_name": "Fable"}},
        },
    ],
}

CODEX_PAYLOAD = {
    "pace": {"secondary": {"summary": "20% in deficit | Runs out in 11h 51m"}},
    "usage": {
        "accountEmail": "info@probackup.io",
        "loginMethod": "pro",
        "primary": None,
        "secondary": {
            "usedPercent": 91,
            "windowMinutes": 10080,
            "resetsAt": "2026-09-07T05:25:09Z",
        },
        "extraRateWindows": [
            {
                "id": "codex-spark",
                "title": "Codex Spark 5-hour",
                "window": {
                    "usedPercent": 0,
                    "resetsAt": "2026-09-05T10:07:22Z",
                    "windowMinutes": 300,
                },
            }
        ],
        "codexResetCredits": {"availableCount": 3},
    },
}


class KeychainServiceTest(unittest.TestCase):
    def test_default_profile_uses_base_name(self):
        self.assertEqual(t3_limits.keychain_service(""), "Claude Code-credentials")

    def test_per_profile_hashes(self):
        self.assertEqual(
            t3_limits.keychain_service("/Users/pjmuller/.claude_kampkompas_home"),
            "Claude Code-credentials-892716b7",
        )
        self.assertEqual(
            t3_limits.keychain_service("/Users/pjmuller/.claude_dentai_home"),
            "Claude Code-credentials-b6deab74",
        )

    def test_tilde_expands_to_the_same_hash(self):
        self.assertEqual(
            t3_limits.keychain_service("~/.claude_kampkompas_home"),
            "Claude Code-credentials-892716b7",
        )


class ClaudeRowsTest(unittest.TestCase):
    def test_rows_ignore_extra_usage(self):
        rows, notes = t3_limits.claude_rows(CLAUDE_PAYLOAD)
        self.assertEqual(
            [(row.window, row.used_percent) for row in rows],
            [("session", 100.0), ("weekly", 16.0), ("Fable only", 19.0)],
        )
        self.assertEqual(
            rows[0].resets_at,
            datetime(2026, 9, 5, 8, 10, 0, 158842, tzinfo=timezone.utc),
        )
        self.assertEqual(notes, [])  # paid overage is deliberately not reported

    def test_falls_back_to_top_level_windows(self):
        rows, _ = t3_limits.claude_rows(dict(CLAUDE_PAYLOAD, limits=[]))
        self.assertEqual([row.window for row in rows], ["session", "weekly"])

    def test_expired_token_reports_instead_of_raising(self):
        settings = self._settings()

        def fetch(_token):
            raise urllib.error.HTTPError(
                t3_limits.USAGE_URL, 401, "unauthorized", {}, None
            )

        accounts = t3_limits.claude_accounts(fetch=fetch, settings_path=settings)
        self.assertEqual(
            [account.error for account in accounts], [t3_limits.EXPIRED_HINT]
        )

    def _settings(self) -> Path:
        path = Path(tempfile.mkdtemp()) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "providerInstances": {
                        "grok": {"driver": "grok", "enabled": False},
                        "claudeAgent_dentai": {
                            "driver": "claudeAgent",
                            "enabled": True,
                            "displayName": "Claude DentAI",
                            "config": {"homePath": "~/.claude_dentai_home"},
                        },
                    }
                }
            )
        )
        return path


class CodexRowsTest(unittest.TestCase):
    def test_null_primary_and_extra_windows(self):
        account = t3_limits.codex_account(fetch=lambda: CODEX_PAYLOAD)
        self.assertEqual(account.plan, "pro")
        self.assertEqual(account.label, "Codex  info@probackup.io")
        self.assertEqual(
            [(row.window, row.used_percent, row.length_seconds) for row in account.rows],
            [("weekly", 91.0, 10080 * 60)],  # Spark sub-windows are dropped
        )
        self.assertEqual(account.notes, ["reset credits: 3"])

    def test_missing_cli_becomes_an_error_row(self):
        def fetch():
            raise FileNotFoundError("codexbar not found")

        account = t3_limits.codex_account(fetch=fetch)
        self.assertIn("codexbar", account.error)
        self.assertEqual(account.rows, [])


class FormattingTest(unittest.TestCase):
    def test_relative(self):
        self.assertEqual(t3_limits.relative(0), "now")
        self.assertEqual(t3_limits.relative(45 * 60), "in 45m")
        self.assertEqual(t3_limits.relative(3 * 3600 + 5 * 60), "in 3h05")
        self.assertEqual(t3_limits.relative(2 * 86400), "in 2d00h")

    def test_reset_text_same_day_vs_other_day(self):
        same = NOW + timedelta(hours=3, minutes=5)
        self.assertEqual(t3_limits.reset_text(same, NOW), "resets 12:10 (in 3h05)")
        later = datetime(2026, 9, 7, 5, 25, 9, tzinfo=timezone.utc)
        self.assertEqual(
            t3_limits.reset_text(later, NOW), "resets Sep 7 07:25 (in 1d22h)"
        )
        self.assertEqual(t3_limits.reset_text(None, NOW), "no reset")

    def test_json_rows(self):
        account = t3_limits.codex_account(fetch=lambda: CODEX_PAYLOAD)
        rows = t3_limits.json_rows([account], NOW)
        self.assertEqual(rows[0]["instance_id"], "codex")
        self.assertEqual(rows[0]["window"], "weekly")
        self.assertEqual(rows[0]["resets_at"], "2026-09-07T05:25:09Z")
        self.assertEqual(rows[0]["resets_in_seconds"], 166809)
        self.assertEqual(rows[0]["window_seconds"], 604800)
        self.assertEqual(rows[0]["pace_percent"], 72.4)  # 166809 s left of 7 d
        self.assertEqual(rows[0]["room_percent"], -18.6)

    def test_json_rows_include_errored_accounts(self):
        account = t3_limits.Account(label="Boom", instance_id="x", error="token expired")
        self.assertEqual(
            t3_limits.json_rows([account], NOW),
            [
                {
                    "account": "Boom",
                    "instance_id": "x",
                    "window": None,
                    "error": "token expired",
                }
            ],
        )


class PaceTest(unittest.TestCase):
    def test_session_pace_and_room(self):
        row = t3_limits.Row("session", 10.0, NOW + timedelta(hours=4), 5 * 3600)
        expected, room = row.pace(NOW)
        self.assertAlmostEqual(expected, 20.0)
        self.assertAlmostEqual(room, 10.0)

    def test_stale_or_unknown_window_has_no_pace(self):
        self.assertIsNone(t3_limits.Row("session", 0.0, None, 5 * 3600).pace(NOW))
        self.assertIsNone(
            t3_limits.Row("session", 0.0, NOW - timedelta(minutes=1), 5 * 3600).pace(NOW)
        )
        self.assertIsNone(t3_limits.Row("x", 0.0, NOW + timedelta(hours=1)).pace(NOW))

    def test_markdown_has_one_row_per_window(self):
        account = t3_limits.codex_account(fetch=lambda: CODEX_PAYLOAD)
        text = t3_limits.render_markdown([account], NOW)
        self.assertIn("| Codex  info@probackup.io | `codex` | weekly | 91% | 72% | -19 |", text)


if __name__ == "__main__":
    unittest.main()
