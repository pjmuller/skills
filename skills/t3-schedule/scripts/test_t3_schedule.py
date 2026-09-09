"""uv run pytest .agents/skills/t3-schedule/scripts — pure functions only, no launchctl."""
import plistlib
from importlib.machinery import SourceFileLoader
from pathlib import Path

mod = SourceFileLoader("t3_schedule", str(Path(__file__).with_name("t3-schedule"))).load_module()


def test_weekday_plist(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    body = plistlib.loads(mod.plist_body("x", 7, 30, mod.WEEKDAYS, tmp_path / "x.sh"))
    assert body["Label"] == "com.t3-skills.t3-schedule.x"
    assert [d["Weekday"] for d in body["StartCalendarInterval"]] == [1, 2, 3, 4, 5]
    assert body["RunAtLoad"] is False
    daily = plistlib.loads(mod.plist_body("x", 7, 30, None, tmp_path / "x.sh"))
    assert daily["StartCalendarInterval"] == {"Hour": 7, "Minute": 30}


def test_parse_days_and_describe():
    ns = type("A", (), {"weekdays": False, "days": "Mon,thu"})
    assert mod.parse_days(ns) == [1, 4]
    assert mod.describe_days([1, 4]) == "mon,thu"
    assert mod.describe_days(mod.WEEKDAYS) == "weekdays"
    assert mod.describe_days(None) == "daily"


def test_runner_script_is_root_spawn(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    s = {"name": "job", "project": "/repo", "profile": "work", "model": "fable", "thinking": None,
         "title": "⏰ job {date}", "wait_max": 5}
    body = mod.runner_script(s, p)
    assert "unset T3_SOURCE_THREAD_ID CODEX_THREAD_ID" in body
    assert "t3-spawn-thread --project /repo --no-open --model fable" in body and "profile=work" in body
    assert "--thinking" not in body
    assert str(p["prompt"]) in body and str(p["log"]) in body
    assert "--settle-when-done" not in body
    s["settle_when_done"] = True
    assert "--no-open --settle-when-done --model fable" in mod.runner_script(s, p)


def row(pid, window, used, room, reset=1000):
    return {"instance_id": pid, "window": window, "used_percent": used, "room_percent": room,
            "resets_in_seconds": reset}


def test_pick_profile_prefers_room_and_skips_exhausted():
    rows = [row("a", "session", 10, 30), row("a", "weekly", 11, 15), row("a", "Fable only", 16, 10),
            row("b", "session", 22, 33), row("b", "weekly", 45, 44), row("b", "Fable only", 55, 34),
            row("c", "session", 95, 90, reset=5), row("c", "weekly", 1, 99)]
    pid, why = pick = mod.pick_profile(rows)
    assert pid == "b" and "c +" in why and "blocked" in why
    pid, why = mod.pick_profile([row("x", "session", 96, -50, reset=9), row("y", "session", 91, -40, reset=3)])
    assert pid == "y" and why.startswith("all blocked")


def test_runner_guard_and_auto_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    body = mod.runner_script({"name": "job", "project": "/r", "profile": None, "model": None, "thinking": None,
                              "title": "t", "wait_max": 1}, p)
    assert "already spawned today" in body and "t3-schedule pick-profile" in body
    assert str(p["last"]) in body


def test_last_run(tmp_path):
    log = tmp_path / "l.log"
    assert mod.last_run(log) == "never"
    log.write_text("=== 2026-09-07 12:50:55 CEST  lbl\nstuff\n-- job: spawned X\n")
    assert mod.last_run(log) == "2026-09-07 12:50 job: spawned X"


def test_pick_profile_tolerates_null_room():
    # t3-limits reported room_percent=null for a session window on 2026-09-09 and crashed every job
    rows = [row("a", "session", 0, None), row("a", "weekly", 40, 7), row("b", "session", 4, 3.9, reset=None)]
    pid, why = mod.pick_profile(rows)
    assert pid == "a"


def test_due_now_window_and_days():
    from datetime import datetime
    spec = {"at": "05:00", "days": [3]}  # Wednesday
    wed = datetime(2026, 9, 9, 6, 0)
    assert mod.due_now(spec, wed, None)
    assert not mod.due_now(spec, wed, "2026-09-09")            # spawned today
    assert not mod.due_now(spec, datetime(2026, 9, 9, 4, 59), None)   # before slot
    assert not mod.due_now(spec, datetime(2026, 9, 9, 15, 1), None)   # past slot+10h
    assert not mod.due_now(spec, datetime(2026, 9, 10, 6, 0), None)   # Thursday
    assert mod.due_now({"at": "15:00", "days": None}, datetime(2026, 9, 9, 23, 30), None)  # clipped to same day


def test_runner_fails_once_per_day(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    body = mod.runner_script({"name": "job", "project": "/r", "profile": None, "model": None, "thinking": None,
                              "title": "t", "wait_max": 10}, p)
    assert str(p["failed"]) in body and 'fail "job: spawn FAILED' in body
    assert body.count("display notification") == 2  # once in fail(), once on success


def test_pick_profile_recent_penalty_spreads_close_profiles():
    rows = [row("a", "session", 10, 50), row("a", "weekly", 20, 40),
            row("b", "session", 12, 48), row("b", "weekly", 22, 38),
            row("c", "session", 50, 5), row("c", "weekly", 96, 1)]
    assert mod.pick_profile(rows)[0] == "a"
    assert mod.pick_profile(rows, {"a": 1})[0] == "b"        # a just got a job → b, nearly equal room
    assert mod.pick_profile(rows, {"a": 1, "b": 1})[0] == "a"  # never the exhausted c
    assert mod.pick_profile(rows, {"a": 5})[0] == "b"


def test_refresh_retires_legacy_and_preserves_job_data(tmp_path, monkeypatch):
    import argparse
    import json
    import subprocess
    monkeypatch.setenv('HOME', str(tmp_path))
    p = mod.paths('smoke')
    for path in p.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    spec = dict(name='smoke', project='/repo', at='07:30', days=None,
                title='smoke', wait_max=10)
    p['spec'].write_text(json.dumps(spec))
    p['prompt'].write_text('keep prompt')
    p['last'].write_text('2026-09-09')
    legacy = 'com.pjmuller.t3-schedule.smoke'
    old = p['plist'].with_name(legacy + '.plist')
    old.write_bytes(plistlib.dumps({'Label': legacy}))
    active = {legacy}
    def ctl(*args):
        if args[0] == 'list':
            return subprocess.CompletedProcess(args, 0, '\n'.join('- 0 ' + x for x in active), '')
        label = args[1].split('/', 2)[-1]
        if args[0] == 'bootout': active.discard(label)
        return subprocess.CompletedProcess(args, 0 if label in active else 1, '', '')
    monkeypatch.setattr(mod, 'launchctl', ctl)
    monkeypatch.setattr(mod, 'bootstrap', lambda path: active.add(plistlib.loads(path.read_bytes())['Label']))
    mod.cmd_refresh(argparse.Namespace())
    mod.cmd_refresh(argparse.Namespace())
    assert legacy not in active and not old.exists()
    assert active == {mod.label_for('smoke'), mod.label_for(mod.CATCH_UP)}
    assert p['prompt'].read_text() == 'keep prompt'
    assert p['last'].read_text() == '2026-09-09'
    assert json.loads(p['spec'].read_text()) == spec


def test_runner_path_has_pnpm_and_mise():
    # launchd gets no login shell PATH: without pnpm's global bin the runner falls back to `pnpm dlx`
    assert mod.PNPM_BIN in mod.SCHEDULE_PATH
    assert "$HOME/.local/share/mise/shims" in mod.SCHEDULE_PATH
