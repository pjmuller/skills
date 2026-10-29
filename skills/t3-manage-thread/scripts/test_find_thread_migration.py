"""t3-find-thread moved into this skill: old installs keep working, and a rollback keeps their links."""
import os
from pathlib import Path
import shutil
import subprocess

SKILLS = Path(__file__).resolve().parents[2]
COMMANDS = ('t3-find-thread', 't3-open-thread')


def setup(tmp_path):
    home = tmp_path / 'home'
    skills = home / '.agents/skills'
    bin_dir = home / '.local/bin'
    bin_dir.mkdir(parents=True)
    for name in ('t3-manage-thread', 't3-find-thread'):
        shutil.copytree(SKILLS / name, skills / name, ignore=shutil.ignore_patterns('__pycache__', '.*cache'))
    env = {k: v for k, v in os.environ.items() if k != 'T3_MANAGE_BIN'}
    # Only this fake install on PATH (never the machine's own t3-relay), plus a real uv (not a mise shim).
    uv = Path(os.environ.get('UV') or shutil.which('uv') or 'uv').resolve().parent  # uv run sets UV
    env.update(HOME=str(home), T3_MANAGE_BIN=str(bin_dir), PATH=f"{bin_dir}:{uv}:/usr/bin:/bin")
    return skills, bin_dir, env


def install(skills, env, *args):
    return subprocess.run(['bash', str(skills / 't3-manage-thread/scripts/install'), *args], env=env,
                          text=True, capture_output=True)


def test_links_into_an_old_copy_stay_until_relink(tmp_path):
    skills, bin_dir, env = setup(tmp_path)
    old = skills / 't3-find-thread/scripts'
    for name in COMMANDS:
        (bin_dir / name).symlink_to(old / name)
    result = install(skills, env)
    assert result.returncode == 0, result.stderr
    # Kept: the stub forwards, and a rollback's old installers still own these links.
    assert all((bin_dir / n).resolve() == (old / n).resolve() for n in COMMANDS)
    assert 'KEEP' in result.stdout
    assert install(skills, env, '--relink').returncode == 0
    assert all((bin_dir / n).resolve() == (skills / 't3-manage-thread/scripts' / n).resolve() for n in COMMANDS)


def test_dangling_old_links_are_replaced(tmp_path):
    skills, bin_dir, env = setup(tmp_path)
    for name in COMMANDS:
        (bin_dir / name).symlink_to(tmp_path / 'gone/t3-find-thread/scripts' / name)
    assert install(skills, env).returncode == 0
    assert all((bin_dir / n).resolve() == (skills / 't3-manage-thread/scripts' / n).resolve() for n in COMMANDS)


def test_stub_forwards_to_manage_installed_in_another_scope(tmp_path):
    skills, bin_dir, env = setup(tmp_path)
    assert install(skills, env).returncode == 0  # global management puts t3-relay on PATH
    project = tmp_path / 'project/.agents/skills/t3-find-thread'
    shutil.move(skills / 't3-find-thread', project)
    for name in COMMANDS:
        result = subprocess.run([str(project / 'scripts' / name), '--help'], env=env, text=True,
                                capture_output=True)
        assert result.returncode == 0 and result.stdout.startswith(f'usage: {name}'), result.stderr
    check = subprocess.run(['bash', str(project / 'scripts/install'), '--check'], env=env, text=True,
                           capture_output=True)
    assert check.returncode == 0 and check.stdout.count('ok ') == 2, check.stdout


def test_stub_check_fails_without_manage(tmp_path):
    skills, bin_dir, env = setup(tmp_path)
    shutil.rmtree(skills / 't3-manage-thread')
    stub = skills / 't3-find-thread/scripts'
    assert subprocess.run(['bash', str(stub / 'install')], env=env).returncode == 0  # never blocks a refresh
    check = subprocess.run(['bash', str(stub / 'install'), '--check'], env=env, text=True, capture_output=True)
    assert check.returncode == 1 and 'MISSING t3-find-thread' in check.stdout
