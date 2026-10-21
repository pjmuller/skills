"""skills-refresh against a local release repo: apply, idempotence, rollback, lock."""
import os
import re
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

def signed_tag(repo, tag, key=None):
    key = key or repo.parent / "signer"
    git(repo, "-c", "gpg.format=ssh", "-c", f"user.signingkey={key}",
        "-c", "user.name=Release Test", "-c", "user.email=release@example.test",
        "tag", "-s", "-m", tag, tag)


def release(repo, tag, version, install=INSTALL, changelog=LOG_V2):
    scripts = repo / "skills/demo/scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (repo / "skills/demo/SKILL.md").write_text(f"demo {version}\n")
    (scripts / "install").write_text(install)
    (scripts / "install").chmod(0o755)
    (repo / "CHANGELOG.md").write_text(changelog)
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", tag)
    signed_tag(repo, tag)


@pytest.fixture
def env(tmp_path):
    key = tmp_path / "signer"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    # Explicit local re-enrollment in a disposable script; production has no env bypass.
    script = tmp_path / "skills-refresh"
    pin = 'release-test namespaces="git" ' + key.with_suffix(".pub").read_text().strip()
    script.write_text(re.sub(r"ALLOWED_SIGNERS='[^']*'", f"ALLOWED_SIGNERS='{pin}'", SCRIPT.read_text())
                      .replace("MIN_VERIFYING_RELEASE='v0.5.5'", "MIN_VERIFYING_RELEASE='v0.1.0'"))
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
    e.update(SKILLS_REFRESH_HOME=str(home), SKILLS_REFRESH_REPO=str(repo), T3_MANAGE_BIN=str(bin_dir),
             T3CODE_HOME=str(tmp_path / "t3"), HOME=str(tmp_path / "userhome"))
    return {"repo": repo, "home": home, "bin": bin_dir, "env": e, "script": script, "key": key}


def run(env, *args, **extra):
    return subprocess.run(["bash", str(env["script"]), *args], env={**env["env"], **extra},
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


def test_refuses_release_on_t3_0_0_x(env, tmp_path):
    (tmp_path / "t3/userdata").mkdir(parents=True)
    (tmp_path / "t3/userdata/state.sqlite").write_text("")  # V1 store only = T3 0.0.x
    result = run(env)
    assert result.returncode == 1 and "needs T3 Code >= 0.1.0" in result.stderr and stamp(env) is None
    (tmp_path / "t3/userdata/statev2.sqlite").write_text("")
    assert run(env).returncode == 10 and stamp(env) == "v0.2.0"


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


def test_job_passes_exit_code_through_and_states_lifecycle(env):
    result = run(env, "--job")
    assert result.returncode == 10 and result.stdout.rstrip().endswith("thread: KEEP OPEN (the user should see this)")
    quiet = run(env, "--job", "--quiet")
    assert quiet.returncode == 0 and "thread: SETTLE (nothing for the user): call the T3 MCP tool t3_thread_organize" in quiet.stdout.splitlines()[-1]


def test_version_source_checkout_vs_copy_inside_other_repo(env, tmp_path):
    # Managed copy: ~/.agents/skills symlinked into a setup repo's ai/skills (a real dir in git).
    setup = tmp_path / "setup"
    (setup / "ai/skills/t3-manage-thread").mkdir(parents=True)
    (setup / "ai/skills/t3-manage-thread/SKILL.md").write_text("x\n")
    git(setup, "init", "-q")
    git(setup, "add", "-A")
    git(setup, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "setup")
    home = tmp_path / "copy-home"
    home.mkdir()
    (home / "skills").symlink_to(setup / "ai/skills")
    (home / "pjmuller-skills.version").write_text("v0.2.0 2026-02-01\n")
    assert run(env, "--version", SKILLS_REFRESH_HOME=str(home)).stdout.startswith("v0.2.0 (applied 2026-02-01)")
    # Source checkout: the skill dir symlinks to <this repo>/skills/t3-manage-thread.
    (env["repo"] / "skills/t3-manage-thread").mkdir()
    (env["home"] / "skills/t3-manage-thread").symlink_to(env["repo"] / "skills/t3-manage-thread")
    assert run(env, "--version").stdout.startswith("source checkout v0.2.0")


# --- global prompt re-sync (prompt_sync) ---

TEMPLATE = "skills/agents-md/global-template.md"


def commit(repo, msg, date="2026-01-01T00:00:00"):
    git(repo, "add", "-A")
    subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgSign=false", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", msg], check=True, capture_output=True,
                   env={**os.environ, "GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date})
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, capture_output=True).stdout.strip()


@pytest.fixture
def tenv(env, tmp_path):
    """Release v0.3.0 changes the template; the user's prompt lives in a committed setup repo."""
    repo = env["repo"]
    (repo / TEMPLATE).parent.mkdir(parents=True)
    (repo / TEMPLATE).write_text("rule one\n")
    old = commit(repo, "template v1", "2026-03-01T00:00:00")
    (repo / TEMPLATE).write_text("rule one\nrule two\n")
    commit(repo, "template v2", "2026-05-01T00:00:00")
    signed_tag(repo, "v0.3.0")
    setup = tmp_path / "setup"
    (setup / "ai").mkdir(parents=True)
    git(setup, "init", "-q")
    prompt = setup / "ai/AGENTS.md"
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "t3-pick-instance").write_text('#!/bin/sh\n[ "$1" = claude ] && echo "claudeAgent claude-opus-5-5 high"\n')
    (stub / "t3-pick-instance").chmod(0o755)
    env["env"].update(SKILLS_REFRESH_PROMPT=str(prompt), PATH=f"{stub}:{os.environ['PATH']}")
    return {**env, "old": old, "setup": setup, "prompt": prompt, "stub": stub}


def job(env):
    return run(env, "--job")


def brief(env):
    return (env["home"] / "pjmuller-skills/template-sync.md").read_text()


def test_marker_at_installed_tag_settles(tenv):
    tenv["prompt"].write_text("me\n<!-- template: pjmuller/skills@v0.3.0 -->\n")
    commit(tenv["setup"], "prompt")
    result = job(tenv)
    assert result.stdout.splitlines()[-1].startswith("thread: KEEP OPEN")  # skills applied; no re-sync line
    assert "template check" not in result.stdout and not (tenv["home"] / "pjmuller-skills/repo.git").exists()
    assert job(tenv).stdout.splitlines()[-1].startswith("thread: SETTLE")  # rerun: silent


def test_old_marker_delegates_with_three_way_brief(tenv):
    tenv["prompt"].write_text(f"me\n<!-- template: pjmuller/skills@{tenv['old'][:7]}; tailored -->\n")
    commit(tenv["setup"], "prompt")
    last = job(tenv).stdout.splitlines()[-1]
    assert last.startswith("thread: DELEGATE") and '"providerInstanceId":"claudeAgent"' in last
    assert '"options":{"effort":"high"}' in last and "Never settle" in last
    text = brief(tenv)
    assert f"Base: `{tenv['old']}` (marker {tenv['old'][:7]})" in text
    assert "uncommitted" not in text and "@v0.3.0" in text and "TAG" not in text


def test_dirty_prompt_asks_instead_of_merging(tenv):
    tenv["prompt"].write_text(f"me\n<!-- template: pjmuller/skills@{tenv['old']} -->\n")
    commit(tenv["setup"], "prompt")
    tenv["prompt"].write_text(tenv["prompt"].read_text() + "local tweak\n")
    assert job(tenv).stdout.splitlines()[-1].startswith("thread: DELEGATE")
    assert "uncommitted edits: change nothing" in brief(tenv)


def test_missing_marker_infers_base_from_first_commit(tenv):
    tenv["prompt"].write_text("me\n")
    commit(tenv["setup"], "prompt", "2026-04-01T00:00:00")  # between template v1 and v2
    tenv["prompt"].write_text("me, edited\n")
    commit(tenv["setup"], "edit", "2026-06-01T00:00:00")  # later edits don't move the base
    assert job(tenv).stdout.splitlines()[-1].startswith("thread: DELEGATE")
    assert f"Base: `{tenv['old']}` (no marker; base inferred" in brief(tenv)


def test_uncommitted_prompt_or_no_router_keeps_open(tenv):
    tenv["prompt"].write_text("me\n")  # never committed
    result = job(tenv)
    assert "not committed in a git repository" in result.stdout
    assert result.stdout.splitlines()[-1].startswith("thread: KEEP OPEN")
    commit(tenv["setup"], "prompt")
    (tenv["stub"] / "t3-pick-instance").write_text("#!/bin/sh\nexit 1\n")
    result = job(tenv)
    assert "ask a frontier agent" in result.stdout and result.stdout.splitlines()[-1].startswith("thread: KEEP OPEN")


def test_unreachable_history_keeps_open(tenv):
    tenv["prompt"].write_text(f"me\n<!-- template: pjmuller/skills@{tenv['old']} -->\n")
    commit(tenv["setup"], "prompt")
    job(tenv)  # applies v0.3.0, fills the cache
    (tenv["home"] / "pjmuller-skills/repo.git/config").write_text("garbage\n")
    result = job(tenv)
    assert "cannot fetch" in result.stdout and result.stdout.splitlines()[-1].startswith("thread: KEEP OPEN")


def test_odd_paths_keep_brief_and_json_intact(tenv, tmp_path):
    import json
    home = tmp_path / 'we"ird&home'
    (home / "skills/demo").mkdir(parents=True)
    (home / "skills/demo/SKILL.md").write_text("demo 1\n")
    prompt = tenv["setup"] / "ai/Prompt&rules.md"
    prompt.write_text(f"me\n<!-- template: pjmuller/skills@{tenv['old']} -->\n")
    commit(tenv["setup"], "prompt")
    tenv["env"].update(SKILLS_REFRESH_HOME=str(home), SKILLS_REFRESH_PROMPT=str(prompt))
    last = job(tenv).stdout.splitlines()[-1]
    payload = json.loads(last.split("delegate_task with ", 1)[1].split(", end the turn", 1)[0])
    assert payload["task"] == f"Read and execute {home}/pjmuller-skills/template-sync.md"
    assert f"bash -s -- {prompt.resolve()}" in (home / "pjmuller-skills/template-sync.md").read_text()


def test_old_job_prompt_is_migrated_once(tenv, tmp_path):
    sched = tenv["setup"] / ".agents/schedules"
    sched.mkdir(parents=True)
    (sched / "skills-refresh.json").write_text("{}\n")
    old = ("Run exactly one command: `skills-refresh --job --quiet`. Then end the turn with its complete output as your answer, nothing else.\n"
           "Its last line decides this thread's lifecycle: `thread: SETTLE` → settle; `thread: KEEP OPEN` → just answer. Never retry, never fix anything.\n")
    (sched / "skills-refresh.prompt.md").write_text(old)
    pointer = tmp_path / "userhome/.t3/userdata/scheduled/t3-schedule/skills-refresh.json"
    pointer.parent.mkdir(parents=True)
    import json
    pointer.write_text(json.dumps({"name": "skills-refresh", "source": str(sched / "skills-refresh.json")}, indent=2))
    tenv["prompt"].write_text("me\n<!-- template: pjmuller/skills@v0.3.0 -->\n")
    commit(tenv["setup"], "prompt")
    job(tenv)  # applies v0.3.0
    new = (sched / "skills-refresh.prompt.md").read_text()
    assert "thread: DELEGATE" in new and "--job --quiet" in new
    assert job(tenv).stdout.splitlines()[-1].startswith("thread: SETTLE")  # migrated once, then silent


def test_customised_job_prompt_is_left_alone(tenv, tmp_path):
    import json
    sched = tenv["setup"] / ".agents/schedules"
    sched.mkdir(parents=True)
    custom = ("Run exactly one command: `skills-refresh --job`. Then end the turn with its complete output as your answer, nothing else.\n"
              "Its last line decides this thread's lifecycle: `thread: KEEP OPEN` → just answer.\nAlso run my security check.\n")
    (sched / "skills-refresh.prompt.md").write_text(custom)
    pointer = tmp_path / "userhome/.t3/userdata/scheduled/t3-schedule/skills-refresh.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({"source": str(sched / "skills-refresh.json")}))
    tenv["prompt"].write_text("me\n<!-- template: pjmuller/skills@v0.3.0 -->\n")
    commit(tenv["setup"], "prompt")
    job(tenv)
    assert (sched / "skills-refresh.prompt.md").read_text() == custom


@pytest.mark.parametrize("kind", ["lightweight", "unsigned", "unknown", "tampered", "replayed"])
def test_untrusted_tag_never_activates_even_with_forced_tag(env, tmp_path, kind):
    assert run(env).returncode == 10
    release(env["repo"], "v0.3.0", "3")
    repo = env["repo"]
    raw = subprocess.check_output(["git", "-C", str(repo), "cat-file", "tag", "v0.3.0"])
    git(repo, "tag", "-d", "v0.3.0")
    if kind == "lightweight":
        git(repo, "tag", "v0.3.0")
    elif kind == "unsigned":
        git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "tag", "-a", "-m", "unsigned", "v0.3.0")
    elif kind == "unknown":
        key = tmp_path / "attacker"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        signed_tag(repo, "v0.3.0", key)
    elif kind == "tampered":
        changed = raw.replace(b"\nv0.3.0\n", b"\nchanged message\n", 1)
        assert changed != raw
        oid = subprocess.check_output(["git", "-C", str(repo), "hash-object", "-w", "-t", "tag", "--stdin"],
                                      input=changed).decode().strip()
        git(repo, "update-ref", "refs/tags/v0.3.0", oid)
    else:
        git(repo, "update-ref", "refs/tags/v0.3.0", "refs/tags/v0.2.0")
    result = run(env, "--job", "--quiet", SKILLS_REFRESH_TAG="v0.3.0")
    assert result.returncode == 1
    assert "verification failed" in result.stderr
    assert result.stdout.rstrip().endswith("thread: KEEP OPEN (the user should see this)")
    assert stamp(env) == "v0.2.0"
    assert (env["home"] / "skills/demo/SKILL.md").read_text() == "demo 2\n"
    assert not (env["home"] / "pjmuller-skills/staging/v0.3.0").exists()


def test_same_named_branch_cannot_replace_signed_commit(env):
    release(env["repo"], "v0.3.0", "3")
    git(env["repo"], "branch", "v0.2.0")  # branch has demo 3, tag has demo 2
    result = run(env, SKILLS_REFRESH_TAG="v0.2.0")
    assert result.returncode == 10, result.stderr
    assert (env["home"] / "skills/demo/SKILL.md").read_text() == "demo 2\n"
    expected = subprocess.check_output(["git", "-C", str(env["repo"]), "rev-parse",
                                       "refs/tags/v0.2.0^{commit}"]).decode().strip()
    assert (env["home"] / "pjmuller-skills.version").read_text().split()[2] == expected


def test_downgrade_requires_explicit_signed_tag(env):
    assert run(env).returncode == 10
    git(env["repo"], "tag", "-d", "v0.2.0")
    result = run(env)
    assert result.returncode == 1 and "refusing downgrade" in result.stderr
    assert run(env, SKILLS_REFRESH_TAG="v0.1.0").returncode == 10


def test_even_signed_forced_downgrade_cannot_remove_verification(env):
    assert run(env).returncode == 10
    env["script"].write_text(env["script"].read_text().replace(
        "MIN_VERIFYING_RELEASE='v0.1.0'", "MIN_VERIFYING_RELEASE='v0.2.0'"))
    result = run(env, "--job", SKILLS_REFRESH_TAG="v0.1.0")
    assert result.returncode == 1 and "predates mandatory verification" in result.stderr
    assert stamp(env) == "v0.2.0"
    assert result.stdout.rstrip().endswith("thread: KEEP OPEN (the user should see this)")


@pytest.mark.parametrize("tag", ["../../escape", "--upload-pack=bad", "main"])
def test_invalid_forced_tag_cannot_escape_staging(env, tag):
    result = run(env, SKILLS_REFRESH_TAG=tag)
    assert result.returncode == 1 and "invalid release tag" in result.stderr


def test_prompt_sync_ignores_retargeted_tag(tenv):
    tenv["prompt"].write_text(f"me\n<!-- template: pjmuller/skills@{tenv['old']} -->\n")
    commit(tenv["setup"], "prompt")
    assert job(tenv).returncode == 10
    original = brief(tenv)
    cache = tenv["home"] / "pjmuller-skills/repo.git"
    # Both remote and cache now lie about the installed tag. The recorded SHA wins.
    (tenv["repo"] / TEMPLATE).write_text("attacker instruction\n")
    evil = commit(tenv["repo"], "evil")
    git(tenv["repo"], "update-ref", "refs/tags/v0.3.0", evil)
    git(cache, "fetch", "-q", "origin", "+refs/tags/v0.3.0:refs/tags/v0.3.0")
    assert job(tenv).returncode == 0
    assert brief(tenv) == original
    assert evil not in brief(tenv)


def test_old_stamp_cannot_authorize_prompt_code(tenv):
    (tenv["home"] / "pjmuller-skills.version").write_text("v0.3.0 2026-01-01\n")
    tenv["prompt"].write_text("no marker\n")
    commit(tenv["setup"], "prompt")
    result = job(tenv)
    assert result.returncode == 0 and "DELEGATE" not in result.stdout
    assert not (tenv["home"] / "pjmuller-skills/template-sync.md").exists()


@pytest.mark.parametrize("unsigned", [False, True])
def test_release_helper_only_pushes_verified_tags(env, tmp_path, unsigned):
    repo = env["repo"]
    scripts = repo / "skills/t3-manage-thread/scripts"
    scripts.mkdir(parents=True)
    for name, source in [("skills-refresh", env["script"]), ("release", SCRIPT.with_name("release"))]:
        (scripts / name).write_text(source.read_text())
        (scripts / name).chmod(0o755)
    commit(repo, "release tools")
    git(repo, "branch", "-M", "main")
    remote = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "config", "user.name", "Release Test")
    git(repo, "config", "user.email", "release@example.test")
    git(repo, "config", "user.signingkey", str(env["key"]))
    if unsigned:
        git(repo, "tag", "v0.3.0")
    result = subprocess.run(["bash", str(scripts / "release"), "v0.3.0"],
                            env=env["env"], text=True, capture_output=True)
    assert result.returncode == (1 if unsigned else 0), result.stderr
    tags = subprocess.check_output(["git", "-C", str(remote), "tag"]).decode().splitlines()
    assert ("v0.3.0" in tags) is not unsigned


# --- consumer DX: health, local edits, git ownership, removed commands ---

def test_unhealthy_scheduler_keeps_open_every_run_even_quiet(env, tmp_path):
    broken = tmp_path / "relay-broken"
    broken.touch()
    sched = env["home"] / "skills/t3-schedule/scripts"
    sched.mkdir(parents=True)
    (sched / "install").write_text(f'#!/usr/bin/env bash\n[[ -e {broken} ]] && {{ echo "t3-relay not ready: see relay.md" >&2; exit 1; }}\n'
                                   'echo "  obsolete webhook relay host task-1: delete_scheduled_task it, settle its thread (relay.md)"\n')
    (sched / "install").chmod(0o755)
    for _ in range(2):  # the applying run and the next "up to date" run
        out = run(env, "--job", "--quiet").stdout.splitlines()
        assert out[-1].startswith("thread: KEEP OPEN") and "ACTION NEEDED:" in out
        assert any("cannot fire: t3-relay not ready" in line for line in out[-4:])
    broken.unlink()
    out = run(env, "--job", "--quiet").stdout.splitlines()
    assert out[-1].startswith("thread: KEEP OPEN") and "obsolete webhook relay host task-1" in out[-2]
    (sched / "install").write_text("#!/usr/bin/env bash\necho ok\n")
    assert run(env, "--job", "--quiet").stdout.splitlines()[-1].startswith("thread: SETTLE")
    manual = run(env)  # manual runs report the same block
    assert manual.returncode == 0 and "ACTION NEEDED" not in manual.stdout


def test_local_edit_blocks_activation_extra_files_do_not(env):
    assert run(env).returncode == 10  # v0.2.0 recorded
    live = env["home"] / "skills/demo"
    (live / ".venv").mkdir()
    (live / ".venv/pyvenv.cfg").write_text("generated\n")
    release(env["repo"], "v0.3.0", "3")
    (live / "SKILL.md").write_text("demo 2, my tweak\n")
    blocked = run(env)
    assert blocked.returncode == 1 and "local edits" in blocked.stderr and "demo: SKILL.md" in blocked.stderr
    assert stamp(env) == "v0.2.0" and (live / "SKILL.md").read_text() == "demo 2, my tweak\n"
    (env["home"] / "pjmuller-skills/manifest/demo").unlink()  # the documented way to discard
    assert run(env).returncode == 10 and stamp(env) == "v0.3.0"


def setup_repo(tmp_path, env, unpushed=False):
    """~/.agents/skills symlinked into a setup repo that tracks ai/skills, with a pushed upstream."""
    gcfg = tmp_path / "gitconfig"
    gcfg.write_text("[user]\n\tname = t\n\temail = t@t\n[commit]\n\tgpgSign = false\n")
    env["env"].update(GIT_CONFIG_GLOBAL=str(gcfg))
    remote, setup = tmp_path / "remote.git", tmp_path / "setup"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    (setup / "ai/skills/demo").mkdir(parents=True)
    (setup / "ai/skills/demo/SKILL.md").write_text("demo 1\n")
    (setup / "notes.md").write_text("mine\n")
    g = lambda *a: subprocess.run(["git", "-C", str(setup), *a], check=True, capture_output=True, text=True,
                                  env={**os.environ, "GIT_CONFIG_GLOBAL": str(gcfg)}).stdout
    g("init", "-q", "-b", "main"); g("add", "-A"); g("commit", "-qm", "setup")
    g("remote", "add", "origin", str(remote)); g("push", "-qu", "origin", "main")
    if unpushed:
        (setup / "notes.md").write_text("mine, committed\n"); g("commit", "-qam", "local")
    (setup / "notes.md").write_text("mine, dirty\n")
    home = tmp_path / "linked-home"
    home.mkdir()
    (home / "skills").symlink_to(setup / "ai/skills")
    env["env"].update(SKILLS_REFRESH_HOME=str(home))
    return g


def test_refresh_commits_and_pushes_only_managed_paths(env, tmp_path):
    g = setup_repo(tmp_path, env)
    result = run(env, "--job")
    assert result.returncode == 10 and "pushed" in result.stdout and "ACTION NEEDED" not in result.stdout
    assert g("show", "--name-only", "--format=%s", "HEAD").split() == \
        ["skills-refresh:", "pjmuller/skills", "v0.2.0", "ai/skills/demo/SKILL.md", "ai/skills/demo/scripts/install"]
    assert g("status", "--porcelain").strip() == "M notes.md"
    assert g("rev-parse", "HEAD") == g("rev-parse", "origin/main")


def test_publish_failures_are_reported_and_retried_every_run(env, tmp_path):
    g = setup_repo(tmp_path, env)
    g("config", "push.default", "matching")
    g("checkout", "-qb", "private"); g("commit", "-qam", "private work"); g("push", "-q", "origin", "private")
    (tmp_path / "setup/notes.md").write_text("private, unpushed\n"); g("commit", "-qam", "private 2")
    g("checkout", "-q", "main")
    lock = tmp_path / "setup/.git/index.lock"
    lock.touch()  # another git process holds the index
    out = run(env, "--job", "--quiet").stdout
    assert "automatic commit failed" in out and out.splitlines()[-1].startswith("thread: KEEP OPEN")
    lock.unlink()
    remote = tmp_path / "remote.git"
    remote.rename(tmp_path / "away.git")  # push fails
    out = run(env, "--job", "--quiet").stdout  # up to date: retries the commit, push fails
    assert "committed" in out and "push failed" in out and out.splitlines()[-1].startswith("thread: KEEP OPEN")
    assert "push failed" in run(env, "--job", "--quiet").stdout  # still reported the next day
    (tmp_path / "away.git").rename(remote)
    out = run(env, "--job", "--quiet").stdout
    assert "pushed" in out and out.splitlines()[-1].startswith("thread: SETTLE")
    # push.default=matching would also have published the other branch's unpushed commit
    assert g("rev-parse", "origin/private") != g("rev-parse", "private")
    g("fetch", "-q"); assert g("rev-parse", "origin/private") != g("rev-parse", "private")


def test_refresh_never_pushes_the_users_unpushed_commits(env, tmp_path):
    g = setup_repo(tmp_path, env, unpushed=True)
    out = run(env, "--job", "--quiet").stdout.splitlines()
    assert out[-1].startswith("thread: KEEP OPEN") and "1 commit(s) of yours there are unpushed too" in out[-2]
    assert g("rev-list", "--count", "origin/main..HEAD").strip() == "2"


def test_removed_command_still_used_by_the_user_is_listed(env, tmp_path):
    old = env["repo"] / "skills/demo/scripts/t3-old-cmd"
    old.write_text("#!/bin/sh\n")
    old.chmod(0o755)
    release(env["repo"], "v0.3.0", "3")
    assert run(env, SKILLS_REFRESH_TAG="v0.3.0").returncode == 10
    old.unlink()
    release(env["repo"], "v0.4.0", "4")
    setup = tmp_path / "setup"
    (setup / "ai/skills/mine").mkdir(parents=True)
    (setup / "ai/AGENTS.md").write_text("me\nping with `t3-old-cmd --id x`\n")
    (setup / "ai/skills/mine/SKILL.md").write_text("calls t3-old-cmd\nt3-old-cmd-v2 is fine\n")
    git(setup, "init", "-q")
    git(setup, "add", "-A")
    env["env"].update(SKILLS_REFRESH_PROMPT=str(setup / "ai/AGENTS.md"))
    result = run(env)
    assert result.returncode == 10 and "removed commands: t3-old-cmd" in result.stdout
    block = result.stdout.split("ACTION NEEDED:")[1]
    assert f"{(setup / 'ai/AGENTS.md').resolve()}:2" in block and "ai/skills/mine/SKILL.md:1" in block
    assert block.count("t3-old-cmd") == 2


def test_template_hint_rationale_and_one_merge_per_release(tenv):
    tenv["prompt"].write_text(f"me\n<!-- template: pjmuller/skills@{tenv['old']} -->\n")
    commit(tenv["setup"], "prompt")
    manual = run(tenv)
    assert manual.returncode == 10 and "Manual runs never merge it" in manual.stdout
    assert job(tenv).stdout.splitlines()[-1].startswith("thread: DELEGATE")
    assert "Why each change was made: CHANGELOG entries newer than v0.2.0" in brief(tenv)
    second = job(tenv).stdout
    assert "not starting a second merge" in second and "DELEGATE" not in second


def test_publish_skips_user_files_and_reports_unresolvable_upstream(env, tmp_path):
    g = setup_repo(tmp_path, env)
    run(env, "--job")
    (tmp_path / "setup/ai/skills/demo/personal.txt").write_text("mine\n")
    assert run(env, "--job", "--quiet").stdout.splitlines()[-1].startswith("thread: SETTLE")  # up to date
    assert "personal.txt" not in g("ls-tree", "-r", "--name-only", "origin/main")
    assert g("status", "--porcelain", "--", "ai/skills").strip() == "?? ai/skills/demo/personal.txt"
    g("config", "branch.main.merge", "refs/heads/gone")  # configured, never fetched
    release(env["repo"], "v0.3.0", "3")
    out = run(env, "--job", "--quiet").stdout
    assert "is not fetched or does not exist" in out and out.splitlines()[-1].startswith("thread: KEEP OPEN")
