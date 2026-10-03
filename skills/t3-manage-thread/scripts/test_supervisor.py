"""Probe and launch behavior with fake OS managers; never touches real services."""
import os
import subprocess
from pathlib import Path

LIB = Path(__file__).parent / 'lib/t3-common.sh'


def run(tmp_path, platform='Linux', ready=True, launch=True, action='t3_supervisor'):
    for name, script in {
        'uname': f'echo {platform}',
        'systemctl': 'exit ' + ('0' if ready else '1'),
        'systemd-run': 'exit ' + ('0' if launch else '1'),
        'launchctl': f'case "$1" in print) exit {0 if ready else 1};; *) exit {0 if launch else 1};; esac',
    }.items():
        file = tmp_path / name
        file.write_text('#!/bin/sh\n' + script + '\n')
        file.chmod(0o755)
    return subprocess.run(['bash', '-c', f'source "{LIB}"; {action}'],
                          env={**os.environ, 'PATH': f'{tmp_path}:' + os.environ['PATH']},
                          text=True, capture_output=True)


def test_linux_ignores_launchctl_and_uses_live_manager(tmp_path):
    result = run(tmp_path)
    assert result.returncode == 0 and result.stdout == 'systemd'


def test_binary_without_user_manager_is_not_ready(tmp_path):
    assert run(tmp_path, ready=False).returncode != 0


def test_mac_checks_gui_domain(tmp_path):
    result = run(tmp_path, platform='Darwin')
    assert result.returncode == 0 and result.stdout == 'launchd'
    assert run(tmp_path, platform='Darwin', ready=False).returncode != 0


def test_refuses_unsupervised_fallback(tmp_path):
    result = run(tmp_path, ready=False, action='t3_supervise test /tmp/test.log /bin/true')
    assert result.returncode != 0
    assert result.stdout == ''
    assert 'No usable worker supervisor' in result.stderr


def test_failed_systemd_launch_does_not_report_success(tmp_path):
    result = run(tmp_path, launch=False, action='t3_supervise test /tmp/test.log /bin/true')
    assert result.returncode != 0 and result.stdout == ''


def test_failed_launchd_launch_does_not_report_success(tmp_path):
    result = run(tmp_path, platform='Darwin', launch=False,
                 action='t3_supervise test /tmp/test.log /bin/true')
    assert result.returncode != 0 and result.stdout == ''
