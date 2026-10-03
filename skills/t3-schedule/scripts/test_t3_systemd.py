"""Systemd backend tests: no real user jobs or service-manager writes."""
import argparse
import json
import subprocess
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

mod = SourceFileLoader("t3_schedule_systemd", str(Path(__file__).with_name("t3-schedule"))).load_module()


@pytest.fixture(autouse=True)
def linux_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "systemd", lambda: True)
    monkeypatch.setenv("HOME", str(tmp_path))


def spec(**kwargs):
    return dict(name="test", at="08:51", days=None, project="/repo", title="test", wait_max=0, **kwargs)


def test_calendar_dates_and_weekdays():
    assert "OnCalendar=*-*-* 08:51:00" in mod.timer_body(spec()).decode()
    weekdays = spec()
    weekdays["days"] = [1, 2, 3, 4, 5]
    assert "OnCalendar=Mon,Tue,Wed,Thu,Fri *-*-* 08:51:00" in mod.timer_body(weekdays).decode()
    once = mod.timer_body(spec(once="2026-10-03")).decode()
    assert "OnCalendar=2026-10-03 08:51:00" in once
    assert "Persistent=true" in once and "AccuracySec=1s" in once


def test_service_and_stale_detection(tmp_path):
    job = spec()
    mod.write_artefacts(job)
    p = mod.paths("test")
    assert p["plist"].suffix == ".timer"
    assert "ExecStart=/bin/zsh" in p["service"].read_text()
    assert "TimeoutStartSec=infinity" in p["service"].read_text()
    assert "stale" not in (mod.job_flag(job) or "")
    p["service"].write_text("old service")
    assert "stale" in mod.job_flag(job)
    assert mod.unit_arg('/a "quote" $foo%bar') == '"/a \\"quote\\" $$foo%%bar"'


def test_lifecycle_and_oneshot_activating(monkeypatch):
    calls = []
    def ctl(*args):
        calls.append(args)
        out = "activating\n" if "--property=ActiveState" in args else "loaded\n"
        return subprocess.CompletedProcess(args, 0, out, "")
    monkeypatch.setattr(mod, "systemctl", ctl)
    mod.write_artefacts(spec())
    mod.bootstrap(mod.paths("test")["plist"])
    assert calls[:2] == [("daemon-reload",), ("enable", "--now", mod.paths("test")["plist"].name)]
    assert mod.loaded("test") and mod.running("test")
    mod.bootout("test")
    assert ("disable", "--now", mod.paths("test")["plist"].name) in calls
    assert ("stop", mod.paths("test")["service"].name) in calls
    mod.kickstart("test")
    assert calls[-1] == ("start", "--no-block", mod.paths("test")["service"].name)


def test_missing_retired_units_can_be_removed(monkeypatch):
    monkeypatch.setattr(mod, "systemctl", lambda *a: subprocess.CompletedProcess(a, 0, "not-found\n", ""))
    p = mod.paths("test")
    p["spec"].parent.mkdir(parents=True)
    p["spec"].write_text(json.dumps(spec(retired="fired 2026-10-03")))
    assert mod.cmd_remove(argparse.Namespace(name="test")) == 0
    assert not p["spec"].exists()


def test_unavailable_manager_is_actionable(monkeypatch):
    monkeypatch.setattr(mod, "systemctl", lambda *a: subprocess.CompletedProcess(a, 1, "", "Failed to connect to bus"))
    with pytest.raises(SystemExit, match="Failed to connect to bus"):
        mod.scheduler_check()


def test_catch_up_units_and_runner_guard(monkeypatch):
    monkeypatch.setattr(mod, "bootstrap", lambda p: None)
    mod.arm_catch_up()
    p = mod.paths(mod.CATCH_UP)
    assert "OnStartupSec=1min" in p["plist"].read_text()
    assert f"OnUnitActiveSec={mod.CATCH_UP_INTERVAL}s" in p["plist"].read_text()
    assert "exec t3-schedule catch-up" in p["sh"].read_text()
    body = mod.runner_script(spec(), mod.paths("test"))
    assert "flock -n 9" in body
    assert "T3_SCHEDULE_AUTOMATIC" in body and "t3-schedule due-check test" in body
    # A persistent timer waking on a different day/before today's slot must not fire stale work.
    job = spec()
    assert not mod.due_now(job, datetime(2026, 10, 4, 8, 0), None)
    assert mod.due_now(job, datetime(2026, 10, 4, 8, 51), None)
    assert not mod.due_now(job, datetime(2026, 10, 4, 8, 51), "2026-10-04")
    assert not mod.due_now(spec(once="2026-10-03"), datetime(2026, 10, 4, 8, 51), None)


def test_rearm_does_not_interrupt_active_runner(monkeypatch):
    monkeypatch.setattr(mod, "running", lambda n: True)
    monkeypatch.setattr(mod, "bootout", lambda n: pytest.fail("must not unload active runner"))
    assert not mod.rearm(spec())


def test_failed_enable_is_not_reported_as_armed(monkeypatch):
    def ctl(*args):
        return subprocess.CompletedProcess(args, 1 if args[0] == "enable" else 0, "", "denied")
    monkeypatch.setattr(mod, "systemctl", ctl)
    with pytest.raises(SystemExit, match="denied"):
        mod.bootstrap(mod.paths("test")["plist"])


@pytest.mark.parametrize("at", ["23:00", "23:30", "23:59"])
def test_late_one_shot_has_real_firing_window(at):
    job = spec(once="2026-10-03")
    job["at"] = at
    fired = datetime.fromisoformat(f"2026-10-03T{at}:01.123456")
    assert mod.due_now(job, fired, None)
    assert mod.retire_status(job, fired, None) is None
