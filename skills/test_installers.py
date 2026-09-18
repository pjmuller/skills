"""Command installers cannot silently steal another checkout's links."""
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

INSTALLERS = [p for p in Path(__file__).parent.glob('*/scripts/install') if 'ln -sfn' in p.read_text()]


@pytest.mark.parametrize('installer', INSTALLERS, ids=lambda p: p.parts[-3])
def test_checkout_guard(installer, tmp_path):
    home = tmp_path / 'home'
    bin_dir = home / '.local/bin'
    bin_dir.mkdir(parents=True)
    # Copy only this installer's scripts: every skill must work independently.
    scripts = tmp_path / 'project/.agents/skills' / installer.parts[-3] / 'scripts'
    shutil.copytree(installer.parent, scripts)
    names = re.search(r'for command_name in (.*); do', installer.read_text())[1].split()
    previous = tmp_path / 'previous' / names[-1]
    previous.parent.mkdir()
    previous.touch()
    (bin_dir / names[-1]).symlink_to(previous)
    env = {k: v for k, v in os.environ.items() if k not in (
        'T3_MANAGE_BIN', 'T3_FIND_BIN', 'T3_SCHEDULE_INSTALL_DIR', 'T3_MAINTENANCE_INSTALL_DIR')}
    env['HOME'] = str(home)

    def run(*args):
        return subprocess.run(['bash', str(scripts / 'install'), *args], env=env,
                              text=True, capture_output=True)

    result = run()
    assert result.returncode == 1
    assert str(previous) in result.stderr and str(scripts) in result.stderr
    assert 'or pass --relink' in result.stderr
    assert sorted(p.name for p in bin_dir.iterdir()) == [names[-1]]
    result = run('--relink')
    assert result.returncode == 0, result.stderr
    assert 'project copy' in result.stderr
    for name in names:
        assert (bin_dir / name).resolve() == (scripts / name).resolve()
    assert run().returncode == 0
    # Readiness may fail without live dependencies, but source must come first.
    assert run('--check').stdout.splitlines()[0] == f'source {scripts.resolve()}'
    # A dead old checkout is safe to replace without an override.
    (bin_dir / names[-1]).unlink()
    (bin_dir / names[-1]).symlink_to(tmp_path / 'gone' / names[-1])
    assert run().returncode == 0
