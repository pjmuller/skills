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
    assert "for candidate in fable; do" in body and "profile=work" in body
    assert 't3-spawn-thread --project /repo --no-open --model "$candidate" "${profile_flag[@]}" --dry-run -- probe' in body
    assert 't3-spawn-thread --project /repo --no-open --model "$chosen" "${profile_flag[@]}" --title' in body
    assert "--thinking" not in body
    assert str(p["prompt"]) in body and str(p["log"]) in body
    assert "--settle-when-done" not in body
    s["settle_when_done"] = True
    assert '--no-open --settle-when-done --model "$chosen"' in mod.runner_script(s, p)


def test_runner_guard_and_auto_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    body = mod.runner_script({"name": "job", "project": "/r", "profile": None, "model": None, "thinking": None,
                              "title": "t", "wait_max": 1}, p)
    assert "already spawned today" in body and "pick-profile" not in body and "--profile" in body
    assert str(p["last"]) in body


def test_last_run(tmp_path):
    log = tmp_path / "l.log"
    assert mod.last_run(log) == "never"
    log.write_text("=== 2026-09-07 12:50:55 CEST  lbl\nstuff\n-- job: spawned X\n")
    assert mod.last_run(log) == "2026-09-07 12:50 job: spawned X"


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
    monkeypatch.setattr(mod, 'running', lambda name: True)
    mod.cmd_refresh(argparse.Namespace())
    assert mod.label_for('smoke') not in active  # a running job is left alone
    monkeypatch.setattr(mod, 'running', lambda name: False)
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


def test_once_plist_and_runner_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    body = plistlib.loads(mod.plist_body("x", 8, 0, None, tmp_path / "x.sh", "2026-09-26"))
    assert body["StartCalendarInterval"] == {"Month": 9, "Day": 26, "Hour": 8, "Minute": 0}
    p = mod.paths("job")
    s = {"name": "job", "project": "/r", "profile": None, "model": None, "thinking": None,
         "title": "t", "wait_max": 1, "once": "2026-09-26"}
    once = mod.runner_script(s, p)
    assert "already fired once" in once and '!= "2026-09-26" && "$T3_SCHEDULE_FORCE" != 1' in once
    assert "already spawned today" not in once
    s["once"] = None
    assert "already fired once" not in mod.runner_script(s, p) and "T3_SCHEDULE_FORCE" not in mod.runner_script(s, p)
    assert mod.describe_when({"once": "2026-09-26", "days": None}) == "once 2026-09-26 (sat)"
    assert mod.describe_when({"days": mod.WEEKDAYS}) == "weekdays"


def test_once_due_and_retire():
    from datetime import datetime
    spec = {"at": "08:00", "days": None, "once": "2026-09-26"}
    sat = datetime(2026, 9, 26, 9, 0)
    assert mod.due_now(spec, sat, None)
    assert not mod.due_now(spec, datetime(2026, 9, 27, 9, 0), None)     # wrong date
    assert not mod.due_now(spec, sat, "2026-09-26")                       # already fired
    assert not mod.due_now(spec, datetime(2027, 9, 26, 9, 0), "2026-09-26")  # annual re-fire
    assert mod.retire_status(spec, sat, None) is None                     # still in window
    assert mod.retire_status(spec, sat, "2026-09-26") == "fired 2026-09-26"
    assert mod.retire_status(spec, datetime(2026, 9, 26, 23, 1), None) == "expired (never fired)"
    assert mod.retire_status({"at": "08:00", "days": None}, sat, None) is None  # recurring: never
    assert not mod.due_now({**spec, "retired": "fired 2026-09-26"}, sat, None)


def test_parse_once_rejects_past():
    import pytest
    from datetime import datetime
    now = datetime(2026, 9, 24, 10, 0)
    assert mod.parse_once("2026-09-24", 10, 1, now) == "2026-09-24"
    for day, h in (("2026-09-24", 10), ("2026-09-23", 12), ("26/09/2026", 8)):
        with pytest.raises(SystemExit):
            mod.parse_once(day, h, 0, now)


def test_once_catch_up_until_23h():
    from datetime import datetime
    spec = {"name": "o", "at": "08:00", "days": None, "once": "2026-09-26"}
    assert mod.due_now(spec, datetime(2026, 9, 26, 22, 45), None)  # recurring grace would end 18:00
    assert not mod.due_now(spec, datetime(2026, 9, 26, 23, 5), None)
    assert mod.retire_status(spec, datetime(2026, 9, 26, 22, 0), None) is None
    assert mod.retire_status(spec, datetime(2026, 9, 26, 23, 5), None) == "expired (never fired)"


def test_runner_model_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    s = {"name": "job", "project": "/r", "profile": None, "model": "haiku,luna", "thinking": "high",
         "title": "t", "wait_max": 1}
    body = mod.runner_script(s, p)
    assert "for candidate in haiku luna; do" in body
    assert 'fail "job: no model candidate available (haiku,luna)"' in body
    assert body.index("--dry-run -- probe") < body.index('--model "$chosen"')
    assert '--thinking high --model "$candidate"' in body
    s["model"] = None
    assert f"for candidate in {mod.DEFAULT_MODELS.replace(',', ' ')}; do" in mod.runner_script(s, p)
    assert mod.describe_models(s) == "opus,sol (default)" and mod.describe_models({"model": "fable"}) == "fable"


def test_valid_models():
    import pytest
    assert mod.valid_models("opus,sol") == "opus,sol" and mod.valid_models(None) is None
    assert mod.valid_models("claude-opus-4.5_x") == "claude-opus-4.5_x"
    for bad in ("opus,,sol", "bad model", "opus,", ""):
        with pytest.raises(SystemExit):
            mod.valid_models(bad)


def test_hide_and_no_notify(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    base = {"name": "job", "project": "/r", "profile": None, "model": "haiku", "thinking": None, "title": "t", "wait_max": 1}
    body = mod.runner_script({**base, "hide": True, "notify": False}, p)
    assert "--no-open --hide" in body and "--settle-when-done" not in body
    assert body.count("display notification") == 2 and '\n  : osascript' in body  # success notification disabled, fail() kept
    default = mod.runner_script(base, p)
    assert "--hide" not in default and ": osascript" not in default
