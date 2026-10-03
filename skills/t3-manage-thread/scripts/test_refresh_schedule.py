"""Legacy cron migration waits for successful native timer registration."""
import os
import subprocess
from pathlib import Path

REFRESH = Path(__file__).parent / 'skills-refresh'


def invoke(tmp_path, success):
    cron = tmp_path / 'cron'
    cron.write_text('30 6 * * * skills-refresh # skills-refresh\n0 1 * * * other-job\n')
    for name, body in {
        't3-schedule': 'exit ' + ('0' if success else '1'),
        'crontab': 'if [ "$1" = -l ]; then cat "$CRON_FILE"; else cat > "$CRON_FILE"; fi',
    }.items():
        script = tmp_path / name
        script.write_text('#!/bin/sh\n' + body + '\n')
        script.chmod(0o755)
    result = subprocess.run(['bash', str(REFRESH), 'schedule', '--project', str(tmp_path)],
                            env={**os.environ, 'PATH': f'{tmp_path}:' + os.environ['PATH'],
                                 'CRON_FILE': str(cron), 'SKILLS_REFRESH_HOME': str(tmp_path / 'state')},
                            capture_output=True, text=True)
    return result, cron.read_text()


def test_migration_preserves_unrelated_jobs(tmp_path):
    result, cron = invoke(tmp_path, True)
    assert result.returncode == 0, result.stderr
    assert cron == '0 1 * * * other-job\n'


def test_failed_timer_keeps_old_cron(tmp_path):
    result, cron = invoke(tmp_path, False)
    assert result.returncode != 0
    assert '# skills-refresh' in cron and 'other-job' in cron
