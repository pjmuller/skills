"""t3-my-prompts --skills: which invocations count as using a skill, and maintenance vs use."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import skill_usage
from v2_fixture import Store


def skill(root: Path, name: str, command: str | None = None) -> Path:
    (root / name).mkdir(parents=True)
    (root / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    if command:
        (root / name / "scripts").mkdir()
        (root / name / "scripts" / command).write_text("#!/bin/sh\n")
        (root / name / "scripts" / command).chmod(0o755)
        (root / name / "scripts" / "install").write_text("#!/bin/sh\n")
        (root / name / "scripts" / "install").chmod(0o755)
    return root / name


def test_counts_invocations_and_separates_maintenance(tmp_path: Path, monkeypatch) -> None:
    home, source = tmp_path / "home", tmp_path / "source-repo"
    skill(source / "skills", "alpha", "alpha-cmd")
    (home / ".agents/skills").mkdir(parents=True)
    (home / ".agents/skills/alpha").symlink_to(source / "skills/alpha")
    skill(home / ".agents/skills", "beta")
    skill(home / ".agents/skills", "idle")
    skill(home / ".agents/skills", "gamma", "audit.sh")
    s = Store(tmp_path / "statev2.sqlite")
    s.db.execute("INSERT INTO projection_projects VALUES ('src', 'source', ?, NULL)", (str(source),))
    for tid, project in [("t1", "p"), ("t2", "p"), ("t3", "p"), ("t4", "src")]:
        s.thread(tid, tid, project=project)
    s.item("t1", "command_execution", {"input": "alpha-cmd --json | jq ."}, 5)
    s.item("t1", "command_execution", {"input": "cat ~/.agents/skills/beta/SKILL.md"}, 5)
    s.item("t2", "dynamic_tool", {"toolName": "Skill", "input": {"skill": "beta"}}, 5)
    s.item("t3", "command_execution", {"input": "echo hi", "output": "alpha-cmd beta/SKILL.md"}, 5)
    s.item("t3", "command_execution", {"input": "./install && my-alpha-cmd"}, 5)
    s.item("t4", "command_execution", {"input": "alpha-cmd --help"}, 5)
    s.thread("t5", "t5")
    s.item("t5", "command_execution", {"input": "cd x && FOO=1 uv run ./scripts/audit.sh --dry-run | head"}, 5)
    s.thread("t6", "t6")
    s.item("t6", "command_execution", {"input": "echo alpha-cmd; rg 'alpha-cmd' README.md"}, 5)
    s.item("t6", "dynamic_tool", {"toolName": "Grep", "input": {"pattern": "alpha-cmd"}}, 5)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    now = datetime.now(timezone.utc)
    skills, _ = skill_usage.count(s.close(), now - timedelta(days=1), now + timedelta(minutes=1))
    rows = {name: (len(x.used), len(x.maintained)) for name, x in skills.items()}
    # Tool output and look-alike words never count; the skill's own repo is maintenance.
    assert rows == {"alpha": (1, 1), "beta": (2, 0), "gamma": (1, 0), "idle": (0, 0)}


def test_executed_takes_programs_not_arguments() -> None:
    assert skill_usage.executed("timeout 60 /x/scripts/t3-fleet list | jq . && echo t3-drafts") == {"t3-fleet", "jq", "echo"}
    assert skill_usage.executed("$(t3-pick-instance sol)") == {"t3-pick-instance"}
    assert skill_usage.executed('read a b <<< "$(t3-pick-instance sol)"') == {"read", "t3-pick-instance"}
    assert skill_usage.executed('echo "$(printf x)" alpha-cmd') == {"echo", "printf"}
    assert skill_usage.executed('echo "$(echo $(printf x); alpha-cmd)"') == {"echo", "printf", "alpha-cmd"}
    assert skill_usage.executed('echo "`alpha-cmd`"; x=$( (cd a; b-cmd) | c-cmd ) d') == {"echo", "alpha-cmd", "cd", "b-cmd", "c-cmd", "d"}
    assert skill_usage.executed("rg 'foo|alpha-cmd' README.md; git commit -m \"a; alpha-cmd\nb\"") == {"rg", "git"}
