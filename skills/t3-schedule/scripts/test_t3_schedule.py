"""uv run pytest .agents/skills/t3-schedule/scripts — pure functions only, no launchctl."""
import json
import plistlib
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

loader = SourceFileLoader("t3_schedule", str(Path(__file__).with_name("t3-schedule")))
spec = spec_from_loader(loader.name, loader)
mod = module_from_spec(spec)
sys.modules[loader.name] = mod
loader.exec_module(mod)


@pytest.fixture(autouse=True)
def mac_backend(monkeypatch):
    # The historical suite exercises launchd without touching the host service manager.
    monkeypatch.setattr(mod, "systemd", lambda: False)
    monkeypatch.setattr(mod, "scheduler_check", lambda: None)


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


def test_runner_fires_through_relay_step(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    body = mod.runner_script({"name": "job", "project": "/r", "profile": None, "model": None, "thinking": None,
                              "title": "t", "wait_max": 10}, p)
    assert "out=$(t3-schedule fire job 2>&1)" in body and "t3-spawn-thread" not in body and "unset " not in body
    assert "already fired today" in body and str(p["last"]) in body and str(p["log"]) in body
    assert str(p["failed"]) in body and 'fail "job: fire FAILED' in body
    assert body.count("display notification") == 2  # once in fail(), once on success


def test_pre_command_runs_while_t3_is_down(tmp_path, monkeypatch):
    """The skills updater rides on --pre-command so it lands even when T3 / t3-relay is broken."""
    import os, subprocess
    monkeypatch.setenv("HOME", str(tmp_path))
    bin_ = tmp_path / ".local/bin"
    bin_.mkdir(parents=True)
    for tool, body in {"curl": "exit 7", "osascript": 'echo "notified: $*" >> "$HOME/notes"',
                       "t3-schedule": 'echo "fire called" >> "$HOME/notes"'}.items():
        (bin_ / tool).write_text(f"#!/bin/sh\n{body}\n")
        (bin_ / tool).chmod(0o755)
    p = mod.paths("job")
    body = mod.runner_script({"name": "job", "project": "/r", "title": "t", "wait_max": 0,
                              "pre_command": 'echo updater-ran $(echo x >> "$HOME/effects"); exit 4'}, p)
    assert body.index("pre-command:") < body.index("until t3_up")
    p["sh"].parent.mkdir(parents=True)
    p["sh"].write_text(body)
    rc = subprocess.run(["zsh", str(p["sh"])], env={**os.environ, "HOME": str(tmp_path)}).returncode
    log = p["log"].read_text()
    assert rc == 1 and "   updater-ran" in log and "pre-command FAILED (exit 4)" in log and "NOT fired" in log
    assert log.index("updater-ran") < log.index("NOT fired")
    notes = (tmp_path / "notes").read_text()
    assert notes.count("notified:") == 1 and "fire called" not in notes   # one alert per day, no fire without T3
    assert (tmp_path / "effects").read_text() == "x\n"                   # logging the command never runs it


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


def test_refresh_preserves_job_data(tmp_path, monkeypatch):
    import argparse
    import json
    monkeypatch.setenv('HOME', str(tmp_path))
    p = mod.paths('smoke')
    for path in p.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    spec = dict(name='smoke', project='/repo', at='07:30', days=None, title='smoke', wait_max=10)
    p['spec'].write_text(json.dumps(spec))
    p['prompt'].write_text('keep prompt')
    p['last'].write_text('2026-09-09')
    active = set()
    monkeypatch.setattr(mod, 'loaded', lambda name: mod.label_for(name) in active)
    monkeypatch.setattr(mod, 'bootout', lambda name: active.discard(mod.label_for(name)))
    monkeypatch.setattr(mod, 'bootstrap', lambda path: active.add(plistlib.loads(path.read_bytes())['Label']))
    monkeypatch.setattr(mod, 'running', lambda name: True)
    mod.cmd_refresh(argparse.Namespace())
    assert mod.label_for('smoke') not in active  # a running job is left alone
    monkeypatch.setattr(mod, 'running', lambda name: False)
    mod.cmd_refresh(argparse.Namespace())
    assert active == {mod.label_for('smoke'), mod.label_for(mod.CATCH_UP)}
    assert p['prompt'].read_text() == 'keep prompt'
    assert p['last'].read_text() == '2026-09-09'
    assert json.loads(p['spec'].read_text()) == spec
    assert "t3-schedule fire smoke" in p['sh'].read_text()


def test_runner_path_has_mise():
    assert "$HOME/.local/share/mise/shims" in mod.SCHEDULE_PATH and "$HOME/.local/bin" in mod.SCHEDULE_PATH


def test_once_plist_and_runner_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    body = plistlib.loads(mod.plist_body("x", 8, 0, None, tmp_path / "x.sh", "2026-09-26"))
    assert body["StartCalendarInterval"] == {"Month": 9, "Day": 26, "Hour": 8, "Minute": 0}
    p = mod.paths("job")
    s = {"name": "job", "project": "/r", "profile": None, "model": None, "thinking": None,
         "title": "t", "wait_max": 1, "once": "2026-09-26"}
    once = mod.runner_script(s, p)
    assert "already fired once" in once and '!= "2026-09-26" && "$T3_SCHEDULE_FORCE" != 1' in once
    assert "already fired today" not in once
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


def test_valid_models():
    import pytest
    assert mod.valid_models("opus,sol") == "opus,sol" and mod.valid_models(None) is None
    assert mod.valid_models("claude-opus-4.5_x") == "claude-opus-4.5_x"
    for bad in ("opus,,sol", "bad model", "opus,", ""):
        with pytest.raises(SystemExit):
            mod.valid_models(bad)


def test_no_notify(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    base = {"name": "job", "project": "/r", "profile": None, "model": "haiku", "thinking": None, "title": "t", "wait_max": 1}
    body = mod.runner_script({**base, "hide": True, "notify": False}, p)  # legacy "hide" key is ignored
    assert body.count("display notification") == 2 and '\n    : osascript' in body  # success notification disabled, fail() kept
    default = mod.runner_script(base, p)
    assert ": osascript" not in default


# --- fire: the runner's relay step ------------------------------------------------
TID = "11111111-2222-3333-4444-555555555555"
PROFILES = [{"instance_id": "claudeAgent_dentai", "profile": "dentai", "ecosystem": "Claude"},
            {"instance_id": "codex_dentai", "profile": "dentai", "ecosystem": "OpenAI"}]


def fire(tmp_path, monkeypatch, spec, relay_rc=0, no_capacity=(), status_rc=None):
    """Run cmd_fire on a machine-local job with faked helpers; returns (rc, argv list)."""
    import argparse
    import json
    import subprocess
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    p["spec"].parent.mkdir(parents=True, exist_ok=True)
    p["spec"].write_text(json.dumps({"name": "job", "project": "/repo", "title": "⏰ job {date}", **spec}))
    p["prompt"].write_text("Run the report.\n")
    p["last"].unlink(missing_ok=True)  # each call is a fresh slot unless a test says otherwise
    calls = []
    def run(argv, **kw):
        calls.append(argv)
        ok = lambda out: subprocess.CompletedProcess(argv, 0, out, "")
        if argv[0] == "t3-list-profiles":
            return ok(json.dumps(PROFILES))
        if argv[:2] == ["t3-pick-instance", "--resolve"]:
            return ok({"fable": "claude-fable-5", "sol": "gpt-6-sol"}.get(argv[2], argv[2]))
        if argv[0] == "t3-pick-instance":
            if argv[1] in no_capacity:
                return subprocess.CompletedProcess(argv, 2, "", "exhausted")
            inst = argv[2].split(",")[0] if len(argv) > 2 else "claudeAgent"
            return ok(f"{inst} {argv[1]}-id high\n")
        if argv[:2] == ["t3-relay", "status"]:
            out = {0: "ok mcp:t\n", 1: "failed host turn completed\n", 3: "pending\n"}.get(status_rc, "")
            return subprocess.CompletedProcess(argv, status_rc, out, "Traceback: database is locked")
        verdict = {1: "failed host turn completed\n", 3: "pending\n"}.get(relay_rc, "")
        return subprocess.CompletedProcess(argv, relay_rc, "accepted: relay abc123 via h (d)\n" + verdict, "")
    monkeypatch.setattr(mod.subprocess, "run", run)
    return mod.cmd_fire(argparse.Namespace(name="job")), calls


def test_legacy_skills_refresh_spec_keeps_running(tmp_path):
    repo = tmp_path / "repo" / ".agents" / "schedules"
    repo.mkdir(parents=True)
    (repo / "skills-refresh.json").write_text(json.dumps({"at": "05:15", "days": None, "model": "haiku,luna"}))
    (repo / "skills-refresh.prompt.md").write_text("go\n")
    spec = mod.merge_pointer({"name": "skills-refresh", "source": str(repo / "skills-refresh.json")})
    assert not spec.get("missing") and spec["allow_small_model"] is True


def test_fire_passes_allow_small_model(tmp_path, monkeypatch):
    rc, calls = fire(tmp_path, monkeypatch, {"model": "haiku", "allow_small_model": True})
    assert rc == 0 and "--allow-small-model" in calls[-1]


def test_fire_launch_maps_job_fields(tmp_path, monkeypatch, capsys):
    rc, calls = fire(tmp_path, monkeypatch, {"model": "opus,fable", "profile": "dentai", "thinking": "low",
                                             "settle_when_done": True}, no_capacity=("opus",))
    relay = calls[-1]
    today = mod.date.today().isoformat()
    assert rc == 0 and relay[:7] == ["t3-relay", "launch", "--project", "/repo", "--title", f"⏰ job {today}",
                                     "--settle-when-done"]
    assert relay[7:13] == ["--model", "fable-id", "--instance", "claudeAgent_dentai", "--effort", "low"]
    assert ["t3-pick-instance", "fable", "claudeAgent_dentai"] in calls  # label narrowed to the Claude account
    assert relay[-3:] == ["--wait", "120", "Run the report."] or relay[-4:] == ["--wait", "120", "--", "Run the report."]
    assert relay[-1] == "Run the report."  # the footer is appended by t3-relay
    assert capsys.readouterr().out.strip().endswith(f"launched ⏰ job {today}")


def test_fire_defaults_and_failures(tmp_path, monkeypatch, capsys):
    rc, calls = fire(tmp_path, monkeypatch, {})
    assert rc == 0 and calls == [["t3-relay", "launch", "--project", "/repo", "--title", calls[0][5],
                                  "--wait", "120", "--", "Run the report."]]
    rc, calls = fire(tmp_path, monkeypatch, {"model": "opus"}, no_capacity=("opus",))
    assert rc == 1 and calls[-1][0] == "t3-pick-instance"  # nothing routable: no relay call, catch-up retries
    rc, _ = fire(tmp_path, monkeypatch, {}, relay_rc=1)
    assert rc == 1 and "t3-relay FAILED (exit 1)" in capsys.readouterr().out


def test_fire_continuation_sends(tmp_path, monkeypatch, capsys):
    rc, calls = fire(tmp_path, monkeypatch, {"resume_thread": TID, "project": None})
    assert rc == 0 and calls[0][:7] == ["t3-relay", "send", "--thread", TID, "--wait", "120", "--"]
    assert calls[0][-1].startswith("Scheduled follow-up (") and calls[0][-1].endswith("thread:\n\nRun the report.")
    assert f"sent follow-up to thread {TID}" in capsys.readouterr().out


def test_add_continuation_validation(tmp_path, monkeypatch, capsys):
    import argparse
    import pytest
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(mod, "thread_exists", lambda tid: tid == TID)  # V2 store lookup
    add = lambda **kw: mod.cmd_add(argparse.Namespace(**{
        "name": "fu", "at": "07:30", "once": None, "weekdays": False, "days": None, "project": None,
        "profile": None, "model": None, "thinking": None, "allow_small_model": False, "settle_when_done": False,
        "no_notify": False, "title": None, "prompt_file": None, "prompt": ["go"], "wait_max": 1,
        "force": False, "dry_run": True, "resume_thread": TID, "many_machines": False, "takeover": False,
        "pre_command": None, **kw}))
    assert add() == 0 and "t3-schedule fire fu" in capsys.readouterr().out  # no project needed
    for kw, msg in (({"resume_thread": "self"}, "currentThreadId"), ({"settle_when_done": True}, "settle-when-done"),
                    ({"model": "opus"}, "drop"), ({"resume_thread": None}, "--project is required"),
                    ({"resume_thread": None, "project": str(tmp_path), "profile": "dentai"}, "--profile needs --model"),
                    ({"resume_thread": None, "project": str(tmp_path), "model": "haiku,luna"}, "--allow-small-model")):
        with pytest.raises(SystemExit, match=msg):
            add(**kw)


# --- versioned job definitions (<project>/.agents/schedules) -------------------------
def no_launchd(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for fn, value in (("loaded", False), ("running", False)):
        monkeypatch.setattr(mod, fn, lambda name, v=value: v)
    for fn in ("bootout", "bootstrap"):
        monkeypatch.setattr(mod, fn, lambda *a: None)
    monkeypatch.setattr(mod, "arm_catch_up", lambda: None)
    import subprocess
    monkeypatch.setattr(mod, "launchctl", lambda *a: subprocess.CompletedProcess(a, 1, "", ""))


def add_args(**kw):
    import argparse
    return argparse.Namespace(**{
        "name": "nightly", "at": "07:30", "once": None, "weekdays": True, "days": None, "project": None,
        "profile": "work", "model": "fable", "thinking": None, "allow_small_model": False, "settle_when_done": True,
        "no_notify": False, "title": None, "prompt_file": None, "prompt": ["Run the report."], "wait_max": 10,
        "force": False, "dry_run": False, "resume_thread": None, "many_machines": False, "takeover": False, "pre_command": None, **kw})


def test_add_recurring_writes_repo_spec_once_stays_local(tmp_path, monkeypatch):
    import json
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    assert mod.cmd_add(add_args(project=str(repo))) == 0
    src, prompt = mod.repo_files(repo, "nightly")
    stored = json.loads(src.read_text())
    me = mod.machine_identity()
    assert stored.pop("adopted_by") == [{"machine": me["label"], "user": None, "since": mod.date.today().isoformat(), "id": me["id"]}]
    assert stored == {"at": "07:30", "days": mod.WEEKDAYS, "title": "⏰ nightly {date}", "model": "fable", "thinking": None, "allow_small_model": False,
                      "settle_when_done": True, "notify": True, "wait_max": 10, "machines": "one",
                      "paused": False, "pause_until": None}
    assert prompt.read_text() == "Run the report.\n"
    p = mod.paths("nightly")
    assert json.loads(p["spec"].read_text()) == {"name": "nightly", "source": str(src), "profile": "work"}
    assert not p["prompt"].exists() and "t3-schedule fire nightly" in p["sh"].read_text()
    spec = mod.load_spec(p["spec"])
    assert spec["project"] == str(repo) and spec["profile"] == "work" and mod.artefacts(spec)[0] == p["sh"].read_text()

    assert mod.cmd_add(add_args(name="oneoff", project=str(repo), weekdays=False, once="2099-01-01")) == 0
    assert not mod.repo_files(repo, "oneoff")[0].exists() and mod.paths("oneoff")["prompt"].exists()
    assert json.loads(mod.paths("oneoff")["spec"].read_text())["project"] == str(repo)


def write_repo_job(repo, name="nightly", at="06:00"):
    import json
    src, prompt = mod.repo_files(repo, name)
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(json.dumps({"at": at, "days": None, "title": "t", "model": "fable", "wait_max": 10}))
    prompt.write_text("go\n")
    return src


def test_add_force_repairs_bad_repo_spec(tmp_path, monkeypatch):
    import json
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    src, _ = mod.repo_files(repo, "nightly")
    src.parent.mkdir(parents=True)
    for bad in ("{broken", "[]"):
        src.write_text(bad)
        assert mod.cmd_add(add_args(project=str(repo), force=True)) == 0
        repaired = json.loads(src.read_text())
        assert repaired["paused"] is False and repaired["pause_until"] is None


def test_pause_resume_keeps_registration_and_skips_catch_up(tmp_path, monkeypatch, capsys):
    import argparse
    import json
    from datetime import datetime
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    src = write_repo_job(repo)
    mod.cmd_adopt(argparse.Namespace(path=str(src), profile=None, force=False, takeover=False))
    before = json.loads(src.read_text())["adopted_by"]
    until = "2099-01-01"
    assert mod.main(["pause", "nightly", "--until", until]) == 0
    stored = json.loads(src.read_text())
    assert stored["adopted_by"] == before and stored["paused"] is True and stored["pause_until"] == until
    spec = mod.load_spec(mod.paths("nightly")["spec"])
    assert mod.pause_label(spec, datetime(2026, 9, 29).date()) == f"paused until {until}"
    assert mod.pause_label(spec, datetime(2099, 1, 1).date()) is None
    assert not mod.due_now(spec, datetime(2026, 9, 29, 7), None)
    assert mod.due_now(spec, datetime(2099, 1, 1, 7), None)
    assert mod.cmd_pause_check(argparse.Namespace(name="nightly")) == mod.PAUSED_SKIP_EXIT
    class FixedDateTime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 9, 29, 7)
    monkeypatch.setattr(mod, "datetime", FixedDateTime)
    mod.cmd_catch_up(argparse.Namespace(dry_run=True))
    assert "nothing due" in capsys.readouterr().out
    runner = mod.paths("nightly")["sh"].read_text()
    assert runner.count("pause_check") >= 3 and runner.index("pause_check") < runner.index("until t3_up")
    mod.cmd_list(argparse.Namespace(json=False, markdown=False))
    assert f"paused until {until}" in capsys.readouterr().out
    assert mod.main(["resume", "nightly"]) == 0
    stored = json.loads(src.read_text())
    assert stored["adopted_by"] == before and stored["paused"] is False and stored["pause_until"] is None
    assert mod.cmd_pause_check(argparse.Namespace(name="nightly")) == 0


def test_pause_validation(tmp_path, monkeypatch):
    import argparse
    import json
    import pytest
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    src = write_repo_job(repo)
    mod.cmd_adopt(argparse.Namespace(path=str(src), profile=None, force=False, takeover=False))
    for bad in ("tomorrow", "2026-02-30", "2000-01-01"):
        with pytest.raises(SystemExit):
            mod.main(["pause", "nightly", "--until", bad])
    for bad in ({"paused": "yes"}, {"paused": True, "pause_until": "2026-02-30"},
                {"paused": False, "pause_until": "2099-01-01"}):
        assert mod.repo_spec_problem({**json.loads(src.read_text()), **bad}, mod.repo_files(repo, "nightly")[1])


def test_adopt_is_explicit_and_refuses_foreign_name(tmp_path, monkeypatch):
    import json
    import pytest
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    src = write_repo_job(repo)
    adopt = lambda path, **kw: mod.cmd_adopt(type("A", (), {"path": str(path), "profile": None, "force": False, "takeover": False, **kw}))
    assert mod.specs() == []  # a clone arms nothing
    adopt(repo, profile="work")
    p = mod.paths("nightly")
    assert json.loads(p["spec"].read_text()) == {"name": "nightly", "source": str(src), "profile": "work"}
    assert "t3-schedule fire nightly" in p["sh"].read_text() and p["plist"].exists()
    adopt(src)  # re-adopt keeps the machine-local profile
    assert json.loads(p["spec"].read_text())["profile"] == "work"
    other = tmp_path / "other"
    write_repo_job(other)
    with pytest.raises(SystemExit, match="already exists"):
        adopt(other)
    adopt(other, force=True)
    assert mod.load_spec(p["spec"])["project"] == str(other)
    (other / mod.SCHEDULES_DIR / "nightly.prompt.md").unlink()
    with pytest.raises(SystemExit, match="prompt"):
        adopt(other)
    with pytest.raises(SystemExit, match="no job specs"):
        adopt(tmp_path / "home")


def test_list_flags_git_state(tmp_path, monkeypatch):
    import subprocess
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    src = write_repo_job(repo)
    git = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                    check=True, capture_output=True)
    mod.cmd_adopt(type("A", (), {"path": str(repo), "profile": None, "force": False, "takeover": False}))
    p = mod.paths("nightly")
    assert mod.job_flag(mod.load_spec(p["spec"])) == "not in git"
    git("init", "-q")
    assert mod.job_flag(mod.load_spec(p["spec"])).startswith("untracked")
    git("add", ".")
    git("commit", "-qm", "job")
    assert mod.job_flag(mod.load_spec(p["spec"])) is None
    (repo / mod.SCHEDULES_DIR / "nightly.prompt.md").write_text("changed\n")
    assert mod.job_flag(mod.load_spec(p["spec"])).startswith("uncommitted")
    git("commit", "-qam", "prompt")
    src.write_text(src.read_text().replace("06:00", "06:30"))  # e.g. a pulled time change
    git("commit", "-qam", "time")
    assert mod.job_flag(mod.load_spec(p["spec"])) == "stale runner (t3-schedule refresh)"
    src.unlink()
    spec = mod.load_spec(p["spec"])
    assert spec["missing"] and mod.job_flag(spec).startswith("MISSING") and not mod.due_now(spec, None, None)


def test_broken_repo_spec_is_isolated(tmp_path, monkeypatch):
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    src = write_repo_job(repo)
    mod.cmd_adopt(type("A", (), {"path": str(repo), "profile": None, "force": False, "takeover": False}))
    src.write_text("<<<<<<< HEAD\n{}")  # conflict markers after a pull
    [spec] = mod.specs()
    assert spec["missing"].startswith("invalid") and not mod.due_now(spec, None, None)
    mod.cmd_refresh(type("A", (), {})())  # skips it instead of crashing


def test_malformed_pulled_definitions_are_isolated(tmp_path, monkeypatch):
    """Review P1: wrong field types must mark only that job invalid, never crash specs()/catch-up."""
    import json
    from datetime import datetime
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    good = write_repo_job(repo, "good", at="05:00")
    src = write_repo_job(repo, "bad", at="06:00")
    mod.cmd_adopt(type("A", (), {"path": str(repo), "profile": None, "force": False, "takeover": False}))
    base = json.loads(src.read_text())
    for field, value in (("at", 730), ("days", "mon,fri"), ("days", [7]), ("days", []), ("model", ["fable"]),
                         ("model", "bad model"), ("notify", "yes"), ("wait_max", "10"), ("wait_max", True)):
        src.write_text(json.dumps({**base, field: value}))
        by_name = {s["name"]: s for s in mod.specs()}
        assert by_name["bad"]["missing"].startswith("invalid"), (field, value)
        assert not mod.due_now(by_name["bad"], datetime(2026, 9, 9, 7, 0), None)
        assert mod.due_now(by_name["good"], datetime(2026, 9, 9, 7, 0), None)
    src.write_text("[1, 2]")
    assert mod.load_spec(mod.paths("bad")["spec"])["missing"].startswith("invalid")
    assert good.exists()


def test_missing_prompt_marks_job_and_list_renders(tmp_path, monkeypatch, capsys):
    """Review P1: a deleted repo prompt must not stay due (starving later jobs) nor crash list --markdown."""
    from datetime import datetime
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    write_repo_job(repo, "early", at="05:00")
    write_repo_job(repo, "late", at="06:00")
    mod.cmd_adopt(type("A", (), {"path": str(repo), "profile": None, "force": False, "takeover": False}))
    (repo / mod.SCHEDULES_DIR / "early.prompt.md").unlink()
    early = mod.load_spec(mod.paths("early")["spec"])
    assert early["missing"] == "prompt not found (early.prompt.md)"
    now = datetime(2026, 9, 9, 7, 0)
    assert [s["name"] for s in mod.specs() if mod.due_now(s, now, None)] == ["late"]
    for flags in ({"json": False, "markdown": True}, {"json": False, "markdown": False}, {"json": True, "markdown": False}):
        mod.cmd_list(type("A", (), flags))
    assert "prompt not found" in capsys.readouterr().out


def test_add_refuses_to_overwrite_repo_definition(tmp_path, monkeypatch):
    """Review P2: a fresh clone (or `remove`, which keeps repo files) has no pointer; add must not clobber."""
    import pytest
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    src = write_repo_job(repo)
    before = src.read_text()
    with pytest.raises(SystemExit, match="adopt"):
        mod.cmd_add(add_args(project=str(repo)))
    assert src.read_text() == before and (repo / mod.SCHEDULES_DIR / "nightly.prompt.md").read_text() == "go\n"
    (repo / mod.SCHEDULES_DIR / "nightly.json").unlink()  # prompt alone (someone's WIP) also blocks
    with pytest.raises(SystemExit, match="already defines"):
        mod.cmd_add(add_args(project=str(repo)))
    assert mod.cmd_add(add_args(project=str(repo), force=True)) == 0
    assert mod.cmd_add(add_args(name="nightly", project=str(repo), weekdays=False, once="2099-01-01", force=True)) == 0


# --- machine registration (machines: one|many, adopted_by) ---------------------------
def adopt_as(monkeypatch, tmp_path, machine, path, **kw):
    """Each simulated machine = its own HOME (identity + pointers), sharing one checkout."""
    monkeypatch.setenv("HOME", str(tmp_path / machine))
    return mod.cmd_adopt(type("A", (), {"path": str(path), "profile": None, "force": False, "takeover": False, **kw}))


def test_one_machine_takeover_displaces_old_primary(tmp_path, monkeypatch, capsys):
    import json
    import pytest
    from datetime import datetime
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    src = write_repo_job(repo)
    adopt_as(monkeypatch, tmp_path, "a", repo)
    a = mod.machine_identity()
    [owner] = json.loads(src.read_text())["adopted_by"]
    assert owner["id"] == a["id"] and owner["machine"] == f"machine-{a['id'][:8]}"
    assert mod.specs()[0]["displaced"] is None and mod.specs()[0]["name"] == "nightly"  # meta/machine.json is no job

    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    for kw in ({}, {"force": True}):  # unattended: refused, and --force is no takeover
        with pytest.raises(SystemExit, match="--takeover"):
            adopt_as(monkeypatch, tmp_path, "b", repo, **kw)
    assert not mod.paths("nightly")["spec"].exists() and json.loads(src.read_text())["adopted_by"] == [owner]
    adopt_as(monkeypatch, tmp_path, "b", repo, takeover=True)
    assert [o["id"] for o in json.loads(src.read_text())["adopted_by"]] == [mod.machine_identity()["id"]]
    assert "keeps firing until its checkout pulls" in capsys.readouterr().out

    monkeypatch.setenv("HOME", str(tmp_path / "a"))  # the old primary, after pulling the takeover
    spec = mod.load_spec(mod.paths("nightly")["spec"])
    assert spec["displaced"].startswith("displaced") and "displaced" in mod.job_flag(spec)
    assert not mod.due_now(spec, datetime(2026, 9, 9, 7, 0), None)
    assert mod.cmd_owner_check(type("A", (), {"name": "nightly"})) == mod.OWNER_SKIP_EXIT
    mod.identity_path().unlink()  # lost identity never mints a new one silently: still skips
    assert "identity missing" in mod.load_spec(mod.paths("nightly")["spec"])["displaced"]

    monkeypatch.setenv("HOME", str(tmp_path / "b"))
    assert mod.cmd_owner_check(type("A", (), {"name": "nightly"})) == 0
    mod.cmd_remove(type("A", (), {"name": "nightly"}))  # b leaves: a (displaced earlier) must stay skipped
    assert json.loads(src.read_text())["adopted_by"] == []
    monkeypatch.setenv("HOME", str(tmp_path / "a"))
    assert "no machine registered" in mod.load_spec(mod.paths("nightly")["spec"])["displaced"]
    adopt_as(monkeypatch, tmp_path, "b", repo)  # nobody registered: adopting needs no takeover
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: True)  # a terminal asks instead
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    with pytest.raises(SystemExit, match="not taken over"):
        adopt_as(monkeypatch, tmp_path, "c", repo)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    adopt_as(monkeypatch, tmp_path, "c", repo)
    assert json.loads(src.read_text())["adopted_by"][0]["id"] == mod.machine_identity()["id"]


def test_many_machines_and_idempotent_readopt(tmp_path, monkeypatch):
    import json
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    src = write_repo_job(repo)
    src.write_text(json.dumps({**json.loads(src.read_text()), "machines": "many"}))
    adopt_as(monkeypatch, tmp_path, "a", repo)
    first = json.loads(src.read_text())["adopted_by"][0]
    adopt_as(monkeypatch, tmp_path, "b", repo)
    owners = json.loads(src.read_text())["adopted_by"]
    assert len(owners) == 2 and owners[0] == first
    owners[0]["since"] = "2020-01-01"
    src.write_text(json.dumps({**json.loads(src.read_text()), "adopted_by": owners}))
    before = src.read_text()
    adopt_as(monkeypatch, tmp_path, "a", repo)  # re-adopt keeps `since`, writes nothing
    assert src.read_text() == before
    for home in ("a", "b"):
        monkeypatch.setenv("HOME", str(tmp_path / home))
        assert mod.load_spec(mod.paths("nightly")["spec"])["displaced"] is None


def test_legacy_spec_runs_and_registration_is_validated(tmp_path, monkeypatch):
    import json
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    src = write_repo_job(repo)
    base = json.loads(src.read_text())
    monkeypatch.setenv("HOME", str(tmp_path / "a"))
    mod.paths("nightly")["spec"].parent.mkdir(parents=True)
    mod.paths("nightly")["spec"].write_text(json.dumps(mod.pointer("nightly", src, None)))
    assert mod.load_spec(mod.paths("nightly")["spec"])["displaced"] is None  # nobody recorded, no identity: runs
    o = lambda i: {"machine": f"m{i}", "user": None, "since": "2026-01-01", "id": f"id{i}"}
    for bad in ({"machines": "some"}, {"adopted_by": [o(1), o(2)]}, {"machines": "many", "adopted_by": [o(1), o(1)]},
                {"adopted_by": [{"machine": "m"}]}, {"adopted_by": "m1"}):
        src.write_text(json.dumps({**base, **bad}))
        assert mod.load_spec(mod.paths("nightly")["spec"])["missing"].startswith("invalid"), bad


def test_repo_adopt_preflights_before_writing(tmp_path, monkeypatch):
    import json
    import pytest
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    write_repo_job(repo, "early")
    late = write_repo_job(repo, "late")
    late.write_text(json.dumps({**json.loads(late.read_text()),
                                "adopted_by": [{"machine": "m", "user": "X", "since": "2026-01-01", "id": "other"}]}))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit, match="late: one-machine job registered to m"):
        adopt_as(monkeypatch, tmp_path, "a", repo)
    assert mod.specs() == [] and "adopted_by" not in json.loads(mod.repo_files(repo, "early")[0].read_text())
    assert not mod.identity_path().exists()


def test_add_force_needs_takeover_and_remove_unregisters(tmp_path, monkeypatch, capsys):
    import json
    import pytest
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    src = write_repo_job(repo)
    adopt_as(monkeypatch, tmp_path, "a", repo)
    monkeypatch.setenv("HOME", str(tmp_path / "b"))
    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit, match="--takeover"):
        mod.cmd_add(add_args(project=str(repo), force=True))
    assert mod.cmd_add(add_args(project=str(repo), force=True, takeover=True, many_machines=True)) == 0
    stored = json.loads(src.read_text())
    assert stored["machines"] == "many" and len(stored["adopted_by"]) == 2  # many keeps a's registration
    mod.cmd_remove(type("A", (), {"name": "nightly"}))
    assert len(json.loads(src.read_text())["adopted_by"]) == 1 and "registry dropped" in capsys.readouterr().out
    monkeypatch.setenv("HOME", str(tmp_path / "a"))
    src.write_text("{broken")
    mod.cmd_remove(type("A", (), {"name": "nightly"}))  # disarms locally even when the repo spec is unreadable
    assert not mod.paths("nightly")["spec"].exists() and "registry NOT updated" in capsys.readouterr().out


def test_runner_checks_owner_before_wait_and_fire(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    base = {"name": "job", "project": "/r", "profile": None, "model": None, "thinking": None, "title": "t", "wait_max": 1}
    assert "owner_check" not in mod.runner_script(base, p)  # machine-local jobs have no registration
    body = mod.runner_script({**base, "source": "/r/.agents/schedules/job.json"}, p)
    calls = [i for i, line in enumerate(body.splitlines()) if line.strip() == "owner_check"]
    lines = body.splitlines()
    assert len(calls) == 2 and calls[0] < lines.index("  waited=0") and lines[calls[1] + 1].startswith("  out=$(")
    assert f"(( rc == {mod.OWNER_SKIP_EXIT} )) || fail" in body and "skipping" in body


def test_pending_resumes(tmp_path, monkeypatch):
    import json
    from datetime import datetime
    monkeypatch.setenv("HOME", str(tmp_path))
    base = {"at": "10:00", "days": None, "resume_thread": "T"}
    jobs = {
        "pending": {**base, "once": "2026-10-27"},
        "fired": {**base, "once": "2026-10-27"},
        "retired": {**base, "once": "2026-10-27", "retired": "fired 2026-09-01"},
        "expired": {**base, "once": "2026-09-01"},
        "weekly": {**base, "days": [1], "paused": True},
        "spawner": {"at": "10:00", "days": None, "once": "2026-10-27"},
    }
    for name, spec in jobs.items():
        mod.paths(name)["spec"].parent.mkdir(parents=True, exist_ok=True)
        mod.paths(name)["spec"].write_text(json.dumps({"name": name, **spec}))
    mod.paths("fired")["last"].write_text("2026-09-30\n")
    names = [spec["name"] for spec in mod.pending_resumes(datetime(2026, 9, 30, 12, 0))]
    assert names == ["pending", "weekly"]


def test_fire_unconfirmed_leaves_marker_and_never_refires(tmp_path, monkeypatch, capsys):
    rc, _ = fire(tmp_path, monkeypatch, {}, relay_rc=mod.PENDING_EXIT)
    marker = mod.paths("job")["pending"]
    assert rc == mod.PENDING_EXIT and marker.read_text().split()[:2] == [mod.date.today().isoformat(), "abc123"]
    rc, calls = fire(tmp_path, monkeypatch, {}, status_rc=mod.PENDING_EXIT)   # still pending: no new launch
    assert rc == mod.PENDING_EXIT and [c[:2] for c in calls] == [["t3-relay", "status"]]
    rc, calls = fire(tmp_path, monkeypatch, {}, status_rc=0)                  # landed late: done, no launch
    assert rc == 0 and len(calls) == 1 and not marker.exists()


def test_fire_after_failed_request_fires_anew(tmp_path, monkeypatch):
    fire(tmp_path, monkeypatch, {}, relay_rc=mod.PENDING_EXIT)
    rc, calls = fire(tmp_path, monkeypatch, {}, status_rc=1)
    assert rc == 0 and calls[0][:2] == ["t3-relay", "status"] and calls[1][:2] == ["t3-relay", "launch"]


def test_stale_marker_fails_without_refire(tmp_path, monkeypatch):
    fire(tmp_path, monkeypatch, {}, relay_rc=mod.PENDING_EXIT)
    marker = mod.paths("job")["pending"]
    day, rid, _ = marker.read_text().split()
    marker.write_text(f"{day} {rid} 0\n")
    rc, calls = fire(tmp_path, monkeypatch, {}, status_rc=mod.PENDING_EXIT)
    assert rc == 1 and len(calls) == 1


def test_runner_treats_pending_as_not_fired(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    body = mod.runner_script({"name": "job", "project": "/r", "profile": None, "model": None, "thinking": None,
                              "title": "t", "wait_max": 10}, p)
    pending, last = body.index(f"rc == {mod.PENDING_EXIT}"), body.index(f'echo "$today" > {p["last"]}')
    assert pending < last and "exit 0" in body[pending:last]


def test_accepted_request_survives_confirmation_crash(tmp_path, monkeypatch):
    """Sol review P1: POST accepted, then the lookup crashed (no verdict) → marker, never a re-fire."""
    rc, _ = fire(tmp_path, monkeypatch, {}, relay_rc=99)
    assert rc == mod.PENDING_EXIT and mod.paths("job")["pending"].exists()
    rc, calls = fire(tmp_path, monkeypatch, {}, status_rc=99)            # status crashes too: keep waiting
    assert rc == mod.PENDING_EXIT and len(calls) == 1 and mod.paths("job")["pending"].exists()


def mark_pending(day, since=None):
    from datetime import datetime
    mod.paths("job")["pending"].write_text(f"{day} abc123 {since if since is not None else datetime.now().timestamp():.0f}\n")


def test_pending_marker_survives_midnight(tmp_path, monkeypatch):
    """A late-night launch still unconfirmed after midnight blocks today's fire until t3-relay decides."""
    from datetime import timedelta
    yesterday = (mod.date.today() - timedelta(days=1)).isoformat()
    fire(tmp_path, monkeypatch, {}, status_rc=0)  # creates the job dirs
    mark_pending(yesterday)
    rc, calls = fire(tmp_path, monkeypatch, {}, status_rc=mod.PENDING_EXIT)
    assert rc == mod.PENDING_EXIT and [c[:2] for c in calls] == [["t3-relay", "status"]]
    assert mod.paths("job")["pending"].read_text().startswith(yesterday)
    rc, calls = fire(tmp_path, monkeypatch, {}, status_rc=0)  # yesterday's landed: today's still fires
    assert rc == 0 and [c[:2] for c in calls] == [["t3-relay", "status"], ["t3-relay", "launch"]]
    assert mod.last_fire("job") == mod.date.today().isoformat() and not mod.paths("job")["pending"].exists()


def test_forgotten_relay_record_retires_only_an_earlier_days_marker(tmp_path, monkeypatch):
    from datetime import timedelta
    fire(tmp_path, monkeypatch, {}, status_rc=0)
    mark_pending(mod.date.today().isoformat())
    rc, _ = fire(tmp_path, monkeypatch, {}, status_rc=2)  # today's request unknown: still never re-fired
    assert rc == mod.PENDING_EXIT
    mark_pending((mod.date.today() - timedelta(days=8)).isoformat())
    rc, calls = fire(tmp_path, monkeypatch, {}, status_rc=2)  # t3-relay keeps records 7 days
    assert rc == 0 and calls[-1][:2] == ["t3-relay", "launch"]


def test_fire_after_same_day_fire_is_a_no_op(tmp_path, monkeypatch):
    fire(tmp_path, monkeypatch, {}, status_rc=0)
    mod.paths("job")["last"].write_text(f"{mod.date.today().isoformat()}\n")
    import argparse
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: pytest.fail("fired twice"))
    assert mod.cmd_fire(argparse.Namespace(name="job")) == 0


def test_fire_refuses_an_unreadable_last_marker(tmp_path, monkeypatch, capsys):
    # A `.last` that exists but can't be read must not launch: recording the fire would fail, so every retry launched again.
    import argparse
    fire(tmp_path, monkeypatch, {}, status_rc=0)
    mod.paths("job")["last"].unlink(missing_ok=True)
    mod.paths("job")["last"].mkdir()
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: pytest.fail("launched with an unreadable .last"))
    assert mod.cmd_fire(argparse.Namespace(name="job")) == 1
    assert "UNREADABLE" in capsys.readouterr().out


def test_fire_waits_for_a_concurrent_fire(tmp_path, monkeypatch):
    import argparse
    import fcntl
    import threading
    fire(tmp_path, monkeypatch, {}, status_rc=0)
    mod.paths("job")["last"].unlink()
    result = []
    with mod.paths("job")["fire_lock"].open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        worker = threading.Thread(target=lambda: result.append(mod.cmd_fire(argparse.Namespace(name="job"))))
        worker.start()
        worker.join(0.3)
        assert worker.is_alive() and not result  # blocked behind the other fire
        mod.paths("job")["last"].write_text(f"{mod.date.today().isoformat()}\n")  # which fired meanwhile
    worker.join(5)
    assert result == [0]


def test_catch_up_confirms_a_once_job_for_its_own_day_before_retiring(tmp_path, monkeypatch):
    import argparse
    import subprocess
    from datetime import timedelta
    no_launchd(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "os_notify", lambda msg: None)
    monkeypatch.setattr(mod, "kickstart", lambda name: pytest.fail("kicked"))
    once = (mod.date.today() - timedelta(days=1)).isoformat()
    p = mod.paths("job")
    p["spec"].parent.mkdir(parents=True)
    p["spec"].write_text(json.dumps({"name": "job", "project": "/repo", "title": "t", "at": "22:30", "days": None,
                                     "once": once}))
    mark_pending(once)
    status = {"rc": 3}
    monkeypatch.setattr(mod.subprocess, "run", lambda argv, **_: subprocess.CompletedProcess(
        argv, status["rc"], {0: "ok mcp:t\n", 3: "pending\n"}[status["rc"]], ""))
    mod.cmd_catch_up(argparse.Namespace(dry_run=False))
    assert "retired" not in json.loads(p["spec"].read_text())  # accepted, maybe still landing: not "never fired"
    status["rc"] = 0
    mod.cmd_catch_up(argparse.Namespace(dry_run=False))
    assert mod.last_fire("job") == once and json.loads(p["spec"].read_text())["retired"] == f"fired {once}"


def test_unreadable_local_spec_and_markers_isolate_one_job(tmp_path, monkeypatch, capsys):
    import argparse
    from datetime import datetime
    no_launchd(monkeypatch, tmp_path)
    base = mod.runtime_dir()
    base.mkdir(parents=True)
    (base / "good.json").write_text(json.dumps({"name": "good", "project": "/r", "at": "05:00", "days": None}))
    (base / "bad.json").write_text('{"name": "bad", "at"')  # truncated by a crash mid-write
    (base / "good.last").mkdir()  # unreadable marker: treated as missing
    by_name = {s["name"]: s for s in mod.specs()}
    assert by_name["bad"]["missing"].startswith("local spec unreadable")
    assert mod.last_fire("good") is None and mod.due_now(by_name["good"], datetime.now().replace(hour=6), None)
    mod.cmd_catch_up(argparse.Namespace(dry_run=True))
    mod.cmd_list(argparse.Namespace(json=False, markdown=False))
    assert "bad" in capsys.readouterr().out
