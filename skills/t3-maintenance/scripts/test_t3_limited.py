#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import importlib.util
import json
import os
import plistlib
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).with_name("t3-limited")
TZ = ZoneInfo("Europe/Brussels")


def load_cli():
    """The CLI has no .py suffix; import it by path to unit-test helpers."""
    loader = SourceFileLoader("t3limited", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class LimitedFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = Path(self.temp.name) / "state.sqlite"
        connection = sqlite3.connect(self.store)
        connection.executescript("""
            CREATE TABLE projection_projects (
              project_id TEXT PRIMARY KEY, title TEXT, workspace_root TEXT
            );
            CREATE TABLE projection_threads (
              thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, created_at TEXT,
              deleted_at TEXT, archived_at TEXT, model_selection_json TEXT
            );
            CREATE TABLE projection_thread_messages (
              message_id TEXT PRIMARY KEY, thread_id TEXT, role TEXT, text TEXT,
              created_at TEXT
            );
            INSERT INTO projection_projects VALUES ('p','fixture','/tmp/fixture');
        """)
        now = datetime.now(timezone.utc)
        self.now = now

        def thread(
            short: str,
            title: str,
            *,
            profile: str = "claudeAgent",
            archived: str | None = None,
        ) -> str:
            thread_id = f"{short}-0000-0000-0000-0000000{short}"
            connection.execute(
                "INSERT INTO projection_threads VALUES (?,?,?,?,?,?,?)",
                (
                    thread_id,
                    "p",
                    title,
                    stamp(now - timedelta(days=2)),
                    None,
                    archived,
                    json.dumps({"instanceId": profile, "model": "fable-5"}),
                ),
            )
            return thread_id

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

        # Blocked on a session limit that already reset (2h ago, resets 1h ago).
        passed_at = (now - timedelta(hours=2)).astimezone(TZ)
        reset_local = (now - timedelta(hours=1)).astimezone(TZ)
        self.blocked = thread("aaaaaaaa", "session blocked")
        message("a1", self.blocked, "user", "go", 200)
        message(
            "a2",
            self.blocked,
            "assistant",
            f"You've hit your session limit · resets "
            f"{reset_local.strftime('%I:%M').lstrip('0')}"
            f"{reset_local.strftime('%p').lower()} (Europe/Brussels)",
            (now - passed_at.astimezone(timezone.utc)).total_seconds() / 60,
        )

        # Limited, but the user already replied afterwards -> not blocked.
        replied = thread("bbbbbbbb", "already replied")
        message(
            "b1",
            replied,
            "assistant",
            "You've hit your limit · resets 8pm (Europe/Brussels)",
            90,
        )
        message("b2", replied, "user", "continue", 80)

        # Archived thread with a live limit message -> excluded.
        archived = thread("cccccccc", "archived", archived=stamp(now))
        message(
            "c1",
            archived,
            "assistant",
            "You've hit your limit · resets 8pm (Europe/Brussels)",
            60,
        )

        # Monthly spend limit, dentai profile -> listed, skipped by resume.
        self.monthly = thread("dddddddd", "monthly spend", profile="claudeAgent_dentai")
        message(
            "d1",
            self.monthly,
            "assistant",
            "You've hit your monthly spend limit · raise it at claude.ai/settings/usage?x=1",
            30,
        )

        # Long prose merely mentioning a rate limit -> not matched.
        prose = thread("eeeeeeee", "prose")
        message(
            "e1",
            prose,
            "assistant",
            "You've hit your limit of patience, but here is the analysis. "
            + "word " * 120,
            15,
        )

        # API rate limit, codex profile, no reset time -> resumable.
        self.api = thread("ffffffff", "api error", profile="codex")
        message("f1", self.api, "assistant", "API Error: Rate limit reached", 10)

        # Model limit whose reset is still pending (in 3h).
        pending = (now + timedelta(hours=3)).astimezone(TZ)
        self.pending = thread("99999999", "model limit pending")
        message(
            "g1",
            self.pending,
            "assistant",
            f"You've reached your Fable 5 limit · resets "
            f"{pending.strftime('%I:%M').lstrip('0')}{pending.strftime('%p').lower()} "
            "(Europe/Brussels). Switch to another model.",
            5,
        )
        connection.commit()
        connection.close()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, *args: str, expect: int = 0) -> str:
        result = subprocess.run(
            [str(SCRIPT), "--store", str(self.store), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expect, f"{result.stdout}\n{result.stderr}")
        return result.stdout

    def rows(self, *args: str) -> list[dict]:
        return json.loads(self.run_script("list", "--json", *args))

    def test_only_currently_blocked_threads_are_listed(self) -> None:
        ids = [row["short_id"] for row in self.rows()]
        self.assertIn("aaaaaaaa", ids)
        self.assertNotIn("bbbbbbbb", ids)  # user replied after the limit message
        self.assertNotIn("cccccccc", ids)  # archived
        self.assertNotIn("eeeeeeee", ids)  # long prose, not a limit banner
        self.assertEqual(ids[0], "99999999")  # newest first

    def test_kinds_and_profile_filter(self) -> None:
        kinds = {row["short_id"]: row["kind"] for row in self.rows()}
        self.assertEqual(kinds["aaaaaaaa"], "session")
        self.assertEqual(kinds["dddddddd"], "monthly")
        self.assertEqual(kinds["ffffffff"], "api")
        self.assertEqual(kinds["99999999"], "model")
        self.assertEqual(
            [row["short_id"] for row in self.rows("--profile", "dentai")], ["dddddddd"]
        )
        self.assertEqual(
            [row["short_id"] for row in self.rows("--profile", "CODEX")], ["ffffffff"]
        )
        self.assertEqual(
            {row["short_id"] for row in self.rows("--profile", "claude")},
            {"aaaaaaaa", "dddddddd", "99999999"},
        )

    def test_reset_parsing_and_since_window(self) -> None:
        by_id = {row["short_id"]: row for row in self.rows()}
        self.assertTrue(by_id["aaaaaaaa"]["reset_passed"])
        self.assertFalse(by_id["99999999"]["reset_passed"])
        self.assertIsNone(by_id["ffffffff"]["reset_at"])
        self.assertEqual(
            [row["short_id"] for row in self.rows("--since", "20m")],
            ["99999999", "ffffffff"],
        )
        actionable = self.rows("--resumable", "--exclude", self.blocked[:8])
        self.assertEqual([row["short_id"] for row in actionable], ["ffffffff"])
        before = stamp(self.now - timedelta(minutes=15))
        self.assertEqual(
            {row["short_id"] for row in self.rows("--before", before)},
            {"aaaaaaaa", "dddddddd"},
        )

    def test_monthly_banner_with_a_session_reset_is_resumable(self) -> None:
        module = load_cli()
        text = (
            "You've hit your monthly spend limit \u00b7 raise it at "
            "claude.ai/settings/usage?x=1 \u00b7 your session limit resets 4:50pm "
            "(Europe/Brussels)"
        )
        self.assertEqual(module.classify(text), "session")
        at = datetime(2026, 9, 5, 12, 0, tzinfo=TZ)
        reset = module.parse_reset(text, at)
        self.assertEqual((reset.hour, reset.minute), (16, 50))
        # Pure monthly cap, no reset time -> still fatal.
        self.assertEqual(
            module.classify("You've hit your monthly spend limit \u00b7 raise it"),
            "monthly",
        )

    def test_reset_rolls_over_to_the_next_day(self) -> None:
        module = load_cli()
        at = datetime(2026, 9, 5, 20, 0, tzinfo=TZ)
        self.assertEqual(
            module.parse_reset("resets 8am (Europe/Brussels)", at).date(),
            at.date() + timedelta(days=1),
        )
        same_day = module.parse_reset("resets 10:10pm (Europe/Brussels)", at)
        self.assertEqual(
            (same_day.date(), same_day.hour, same_day.minute), (at.date(), 22, 10)
        )
        self.assertIsNone(module.parse_reset("no reset here", at))

    def test_resume_dry_run_respects_reset_and_monthly_rules(self) -> None:
        output = self.run_script("resume", "--dry-run")
        self.assertIn(
            f"--thread {self.blocked} --allow-cross-project -- continue", output
        )
        self.assertIn(f"--thread {self.api}", output)
        self.assertNotIn(f"--thread {self.monthly}", output)  # monthly needs --force
        self.assertNotIn(f"--thread {self.pending}", output)  # reset not passed yet
        self.assertIn("skip   dddddddd", output)
        forced = self.run_script(
            "resume", "--dry-run", "--force", "--message", "resume pls"
        )
        self.assertIn(f"--thread {self.monthly}", forced)
        self.assertIn(f"--thread {self.pending}", forced)
        self.assertIn("-- resume pls", forced)
        excluded = self.run_script(
            "resume", "--dry-run", "--exclude", self.blocked[:8]
        )
        self.assertIn("skip   aaaaaaaa  held/excluded", excluded)
        self.assertNotIn(f"--thread {self.blocked}", excluded)

    def test_exact_instance_id_excludes_suffixed_ids(self) -> None:
        # `claudeAgent` is a prefix of every other Claude id -> exact match wins.
        self.assertEqual(
            {row["short_id"] for row in self.rows("--profile", "claudeAgent")},
            {"aaaaaaaa", "99999999"},
        )

    def test_resume_reports_nothing_to_do(self) -> None:
        self.assertIn(
            "Nothing to resume.",
            self.run_script("resume", "--dry-run", "--profile", "nope"),
        )

    def test_resume_times_out_a_wedged_ping_and_kills_its_children(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            helper = Path(temp) / "t3-ping-thread"
            helper.write_text("#!/bin/sh\nsleep 30 &\nwait\n")
            helper.chmod(0o755)
            old_path = os.environ["PATH"]
            os.environ["PATH"] = f"{temp}:{old_path}"
            try:
                output = self.run_script(
                    "resume", "--profile", "codex", "--timeout", "0.05", expect=1
                )
            finally:
                os.environ["PATH"] = old_path
            self.assertIn("FAILED ffffffff", output)
            self.assertIn("timed out after 0.05s", output)

    def test_resume_protects_current_drafts_and_fails_closed_on_lookup_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            drafts = Path(temp) / "t3-drafts"
            drafts.write_text(
                "#!/bin/sh\nprintf '%s\\n' "
                f"'[{json.dumps({'thread_id': self.blocked})}]'\n"
            )
            drafts.chmod(0o755)
            ping = Path(temp) / "t3-ping-thread"
            ping.write_text("#!/bin/sh\necho pinged\n")
            ping.chmod(0o755)
            old_path = os.environ["PATH"]
            os.environ["PATH"] = f"{temp}:{old_path}"
            try:
                output = self.run_script(
                    "resume", "--profile", "claudeAgent", "--protect-drafts"
                )
                self.assertIn("skip   aaaaaaaa  held/excluded", output)
                drafts.write_text("#!/bin/sh\nsleep 30\n")
                timed_out = self.run_script(
                    "resume", "--profile", "claudeAgent", "--protect-drafts",
                    "--draft-timeout", "0.05", expect=1,
                )
            finally:
                os.environ["PATH"] = old_path
            self.assertIn("FAILED draft safety check", timed_out)


class ProfileFilterTest(unittest.TestCase):
    """--profile resolution against instanceIds + T3 settings displayNames."""

    def setUp(self) -> None:
        self.module = load_cli()
        self.names = {
            "claudeAgent": "Claude ProBackup",
            "claudeAgent_dentai": "Claude DentAI",
            "codex": "",
        }
        self.profiles = set(self.names)

    def match(self, query: str) -> set[str]:
        return self.module.profile_matches(query, self.profiles, self.names)

    def test_display_name_substring_matches(self) -> None:
        self.assertEqual(self.match("probackup"), {"claudeAgent"})
        self.assertEqual(self.match("DentAI"), {"claudeAgent_dentai"})
        self.assertEqual(
            self.match("claude"), {"claudeAgent", "claudeAgent_dentai"}
        )
        self.assertEqual(self.match("claudeAgent"), {"claudeAgent"})

    def test_display_names_tolerate_a_missing_or_broken_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "nope.json"
            self.assertEqual(self.module.display_names(missing), {})
            settings = Path(temp) / "settings.json"
            settings.write_text(
                json.dumps(
                    {
                        "providerInstances": {
                            "claudeAgent": {"displayName": "Claude ProBackup"},
                            "grok": None,
                        }
                    }
                )
            )
            self.assertEqual(
                self.module.display_names(settings),
                {"claudeAgent": "Claude ProBackup", "grok": ""},
            )


class ScheduleTest(unittest.TestCase):
    """LaunchAgent generation, with $HOME redirected and launchctl stubbed."""

    def setUp(self) -> None:
        self.module = load_cli()
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.calls: list[tuple[str, ...]] = []
        os.environ["HOME"] = str(self.home)
        self.module.launchctl = self._launchctl
        self.spawned: list[list[str]] = []
        self.module.popen = self._popen

    def _popen(self, command, **kwargs):
        self.spawned.append(command)
        self.assertTrue(kwargs["start_new_session"])
        return types.SimpleNamespace(pid=0)  # only .pid is read

    def _launchctl(self, *args: str):
        self.calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    def tearDown(self) -> None:
        os.environ["HOME"] = self.real_home
        self.temp.cleanup()

    real_home = os.environ["HOME"]

    def plists(self) -> list[Path]:
        return sorted((self.home / "Library/LaunchAgents").glob("*.plist"))

    def test_schedule_writes_plist_and_script(self) -> None:
        target = datetime.now().astimezone() + timedelta(hours=2)
        self.module.main(
            ["schedule", "--profile", "dentai", "--at", target.strftime("%H:%M")]
        )
        (plist,) = self.plists()
        data = plistlib.loads(plist.read_bytes())
        label = f"com.pjmuller.t3-limited-resume.dentai.{target:%Y%m%d-%H%M}"
        self.assertEqual(data["Label"], label)
        self.assertFalse(data["RunAtLoad"])
        self.assertEqual(
            data["StartCalendarInterval"],
            {
                "Month": target.month,
                "Day": target.day,
                "Hour": target.hour,
                "Minute": target.minute,
            },
        )
        self.assertEqual(data["StartInterval"], 60)
        self.assertEqual(data["ProcessType"], "Interactive")
        script = self.home / ".t3/userdata/scheduled" / f"{label}.sh"
        self.assertEqual(data["ProgramArguments"], ["/bin/zsh", "-lc", str(script)])
        body = script.read_text()
        syntax = subprocess.run(
            ["zsh", "-n", str(script)], capture_output=True, text=True, check=False
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        self.assertIn("t3-limited resume --profile dentai --since 7d", body)
        self.assertIn("t3-limited-schedule.log", body)
        self.assertIn(f"launchctl bootout gui/$(id -u)/{label}", body)
        self.assertEqual(self.calls[0][0], "bootstrap")

    def test_schedule_spawns_caffeinate_until_fire(self) -> None:
        target = (datetime.now().astimezone() + timedelta(hours=2)).replace(second=0, microsecond=0)
        self.module.main(
            ["schedule", "--profile", "dentai", "--at", target.strftime("%H:%M")]
        )
        (command,) = self.spawned
        self.assertEqual(command[:3], ["caffeinate", "-i", "-t"])
        # (fire - now) + 3 min slack, within a second of wall-clock drift
        self.assertAlmostEqual(int(command[3]), 2 * 3600 + 180, delta=61)
        label = plistlib.loads(self.plists()[0].read_bytes())["Label"]
        pid_file = self.home / ".t3/userdata/scheduled" / f"{label}.caffeinate.pid"
        self.assertEqual(pid_file.read_text(), "0")
        self.assertIn(str(pid_file), (self.home / ".t3/userdata/scheduled" / f"{label}.sh").read_text())

        self.module.main(["schedule", "--no-caffeinate", "--profile", "x", "--at", target.strftime("%H:%M")])
        self.assertEqual(len(self.spawned), 1)

    def test_cancel_kills_caffeinate(self) -> None:
        target = datetime.now().astimezone() + timedelta(hours=2)
        self.module.main(
            ["schedule", "--profile", "dentai", "--at", target.strftime("%H:%M")]
        )
        label = plistlib.loads(self.plists()[0].read_bytes())["Label"]
        pid_file = self.home / ".t3/userdata/scheduled" / f"{label}.caffeinate.pid"
        pid_file.write_text("4242")
        self.module.caffeinate_pid = lambda name: 4242 if name == label else None
        killed: list[int] = []
        self.module.os.kill = lambda pid, sig: killed.append(pid)
        try:
            self.module.main(["schedule", "--cancel", label])
        finally:
            self.module.os.kill = os.kill
        self.assertEqual(killed, [4242])
        self.assertFalse(pid_file.exists())

    def test_past_time_rolls_to_tomorrow(self) -> None:
        now = datetime(2026, 9, 5, 20, 0).astimezone()
        self.assertEqual(
            self.module.fire_time((10, 11), None, now).date(),
            now.date() + timedelta(days=1),
        )
        self.assertEqual(
            self.module.fire_time((23, 30), None, now),
            now.replace(hour=23, minute=30),
        )
        with self.assertRaises(SystemExit):  # > 7 days out
            self.module.fire_time((9, 0), "2026-09-30", now)

    def test_runner_waits_for_t3_and_notifies(self) -> None:
        target = datetime.now().astimezone() + timedelta(hours=2)
        self.module.main(
            ["schedule", "--profile", "dentai", "--at", target.strftime("%H:%M")]
        )
        body = (self.home / ".t3/userdata/scheduled").glob("*.sh").__next__().read_text()
        self.assertIn(".well-known/t3/environment", body)
        self.assertIn("T3 Code unreachable; retrying via launchd in 60s", body)
        self.assertIn("blocked immediately before resume", body)
        self.assertIn("blocked after resume", body)
        self.assertIn("held for draft", body)
        self.assertIn("--protect-drafts", body)
        self.assertIn("--resumable", body)
        self.assertIn("cutoff", body)
        self.assertIn('--before "$cutoff"', body)
        self.assertLess(body.index("date +%s"), body.index('echo "=== '))
        self.assertIn("--draft-timeout 30", body)
        self.assertIn("--timeout 120", body)
        self.assertIn("display notification", body)

    def test_cancel_removes_plist_and_script(self) -> None:
        target = datetime.now().astimezone() + timedelta(hours=3)
        self.module.main(
            ["schedule", "--profile", "dentai", "--at", target.strftime("%H:%M")]
        )
        (plist,) = self.plists()
        label = plistlib.loads(plist.read_bytes())["Label"]
        cutoff = self.module.cutoff_file(label)
        cutoff.write_text("test")
        self.module.main(["schedule", "--cancel", label])
        self.assertEqual(self.plists(), [])
        self.assertFalse((self.home / ".t3/userdata/scheduled" / f"{label}.sh").exists())
        self.assertFalse(cutoff.exists())
        self.assertEqual(self.calls[-1][0], "bootout")


class DeriveTest(unittest.TestCase):
    """`schedule` without --at: fire time comes from the blocked rows themselves."""

    def setUp(self) -> None:
        self.module = load_cli()
        self.now = datetime.now().astimezone()

    def row(self, kind: str, reset_at: datetime | None):
        return self.module.Limited(
            thread_id="x", profile="claudeAgent_dentai", model="fable-5", title="t",
            project="p", kind=kind, text="", at=self.now, reset_at=reset_at,
        )

    def test_latest_pending_reset_plus_one_minute(self) -> None:
        early = self.now + timedelta(hours=1)
        late = (self.now + timedelta(hours=3)).replace(second=30, microsecond=0)
        fire, note = self.module.derive_fire(
            [self.row("session", early), self.row("session", late), self.row("api", None)],
            self.now,
        )
        # 10:10:30 ceils to 10:11, then +1 -> 10:12
        self.assertEqual(fire, late.replace(second=0, microsecond=0) + timedelta(minutes=2))
        self.assertIn("3 blocked thread(s)", note)

    def test_no_pending_reset_fires_two_minutes_out(self) -> None:
        fire, note = self.module.derive_fire(
            [self.row("api", None), self.row("model", self.now - timedelta(hours=1))],
            self.now,
        )
        self.assertEqual(fire, self.module.ceil_minute(self.now) + timedelta(minutes=2))
        self.assertIn("no pending reset", note)

    def test_monthly_only_is_fatal(self) -> None:
        with self.assertRaises(SystemExit):
            self.module.derive_fire([self.row("monthly", None)], self.now)


class NothingBlockedTest(unittest.TestCase):
    """Empty store + no --at: exit 0, no plist, no script."""

    real_home = os.environ["HOME"]

    def setUp(self) -> None:
        self.module = load_cli()
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        os.environ["HOME"] = str(self.home)
        self.module.launchctl = lambda *a: subprocess.CompletedProcess(a, 0, "", "")
        self.store = self.home / "empty.sqlite"
        connection = sqlite3.connect(self.store)
        connection.executescript("""
            CREATE TABLE projection_projects (
              project_id TEXT PRIMARY KEY, title TEXT, workspace_root TEXT
            );
            CREATE TABLE projection_threads (
              thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, created_at TEXT,
              deleted_at TEXT, archived_at TEXT, model_selection_json TEXT
            );
            CREATE TABLE projection_thread_messages (
              message_id TEXT PRIMARY KEY, thread_id TEXT, role TEXT, text TEXT,
              created_at TEXT
            );
        """)
        connection.commit()
        connection.close()

    def tearDown(self) -> None:
        os.environ["HOME"] = self.real_home
        self.temp.cleanup()

    def test_nothing_blocked_writes_nothing(self) -> None:
        code = self.module.main(
            ["--store", str(self.store), "schedule", "--profile", "dentai"]
        )
        self.assertEqual(code, 0)
        self.assertFalse((self.home / "Library/LaunchAgents").exists())
        self.assertFalse((self.home / ".t3/userdata/scheduled").exists())


if __name__ == "__main__":
    unittest.main()
