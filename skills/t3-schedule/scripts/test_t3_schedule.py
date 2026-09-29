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
    assert body.count("display notification") == 2 and '\n    : osascript' in body  # success notification disabled, fail() kept
    default = mod.runner_script(base, p)
    assert "--hide" not in default and ": osascript" not in default


# --- continuation (--resume-thread) -------------------------------------------------
TID = "11111111-2222-3333-4444-555555555555"


def thread_data(**thread):
    msgs = [{"role": "user", "created_at": "2026-09-27T10:00:00", "text": "BRIEF investigate the outage"}]
    msgs += [{"role": r, "created_at": f"2026-09-27T11:{i:02d}:00", "text": f"msg{i} " + "x" * 50}
             for i, r in enumerate(["assistant", "user"] * 5)]
    return {"thread": {"thread_id": TID, "title": "Outage", "workspace_root": "/repo", "project_title": "repo",
                       "archived_at": None, "deleted_at": None,
                       "model_selection": {"instanceId": "claudeAgent", "model": "m"}, **thread},
            "messages": msgs}


def resume_job(tmp_path, monkeypatch, data, instances=frozenset({"claudeAgent"}), ping_rc=0, **spec):
    import json
    import subprocess
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("fu")
    p["spec"].parent.mkdir(parents=True)
    p["spec"].write_text(json.dumps({"name": "fu", "resume_thread": TID, **spec}))
    p["prompt"].write_text("Check the deploy.\n")
    monkeypatch.setattr(mod, "read_thread", lambda tid: (data, "" if data else f"No T3 thread matches {tid}"))
    monkeypatch.setattr(mod, "registered_instances", lambda: set(instances))
    calls = []
    def run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, ping_rc, "Pinged\n" if ping_rc == 0 else "", "")
    monkeypatch.setattr(mod.subprocess, "run", run)
    import argparse
    return mod.cmd_resume(argparse.Namespace(name="fu")), calls, p


def test_resume_healthy_pings(tmp_path, monkeypatch, capsys):
    rc, calls, p = resume_job(tmp_path, monkeypatch, thread_data(settled_at="2026-09-27"), hide=True)
    assert rc == 0 and not p["fallback"].exists()
    argv = calls[0]
    assert argv[:4] == ["t3-ping-thread", "--thread", TID, "--allow-cross-project"] and "--hide" in argv
    assert argv[-1].startswith("Scheduled follow-up (") and "as agreed earlier in this thread:\n\nCheck the deploy." in argv[-1]
    assert f"resumed Outage ({TID})" in capsys.readouterr().out


def test_resume_unhealthy_falls_back_with_context(tmp_path, monkeypatch, capsys):
    cases = [
        (None, {"claudeAgent"}, 0, "thread not found"),
        (thread_data(deleted_at="2026-09-28"), {"claudeAgent"}, 0, "thread deleted"),
        (thread_data(), {"codex"}, 0, "profile claudeAgent no longer registered"),
        (thread_data(), {"claudeAgent"}, 1, "ping failed (exit 1)"),
    ]
    for data, instances, ping_rc, reason in cases:
        rc, calls, p = resume_job(tmp_path, monkeypatch, data, instances, ping_rc)
        assert rc == mod.FALLBACK_EXIT and f"fallback: {reason}" in capsys.readouterr().out
        assert bool(calls) == (ping_rc != 0)  # unhealthy → no ping attempted
        pack = p["fallback"].read_text()
        assert pack.startswith("Check the deploy.\n\n---\nContext:") and TID in pack and reason in pack
        if data:
            assert "## Original brief\nBRIEF investigate" in pack and "msg9" in pack and "msg3" not in pack
        import shutil
        shutil.rmtree(tmp_path / ".t3")


def test_resume_failed_ping_that_landed_does_not_double_fire(tmp_path, monkeypatch, capsys):
    from datetime import date
    data = thread_data()
    marker = mod.resume_marker("fu", date.today().isoformat())
    data["messages"].append({"role": "user", "created_at": "2026-09-28T10:00:00", "text": marker + ", as agreed…"})
    rc, _, p = resume_job(tmp_path, monkeypatch, data, ping_rc=1)  # ack lost, turn delivered
    assert rc == 0 and not p["fallback"].exists() and "resumed Outage" in capsys.readouterr().out


def test_resume_accepts_legacy_provider_selection():
    data = thread_data(model_selection={"provider": "claudeAgent", "model": "m"})
    assert mod.resume_blocker(data, "", {"claudeAgent"}) is None


def test_context_pack_is_bounded():
    data = thread_data()
    for m in data["messages"]:
        m["text"] = "y" * 50000
    pack = mod.context_pack(TID, data, "thread deleted")
    assert len(pack) <= mod.PACK_MAX_CHARS + 500 and "## Original brief" in pack and "more chars]" in pack


def test_resume_runner_and_add_validation(tmp_path, monkeypatch, capsys):
    import argparse
    import pytest
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("fu")
    base = {"name": "fu", "project": "/r", "profile": None, "model": None, "thinking": None, "title": "t", "wait_max": 1}
    plain = mod.runner_script(base, p)
    assert "t3-schedule resume-thread" not in plain and '-- "$(cat "$prompt_file")"' in plain
    body = mod.runner_script({**base, "resume_thread": TID}, p)
    assert body.index("t3-schedule resume-thread fu") < body.index("for candidate in")  # resume before any spawn
    assert f"(( rc == {mod.FALLBACK_EXIT} )) || fail" in body and f"prompt_file={p['fallback']}" in body
    assert body.count(str(p["last"])) == 3  # daily guard + resume success + spawn success

    monkeypatch.setattr(mod, "registered_instances", lambda: {"claudeAgent"})
    monkeypatch.setattr(mod, "read_thread", lambda tid: (thread_data(workspace_root=str(tmp_path)), ""))
    add = lambda **kw: mod.cmd_add(argparse.Namespace(**{
        "name": "fu", "at": "07:30", "once": None, "weekdays": False, "days": None, "project": None,
        "profile": None, "model": None, "thinking": None, "settle_when_done": False, "hide": False,
        "no_notify": False, "title": None, "prompt_file": None, "prompt": ["go"], "wait_max": 1,
        "force": False, "dry_run": True, "resume_thread": TID, "many_machines": False, "takeover": False, **kw}))
    assert add() == 0 and "t3-schedule resume-thread fu" in capsys.readouterr().out  # project from the thread
    with pytest.raises(SystemExit, match="settle-when-done"):
        add(settle_when_done=True)
    with pytest.raises(SystemExit, match="--project is required"):
        add(resume_thread=None)
    monkeypatch.setattr(mod, "read_thread", lambda tid: (None, "No T3 thread matches x"))
    with pytest.raises(SystemExit, match="thread not found"):
        add()


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
        "profile": "work", "model": "fable", "thinking": None, "settle_when_done": True, "hide": False,
        "no_notify": False, "title": None, "prompt_file": None, "prompt": ["Run the report."], "wait_max": 10,
        "force": False, "dry_run": False, "resume_thread": None, "many_machines": False, "takeover": False, **kw})


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
    assert stored == {"at": "07:30", "days": mod.WEEKDAYS, "title": "⏰ nightly {date}", "model": "fable", "thinking": None,
                      "settle_when_done": True, "hide": False, "notify": True, "wait_max": 10, "machines": "one",
                      "paused": False, "pause_until": None}
    assert prompt.read_text() == "Run the report.\n"
    p = mod.paths("nightly")
    assert json.loads(p["spec"].read_text()) == {"name": "nightly", "source": str(src), "profile": "work"}
    assert not p["prompt"].exists() and f"prompt_file={prompt}" in p["sh"].read_text()
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
    assert mod.cmd_owner_check(argparse.Namespace(name="nightly")) == mod.OWNER_SKIP_EXIT  # old runner
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


def test_pause_validation_and_old_continuation_resume(tmp_path, monkeypatch):
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
    local = mod.paths("fu")["spec"]
    local.write_text(json.dumps({"name": "fu", "resume_thread": "thread-id"}))
    monkeypatch.setattr(mod, "cmd_resume", lambda args: 77)
    assert mod.main(["resume", "fu"]) == 77  # existing generated runner compatibility


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
    assert "--project " + str(repo) in p["sh"].read_text() and p["plist"].exists()
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


def test_migrate_moves_local_recurring_only(tmp_path, monkeypatch):
    import json
    no_launchd(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    mod.cmd_add(add_args(project=str(repo), weekdays=False))
    mod.cmd_add(add_args(name="oneoff", project=str(repo), weekdays=False, once="2099-01-01"))
    # simulate a pre-versioning job: full spec + prompt in the runtime dir
    p = mod.paths("legacy")
    p["spec"].write_text(json.dumps({"name": "legacy", "project": str(repo), "profile": "work", "model": "fable",
                                     "thinking": None, "title": "t", "at": "05:00", "days": None, "created": "x"}))
    p["prompt"].write_text("legacy prompt\n")
    assert mod.job_flag(mod.load_spec(p["spec"])).startswith("local-only")
    mod.cmd_migrate(type("A", (), {"names": [], "force": False, "takeover": False}))
    src, prompt = mod.repo_files(repo, "legacy")
    assert json.loads(p["spec"].read_text()) == {"name": "legacy", "source": str(src), "profile": "work"}
    assert prompt.read_text() == "legacy prompt\n" and not p["prompt"].exists()
    repo_spec = json.loads(src.read_text())  # pre-versioning specs lack hide/notify/wait_max: defaults, never null
    assert "profile" not in repo_spec and repo_spec["wait_max"] == mod.DEFAULT_WAIT_MAX
    assert repo_spec["notify"] is True and repo_spec["hide"] is False and repo_spec["settle_when_done"] is False
    assert not mod.repo_files(repo, "oneoff")[0].exists()  # one-shots stay machine-local


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


def test_runner_checks_owner_before_wait_and_spawn(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = mod.paths("job")
    base = {"name": "job", "project": "/r", "profile": None, "model": None, "thinking": None, "title": "t", "wait_max": 1}
    assert "owner_check" not in mod.runner_script(base, p)  # machine-local jobs have no registration
    body = mod.runner_script({**base, "source": "/r/.agents/schedules/job.json"}, p)
    calls = [i for i, line in enumerate(body.splitlines()) if line.strip() == "owner_check"]
    lines = body.splitlines()
    assert len(calls) == 2 and calls[0] < lines.index("  waited=0") and lines[calls[1] + 1].startswith("  out=$(")
    assert f"(( rc == {mod.OWNER_SKIP_EXIT} )) || fail" in body and "skipping" in body
