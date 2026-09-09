import argparse
import json
import os
import plistlib
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import local_timezone
import topup

HERE = Path(__file__).parent


def test_system_timezone_dst_and_banner(monkeypatch):
    monkeypatch.setenv('TZ', 'America/New_York')
    zone = local_timezone.system_timezone()
    assert datetime(2026, 1, 1, tzinfo=zone).utcoffset().total_seconds() == -18000
    assert datetime(2026, 7, 1, tzinfo=zone).utcoffset().total_seconds() == -14400
    import limited
    monkeypatch.setattr(limited, 'TZ', zone)
    message = datetime(2026, 9, 9, 8, tzinfo=zone)
    assert limited.parse_reset('monthly spend limit (Pro) resets 3pm (Europe/London)', message).hour == 15
    assert limited.parse_reset('resets 3pm', message).utcoffset().total_seconds() == -14400


def test_topup_migration_and_idempotence(tmp_path, monkeypatch):
    monkeypatch.setattr(topup, 'PLIST', tmp_path / (topup.LABEL + '.plist'))
    old = tmp_path / (topup.LEGACY_LABEL + '.plist')
    old.write_text('legacy')
    active = {topup.LEGACY_LABEL}
    def launchctl(*args):
        label = args[1].split('/')[-1]
        if args[0] == 'print':
            return SimpleNamespace(returncode=0 if label in active else 1)
        if args[0] == 'bootout':
            active.discard(label)
        if args[0] == 'bootstrap':
            active.add(plistlib.loads(Path(args[2]).read_bytes())['Label'])
        return SimpleNamespace(returncode=0, stderr='')
    monkeypatch.setattr(topup, 'launchctl', launchctl)
    args = argparse.Namespace(interval=600, dry_run=False)
    assert topup.cmd_install(args) == 0
    assert topup.cmd_install(args) == 0
    assert active == {topup.LABEL}
    assert not old.exists()
    assert ' topup run' in plistlib.loads(topup.PLIST.read_bytes())['ProgramArguments'][-1]


def test_topup_preview_never_waits_or_launches(tmp_path, monkeypatch):
    monkeypatch.setattr(topup, 'LOG', tmp_path / 'log')
    monkeypatch.setattr(topup, 't3_up', lambda: True)
    monkeypatch.setattr(topup, 'limits_rows', lambda: [{'instance_id':'codex', 'window':'session', 'resets_in_seconds':20}])
    monkeypatch.setattr(topup.time, 'sleep', lambda _: (_ for _ in ()).throw(AssertionError('sleep')))
    assert topup.main(['run', '--dry-run', '--ignore-hours', '--json']) == 0


def test_start_friendly_profile_and_settle(tmp_path):
    config = tmp_path / 'userdata/settings.json'
    config.parent.mkdir()
    config.write_text(json.dumps({'providerInstances': {
        'claudeAgent_team': {'driver':'claudeAgent', 'enabled':True, 'displayName':'Team'},
        'claudeAgent_disabled': {'driver':'claudeAgent', 'enabled':False},
    }}))
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name, body in {
        't3-spawn-thread': 'echo "Provider: claudeAgent_team · Model: claude-haiku-4-5 · Thinking: low"\necho "Thread ID: child-id"',
        't3-settle-thread': 'echo "$*" > "$T3CODE_HOME/settled"\necho "Settled at: 2026-09-09T12:00:00Z"',
    }.items():
        path = bin_dir / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)
    env = dict(os.environ, T3CODE_HOME=str(tmp_path), PATH=f'{bin_dir}:' + os.environ['PATH'])
    result = subprocess.run([str(HERE/'t3-usage-windows'), 'start', '--profile', 'TEAM', '--json'], env=env, text=True, check=False, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['ok']
    assert (tmp_path/'settled').read_text().strip() == '--wait 300 child-id'
    result = subprocess.run([str(HERE/'t3-usage-windows'), 'start', '--profile', 'disabled', '--dry-run', '--json'], env=env, text=True, check=False, capture_output=True)
    assert result.returncode == 1
    assert not json.loads(result.stdout)['ok']


def test_empty_profile_parts_never_expand_scope(monkeypatch):
    import profiles
    monkeypatch.setattr(profiles, 'settings', lambda: {'providerInstances': {}})
    assert profiles.matching('work,', {'work', 'other'}) == {'work'}
    assert profiles.matching(', ,', {'work', 'other'}) == set()
