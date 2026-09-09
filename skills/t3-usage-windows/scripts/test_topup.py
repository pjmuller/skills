"""Top-up decisions and launchd project fallback."""
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path
from zoneinfo import ZoneInfo

mod = SourceFileLoader(
    "t3_hello_world_topup", str(Path(__file__).with_name("topup.py"))
).load_module()

TZ = ZoneInfo("Europe/Brussels")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """2026-09-07 is a Monday."""
    return datetime(2026, 9, 6 + day, hour, minute, tzinfo=TZ)


def test_gate_hours_and_weekend():
    assert not mod.within_hours(at(1, 4, 59))
    assert mod.within_hours(at(1, 5, 0))
    assert mod.within_hours(at(1, 20, 59))
    assert not mod.within_hours(at(1, 21, 0))
    assert mod.within_hours(at(5, 12))  # Friday
    assert not mod.within_hours(at(6, 12))  # Saturday
    assert not mod.within_hours(at(0, 12))  # Sunday


def session(instance, left):
    return {"instance_id": instance, "window": "session", "resets_in_seconds": left}


def test_classify():
    rows = [
        session("a", 3600),
        session("b", -30),  # inside the grace window: not stale yet
        session("c", -61),
        session("d", None),  # no reset time
        {"instance_id": "e", "window": "weekly", "resets_in_seconds": 9},  # no session row: reported, never topped up
        {"instance_id": "f", "window": None, "error": "token expired"},
    ]
    assert mod.classify(rows) == (["c", "d"], ["f"], ["e"])


def test_classify_force_skips_only_unknowns():
    rows = [session("a", 3600), {"instance_id": "f", "window": None, "error": "boom"}]
    assert mod.classify(rows, force=True) == (["a"], ["f"], [])


def test_wait_seconds():
    assert mod.wait_seconds([session("a", 900)], 600) is None  # next reset after this tick
    assert mod.wait_seconds([session("a", 300), session("b", 900)], 600) == 360
    assert mod.wait_seconds([session("a", 700)], 1000) == 760
    assert mod.wait_seconds([session("a", 600)], 600) == 660  # boundary: max sleep = interval + grace
    assert mod.wait_seconds([session("a", -300)], 600) is None  # already stale
    assert mod.wait_seconds([], 600) is None


def test_hello_from_launchd_root_global_install(tmp_path):
    import json
    import os
    import shutil
    import subprocess
    scripts = tmp_path / 'installed'
    scripts.mkdir()
    hello = scripts / 'start.sh'
    shutil.copyfile(Path(__file__).with_name('start.sh'), hello)
    settings = tmp_path / '.t3/userdata/settings.json'
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({'providers': {'claudeAgent': {'enabled': False}}}))
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    spawn = bin_dir / 't3-spawn-thread'
    spawn.write_text('#!/bin/sh\nprintf "project args: %s\\n" "$*"\necho "Provider: codex · Model: gpt-5.6-luna · Thinking: low"\n')
    spawn.chmod(0o755)
    settle = bin_dir / 't3-settle-thread'
    settle.write_text('#!/bin/sh\nexit 0\n')
    settle.chmod(0o755)
    env = dict(os.environ, HOME=str(tmp_path), T3CODE_HOME=str(tmp_path / '.t3'),
               PATH=str(bin_dir) + ':' + os.environ['PATH'])
    result = subprocess.run(['bash', str(hello), '--dry-run', '--only', 'codex'],
                            cwd='/', env=env, text=True, check=False, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert '--project ' + str(tmp_path) in result.stdout
