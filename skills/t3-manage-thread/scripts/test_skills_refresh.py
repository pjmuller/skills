"""skills-refresh against a local release repo: apply, idempotence, rollback, lock."""
import os
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("skills-refresh")
INSTALL = '#!/usr/bin/env bash\nset -eu\n[[ "${1:-}" == --check ]] && { echo "ok demo"; exit 0; }\ntouch "$T3_MANAGE_BIN/demo"\n'
LOG_V1 = "# Changelog\n\n## v0.1.0 (2026-01-01)\n- first release\n"
LOG_V2 = "# Changelog\n\n## Unreleased\n- not yet\n\n## v0.2.0 (2026-02-01)\n- second release\n\n## v0.1.0 (2026-01-01)\n- first release\n"


def git(repo, *args):
    # Neutralize a global tag/commit signing config.
    subprocess.run(["git", "-C", str(repo), "-c", "tag.gpgSign=false", "-c", "commit.gpgSign=false", *args],
                   check=True, capture_output=True)


def release(repo, tag, version, install=INSTALL, changelog=LOG_V2):
    scripts = repo / "skills/demo/scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (repo / "skills/demo/SKILL.md").write_text(f"demo {version}\n")
    (scripts / "install").write_text(install)
    (scripts / "install").chmod(0o755)
    (repo / "CHANGELOG.md").write_text(changelog)
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", tag)
    git(repo, "tag", tag)


@pytest.fixture
def env(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    release(repo, "v0.1.0", "1", changelog=LOG_V1)
    release(repo, "v0.2.0", "2")
    home = tmp_path / "agents"
    (home / "skills/demo").mkdir(parents=True)
    (home / "skills/demo/SKILL.md").write_text("demo 1\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith("SKILLS_REFRESH")}
    e.update(SKILLS_REFRESH_HOME=str(home), SKILLS_REFRESH_REPO=str(repo), T3_MANAGE_BIN=str(bin_dir))
    return {"repo": repo, "home": home, "bin": bin_dir, "env": e}


def run(env, *args, **extra):
    return subprocess.run(["bash", str(SCRIPT), *args], env={**env["env"], **extra},
                          text=True, capture_output=True)


def stamp(env):
    path = env["home"] / "pjmuller-skills.version"
    return path.read_text().split()[0] if path.exists() else None


def test_applies_newest_tag_then_is_idempotent(env):
    result = run(env)
    assert result.returncode == 10, result.stderr
    assert "applied v0.2.0 (was none)" in result.stdout
    assert "second release" in result.stdout
    assert "first release" not in result.stdout and "not yet" not in result.stdout
    assert stamp(env) == "v0.2.0"
    assert (env["home"] / "skills/demo/SKILL.md").read_text() == "demo 2\n"
    assert (env["bin"] / "demo").exists()
    assert not (env["home"] / "pjmuller-skills/staging/v0.2.0").exists()
    assert run(env, "--version").stdout.startswith("v0.2.0 (applied ")
    again = run(env)
    assert again.returncode == 0 and "up to date: v0.2.0" in again.stdout


def test_changelog_since_installed_tag(env):
    (env["home"] / "pjmuller-skills.version").write_text("v0.1.0 2026-01-01\n")
    release(env["repo"], "v0.3.0", "3", changelog=LOG_V2.replace("## v0.2.0", "## v0.3.0 (2026-03-01)\n- third\n\n## v0.2.0"))
    result = run(env)
    assert result.returncode == 10
    assert "third" in result.stdout and "second release" in result.stdout
    assert "first release" not in result.stdout


def test_symlinked_skill_is_left_alone(env, tmp_path):
    source = tmp_path / "checkout/demo"
    source.parent.mkdir()
    (env["home"] / "skills/demo").rename(source)
    (env["home"] / "skills/demo").symlink_to(source)
    result = run(env)
    assert result.returncode == 0 and "nothing to manage" in result.stdout
    assert stamp(env) is None


def test_forced_tag_equal_to_installed(env):
    (env["home"] / "pjmuller-skills.version").write_text("v0.1.0 2026-01-01\n")
    result = run(env, SKILLS_REFRESH_TAG="v0.1.0")
    assert result.returncode == 0 and "up to date: v0.1.0" in result.stdout


def test_failed_install_rolls_back(env):
    assert run(env).returncode == 10
    release(env["repo"], "v0.3.0", "3", install="#!/usr/bin/env bash\nexit 1\n")
    result = run(env)
    assert result.returncode == 1 and "rolling back" in result.stderr
    assert (env["home"] / "skills/demo/SKILL.md").read_text() == "demo 2\n"
    assert stamp(env) == "v0.2.0"


def test_syntax_error_blocks_activation(env):
    release(env["repo"], "v0.3.0", "3", install="#!/usr/bin/env bash\nif then fi (\n")
    result = run(env)
    assert result.returncode == 1 and "syntax error" in result.stderr
    assert (env["home"] / "skills/demo/SKILL.md").read_text() == "demo 1\n"
    assert not (env["bin"] / "demo").exists() and stamp(env) is None


def test_lock(env):
    lock = env["home"] / "pjmuller-skills/lock"
    lock.mkdir(parents=True)
    result = run(env)
    assert result.returncode == 1 and "another run" in result.stderr
    old = time.time() - 2 * 3600
    os.utime(lock, (old, old))
    assert run(env).returncode == 10
    assert not lock.exists()


def test_failed_activation_rolls_back(env):
    assert run(env).returncode == 10
    release(env["repo"], "v0.3.0", "3")
    locked = env["home"] / "skills/.demo.new/locked"   # a staging leftover that cannot be cleared
    locked.mkdir(parents=True)
    (locked / "x").touch()
    locked.chmod(0o555)
    try:
        result = run(env)
    finally:
        locked.chmod(0o755)
    assert result.returncode == 1 and "rolling back" in result.stderr
    assert (env["home"] / "skills/demo/SKILL.md").read_text() == "demo 2\n"
    assert stamp(env) == "v0.2.0"


def test_job_outside_t3_passes_exit_code_through(env):
    e = {k: v for k, v in env["env"].items() if k not in ("CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID")}
    result = subprocess.run(["bash", str(SCRIPT), "--job"], env=e, text=True, capture_output=True)
    assert result.returncode == 10 and "not inside a T3 thread" in result.stdout
    assert subprocess.run(["bash", str(SCRIPT), "--job", "--quiet"], env=e, text=True, capture_output=True).returncode == 0
