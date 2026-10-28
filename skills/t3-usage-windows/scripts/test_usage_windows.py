import argparse
import json
import os
import plistlib
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import local_timezone
import reset_credit
import topup

HERE = Path(__file__).parent


def test_reset_selects_earliest_available_credit():
    snapshot = {'rateLimitResetCredits': {'credits': [
        {'id': 'later', 'status': 'available', 'expiresAt': 20},
        {'id': 'used', 'status': 'consumed', 'expiresAt': 1},
        {'id': 'first', 'status': 'available', 'expiresAt': 10},
    ]}}
    assert [row['id'] for row in reset_credit.available_credits(snapshot)] == ['first', 'later']


def test_reset_inventory_renders_markdown(monkeypatch):
    monkeypatch.setattr(reset_credit, 'datetime', SimpleNamespace(
        fromtimestamp=lambda value: SimpleNamespace(
            astimezone=lambda: SimpleNamespace(
                isoformat=lambda: f'time-{value}',
                strftime=lambda _: f'local-{value}',
            )
        )
    ))
    inventory = reset_credit.credit_inventory({'accountId': 'account', 'rateLimitResetCredits': {
        'availableCount': 1,
        'credits': [{'id': 'one', 'title': 'Full reset', 'status': 'available', 'expiresAt': 10}],
    }})
    assert inventory['resets'][0]['expires_at'] == 'time-10'
    assert reset_credit.format_markdown(inventory) == (
        '### Codex banked resets\n\n**1 available.**\n\n'
        '| Reset | Expires |\n|---|---|\n| Full reset | local-10 |'
    )


def test_system_timezone_dst(monkeypatch):
    monkeypatch.setenv('TZ', 'America/New_York')
    zone = local_timezone.system_timezone()
    assert datetime(2026, 1, 1, tzinfo=zone).utcoffset().total_seconds() == -18000
    assert datetime(2026, 7, 1, tzinfo=zone).utcoffset().total_seconds() == -14400


def test_topup_install_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(topup, 'PLIST', tmp_path / (topup.LABEL + '.plist'))
    active = set()
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
    assert ' topup run' in plistlib.loads(topup.PLIST.read_bytes())['ProgramArguments'][-1]


def test_topup_preview_never_waits_or_launches(tmp_path, monkeypatch):
    monkeypatch.setattr(topup, 'LOG', tmp_path / 'log')
    monkeypatch.setattr(topup, 't3_up', lambda: True)
    monkeypatch.setattr(topup, 'limits_rows', lambda: [{'instance_id':'codex', 'window':'session', 'resets_in_seconds':20}])
    monkeypatch.setattr(topup.time, 'sleep', lambda _: (_ for _ in ()).throw(AssertionError('sleep')))
    assert topup.main(['run', '--dry-run', '--ignore-hours', '--json']) == 0


def test_topup_morning_start_fires_once_per_day(tmp_path, monkeypatch):
    class Clock(datetime):
        now_value = datetime(2026, 9, 12, 5, 3)  # a Saturday
        @classmethod
        def now(cls, tz=None):
            return cls.now_value.replace(tzinfo=tz)
    monkeypatch.setattr(topup, 'datetime', Clock)
    monkeypatch.setattr(topup, 'LOG', tmp_path / 'log')
    monkeypatch.setattr(topup, 'STATE', tmp_path / 'state.json')
    monkeypatch.setattr(topup, 't3_up', lambda: True)
    monkeypatch.setattr(topup, 'limits_rows', lambda: [
        {'instance_id': 'claude', 'window': 'session', 'resets_in_seconds': 9000},
        {'instance_id': 'codex', 'window': 'weekly', 'resets_in_seconds': 9000}])
    calls = []
    monkeypatch.setattr(topup.subprocess, 'run', lambda cmd, **kw: calls.append(cmd[1:]) or SimpleNamespace(returncode=0, stdout='', stderr=''))
    assert topup.main(['run']) == 0
    assert calls == [['start', '--profile', 'codex']]
    Clock.now_value = datetime(2026, 9, 12, 20, 50)
    assert topup.main(['run']) == 0 and len(calls) == 1  # same day: no refire
    Clock.now_value = datetime(2026, 9, 13, 5, 1)
    assert topup.main(['run']) == 0 and len(calls) == 2  # next day


def test_topup_failed_account_does_not_repeat_successful_morning_launches(tmp_path, monkeypatch):
    monkeypatch.setattr(topup, 'LOG', tmp_path / 'log')
    monkeypatch.setattr(topup, 'STATE', tmp_path / 'state.json')
    monkeypatch.setattr(topup, 't3_up', lambda: True)
    monkeypatch.setattr(topup, 'datetime', SimpleNamespace(
        now=lambda tz=None: datetime(2026, 9, 12, 5, 3, tzinfo=tz)))
    monkeypatch.setattr(topup, 'limits_rows', lambda: [
        {'instance_id': instance, 'window': 'weekly', 'resets_in_seconds': 9000}
        for instance in ['codex_exhausted', 'codex_ready', 'codex_other']])
    calls = []

    def launch(command, **kwargs):
        instance = command[-1]
        calls.append(instance)
        return SimpleNamespace(returncode=1 if instance == 'codex_exhausted' else 0,
                               stdout='', stderr='')

    monkeypatch.setattr(topup.subprocess, 'run', launch)
    assert topup.main(['run', '--ignore-hours']) == 1
    assert calls == ['codex_exhausted', 'codex_ready', 'codex_other']
    assert set(topup.load_started()) == {'codex_ready', 'codex_other'}
    calls.clear()
    assert topup.main(['run', '--ignore-hours']) == 1
    assert calls == ['codex_exhausted']


def test_start_relays_one_cheap_turn_per_profile(tmp_path):
    config = tmp_path / 'userdata/settings.json'
    config.parent.mkdir()
    config.write_text(json.dumps({'providerInstances': {
        'claudeAgent_team': {'driver':'claudeAgent', 'enabled':True, 'displayName':'Team'},
        'claudeAgent_disabled': {'driver':'claudeAgent', 'enabled':False},
        'codex_team': {'driver':'codex', 'enabled':True, 'displayName':'Codex Team'},
    }}))
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    relay = bin_dir / 't3-relay'
    relay.write_text('#!/bin/sh\nprintf "%s|" "$@" >> "$T3CODE_HOME/relayed"; echo >> "$T3CODE_HOME/relayed"\n')
    relay.chmod(0o755)
    env = dict(os.environ, T3CODE_HOME=str(tmp_path), PATH=f'{bin_dir}:' + os.environ['PATH'])
    run = lambda *a: subprocess.run([str(HERE/'t3-usage-windows'), 'start', *a], env=env, text=True, check=False, capture_output=True)
    result = run('--profile', 'TEAM', '--json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['ok']
    calls = (tmp_path/'relayed').read_text().splitlines()
    assert len(calls) == 2  # Team matches both enabled profiles by display name
    claude = next(c.split('|') for c in calls if '|claudeAgent_team|' in c)
    assert claude[:2] == ['launch', '--project']
    assert claude[claude.index('--model') + 1] == 'haiku'
    assert claude[claude.index('--effort') + 1] == 'low'
    assert claude[claude.index('--title') + 1] == 'Warm-up — Team'
    prompt = claude[claude.index('--') + 1]
    assert prompt == 'Reply only: ok.'
    assert claude[claude.index('--settle-after-run') + 1] == '90'
    result = run('--profile', 'disabled', '--dry-run', '--json')
    assert result.returncode == 1
    assert not json.loads(result.stdout)['ok']
    result = run('--profile', 'codex_team', '--dry-run')
    assert result.returncode == 0, result.stderr
    assert '--instance codex_team --model luna --effort low' in result.stdout
    assert len((tmp_path/'relayed').read_text().splitlines()) == 2  # dry-run never relays


def test_empty_profile_parts_never_expand_scope(monkeypatch):
    import profiles
    monkeypatch.setattr(profiles, 'settings', lambda: {'providerInstances': {}})
    assert profiles.matching('work,', {'work', 'other'}) == {'work'}
    assert profiles.matching(', ,', {'work', 'other'}) == set()

