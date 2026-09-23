"""Unit tests for the t3-limits helper (no network, no Keychain).

python3 -m unittest scripts/test_t3_limits.py
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_loader(
    "t3_limits",
    importlib.machinery.SourceFileLoader(
        "t3_limits", str(Path(__file__).resolve().parent / "lib" / "t3_limits.py")
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

CODEX_PAYLOAD = {  # chatgpt.com/backend-api/wham/usage
    "email": "user@example.com",
    "plan_type": "pro",
    "rate_limit": {
        "primary_window": {"used_percent": 91, "limit_window_seconds": 604800, "reset_at": 1788758709},
        "secondary_window": None,
    },
    "additional_rate_limits": [
        {"limit_name": "gpt-reserve", "normal_model_slug": "gpt-5.6-luna",
         "rate_limit": {"primary_window": {"used_percent": 0, "limit_window_seconds": 604800, "reset_at": 1790000000}}}
    ],
    "rate_limit_reset_credits": {"available_count": 3},
}


def codex_account(payload=CODEX_PAYLOAD) -> "t3_limits.Account":
    plan, rows, notes = t3_limits.codex_rows(payload)
    return t3_limits.Account("Codex Alpha", "codex", plan, rows, notes)


class KeychainServiceTest(unittest.TestCase):
    def test_default_profile_uses_base_name(self):
        self.assertEqual(t3_limits.keychain_service(""), "Claude Code-credentials")

    def test_per_profile_hashes(self):
        self.assertEqual(
            t3_limits.keychain_service("/Users/example/.claude_personal_home"),
            "Claude Code-credentials-ab379f19",
        )
        self.assertEqual(
            t3_limits.keychain_service("/Users/example/.claude_work_home"),
            "Claude Code-credentials-202b9f55",
        )

    @patch.dict("os.environ", {"HOME": "/Users/example"})
    def test_tilde_expands_to_the_same_hash(self):
        self.assertEqual(
            t3_limits.keychain_service("~/.claude_personal_home"),
            "Claude Code-credentials-ab379f19",
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

    @patch.object(t3_limits, "keychain_token", return_value={"accessToken": "fixture-token"})
    def test_expired_token_reports_instead_of_raising(self, _token):
        settings = settings_fixture()

        def fetch(_token):
            raise urllib.error.HTTPError(
                t3_limits.USAGE_URL, 401, "unauthorized", {}, None
            )

        accounts = t3_limits.claude_accounts(fetch=fetch, settings_path=settings, cache_path=settings.parent / "cache.json")
        self.assertEqual(
            [account.error for account in accounts], [t3_limits.EXPIRED_HINT]
        )


def settings_fixture() -> Path:
    """T3 settings.json with one enabled claudeAgent instance."""
    path = Path(tempfile.mkdtemp()) / "settings.json"
    path.write_text(
        json.dumps(
            {
                "providerInstances": {
                    "claudeAgent": {"driver": "claudeAgent", "enabled": False},
                    "grok": {"driver": "grok", "enabled": False},
                    "claudeAgent_work": {
                        "driver": "claudeAgent",
                        "enabled": True,
                        "displayName": "Claude Work",
                        "config": {"homePath": "~/.claude_work_home"},
                    },
                }
            }
        )
    )
    return path


class CacheTest(unittest.TestCase):
    """The usage endpoint is shared with other pollers, so 429s are routine."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = self.tmp / "t3-limits-cache.json"
        self.settings = settings_fixture()
        patcher = patch.object(
            t3_limits, "keychain_token", return_value={"accessToken": "fixture-token"}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_cache(self, age_seconds: float):
        self.cache.write_text(
            json.dumps(
                {
                    "claudeAgent_work": {
                        "payload": CLAUDE_PAYLOAD,
                        "fetched_at": NOW.timestamp() - age_seconds,
                        "identity": "~/.claude_work_home|",
                    }
                }
            )
        )

    def _accounts(self, fetch, **kwargs):
        return t3_limits.claude_accounts(
            fetch=fetch,
            settings_path=self.settings,
            cache_path=self.cache,
            now=NOW,
            **kwargs,
        )

    def test_fresh_cache_entry_skips_the_network(self):
        self._write_cache(30)

        def fetch(_token):
            raise AssertionError("must not hit the network")

        [account] = self._accounts(fetch)
        self.assertEqual(account.error, "")
        self.assertFalse(account.stale)  # fresh enough to pass as live
        self.assertEqual([row.window for row in account.rows], ["session", "weekly", "Fable only"])

    def test_fresh_flag_bypasses_the_cache_and_rewrites_it(self):
        self._write_cache(30)
        calls = []

        def fetch(token):
            calls.append(token)
            return dict(CLAUDE_PAYLOAD, limits=[])

        [account] = self._accounts(fetch, fresh=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual([row.window for row in account.rows], ["session", "weekly"])
        stored = json.loads(self.cache.read_text())["claudeAgent_work"]
        self.assertEqual(stored["fetched_at"], NOW.timestamp())
        self.assertNotIn("fixture-token", self.cache.read_text())
        self.assertEqual(self.cache.stat().st_mode & 0o777, 0o600)

    def test_429_falls_back_to_a_recent_cache_entry(self):
        self._write_cache(3 * 60)
        calls = []

        def fetch(_token):
            calls.append(1)
            raise urllib.error.HTTPError(
                t3_limits.USAGE_URL, 429, "too many", {"Retry-After": "0"}, None
            )

        with patch.object(t3_limits.time, "sleep") as sleep:
            [account] = self._accounts(fetch)
        self.assertEqual(len(calls), 2)  # one short retry before falling back
        sleep.assert_called_once_with(0.0)
        self.assertEqual(account.error, "")
        self.assertTrue(account.stale)
        self.assertEqual(account.rows[0].used_percent, 100.0)
        self.assertIn("(cached 3m ago)", t3_limits.render([account], NOW))
        row = t3_limits.json_rows([account], NOW)[0]
        self.assertTrue(row["stale"])
        self.assertEqual(row["fetched_at"], "2026-09-05T07:02:00Z")

    def test_429_without_usable_cache_reports_the_error(self):
        self._write_cache(20 * 60)  # too old to trust

        def fetch(_token):
            raise urllib.error.HTTPError(
                t3_limits.USAGE_URL, 429, "too many", {}, None
            )

        with patch.object(t3_limits.time, "sleep"):
            [account] = self._accounts(fetch)
        self.assertEqual(account.error, "HTTP 429")
        # Too old to serve as a reading, but the exhausted session (reset in the
        # future) survives as evidence so routing keeps excluding the account.
        self.assertEqual([(r.window, r.used_percent) for r in account.rows], [("session", 100.0)])
        self.assertFalse(account.stale)
        self.assertIsNotNone(account.fetched_at)

    def test_cache_bound_to_identity(self):
        self._write_cache(30)
        cached = json.loads(self.cache.read_text())
        cached["claudeAgent_work"]["identity"] = "~/.other_home|"
        self.cache.write_text(json.dumps(cached))
        calls = []

        def fetch(_token):
            calls.append(1)
            return dict(CLAUDE_PAYLOAD, limits=[])

        [account] = self._accounts(fetch)
        self.assertEqual(len(calls), 1)  # a different home/account never reuses the entry
        self.assertEqual(json.loads(self.cache.read_text())["claudeAgent_work"]["identity"],
                         "~/.claude_work_home|")


class CodexRowsTest(unittest.TestCase):
    def test_windows_notes_and_plan(self):
        account = codex_account()
        self.assertEqual(account.plan, "pro · user@example.com")
        self.assertEqual(
            [(row.window, row.used_percent, row.length_seconds) for row in account.rows],
            [("weekly", 91.0, 604800)],  # optional secondary window absent
        )
        self.assertEqual(account.notes, ["gpt-reserve (gpt-5.6-luna): 0% used", "reset credits: 3"])

    def test_secondary_and_nonstandard_windows(self):
        payload = {"rate_limit": {
            "primary_window": {"used_percent": 12, "limit_window_seconds": 18000, "reset_at": 1789795509},
            "secondary_window": {"used_percent": None, "limit_window_seconds": 10800, "reset_at": 1789795509},
        }}
        _, rows, _ = t3_limits.codex_rows(payload)
        self.assertEqual([r.window for r in rows], ["session", "3h"])
        self.assertTrue(math.isnan(rows[1].used_percent))  # missing % is unknown, not 0
        row = t3_limits.json_rows([codex_account(payload)], NOW)[1]
        self.assertIsNone(row["used_percent"])
        self.assertIsNone(row["room_percent"])
        json.dumps(row, allow_nan=False)  # strict consumers must not see NaN

    def test_malformed_payload_is_unknown_not_a_crash(self):
        settings = Path(tempfile.mkdtemp()) / "settings.json"
        settings.write_text(json.dumps({"providerInstances": {
            "codex": {"driver": "codex", "enabled": True, "config": {"homePath": str(settings.parent / "a")}},
            "codex_b": {"driver": "codex", "enabled": True, "config": {"homePath": str(settings.parent / "b")}}}}))
        for home in ("a", "b"):
            (settings.parent / home).mkdir()
            (settings.parent / home / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {
                "access_token": "secret", "account_id": home}}))
        bad = {"rate_limit": {"primary_window": {"used_percent": 10, "limit_window_seconds": 604800, "reset_at": "bad"}}}
        fetch = lambda c: bad if c["identity"] == "a" else CODEX_PAYLOAD
        first, second = t3_limits.codex_accounts(fetch=fetch, settings_path=settings,
                                                 cache_path=settings.parent / "cache.json", now=NOW)
        self.assertIn("malformed", first.error)
        self.assertEqual(first.rows, [])
        self.assertEqual(second.error, "")
        self.assertEqual(second.rows[0].used_percent, 91.0)

    def test_codex_credentials_from_home(self):
        home = Path(tempfile.mkdtemp())
        with self.assertRaises(LookupError):
            t3_limits.codex_credentials(str(home))
        (home / "auth.json").write_text(json.dumps({"auth_mode": "apikey", "tokens": {}}))
        with self.assertRaises(LookupError):
            t3_limits.codex_credentials(str(home))
        (home / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {
            "access_token": "secret", "account_id": "acc-1"}}))
        credentials = t3_limits.codex_credentials(str(home))
        self.assertEqual(credentials["identity"], "acc-1")

    def test_missing_login_becomes_an_error_row(self):
        settings = Path(tempfile.mkdtemp()) / "settings.json"
        settings.write_text(json.dumps({"providerInstances": {"codex": {
            "driver": "codex", "enabled": True, "config": {"homePath": str(settings.parent / "nohome")}}}}))
        [account] = t3_limits.codex_accounts(fetch=lambda _c: CODEX_PAYLOAD, settings_path=settings,
                                             cache_path=settings.parent / "cache.json", now=NOW)
        self.assertIn("no Codex login", account.error)
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
        account = codex_account()
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
        account = codex_account()
        text = t3_limits.render_markdown([account], NOW)
        self.assertIn("| Codex Alpha | `codex` | weekly | 91% | 72% | -19 |", text)


if __name__ == "__main__":
    unittest.main()
