import importlib.machinery
import importlib.util
import json
import time
from datetime import datetime, timezone
from pathlib import Path

loader = importlib.machinery.SourceFileLoader('claude_usage', str(Path(__file__).with_name('codexbar-claude-usage')))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

NOW = datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc)
ROWS = [  # `t3-limits --json --claude-only`
    {'account': 'Claude Default', 'instance_id': 'claudeAgent', 'window': 'session', 'used_percent': 0.0,
     'resets_at': '2026-10-19T23:40:00.123456Z', 'fetched_at': '2026-10-19T18:47:18.6Z'},
    {'account': 'Claude Default', 'instance_id': 'claudeAgent', 'window': 'weekly', 'used_percent': 4.0,
     'resets_at': '2026-10-24T15:00:00Z'},
    {'account': 'Claude Work', 'instance_id': 'claudeAgent_work', 'window': 'Fable only', 'used_percent': 91.0,
     'resets_at': None},
    {'account': 'Claude Work', 'instance_id': 'claudeAgent_work', 'window': 'weekly', 'used_percent': None},
    {'account': 'Claude Down', 'instance_id': 'claudeAgent_down', 'window': None, 'error': 'HTTP 429'},
]


def test_schema_v1_slots_follow_t3_order_and_default_is_active():
    listed = m.account_list(ROWS, {'claudeAgent': '', 'claudeAgent_work': '/nonexistent/work',
                                   'claudeAgent_down': '/nonexistent/down'}, NOW)
    assert listed['schemaVersion'] == 1 and listed['activeAccountNumber'] == 1
    first, work, down = listed['accounts']
    assert (first['number'], first['active'], first['usageStatus']) == (1, True, 'ok')
    assert first['usage']['fiveHour'] == {'pct': 0.0, 'resetsAt': '2026-10-19T23:40:00Z'}
    assert first['usageFetchedAt'] == '2026-10-19T18:47:18Z'
    assert work['usage'] is None and work['usageStatus'] == 'unavailable'  # scoped cap alone is no reading
    assert (down['number'], down['active'], down['usage'], down['email']) == (3, False, None, '')


def test_only_list_and_version_are_served(capsys):
    assert m.main(['--switch-to', '2', '--json']) == 2
    assert json.loads(capsys.readouterr().out)['error']['type'] == 'Unsupported'
    assert m.main(['--version']) == 0
    assert capsys.readouterr().out.split()[-1] == '1'


def test_slow_t3_limits_serves_the_last_answer_and_keeps_running(tmp_path, monkeypatch, capsys):
    last = tmp_path / 'last.json'
    last.write_text('{"schemaVersion": 1, "activeAccountNumber": null, "accounts": []}\n')
    finished = tmp_path / 'finished'
    slow = tmp_path / 't3-limits'
    slow.write_text(f'#!/bin/sh\n/bin/sleep 1\ntouch {finished}\necho []\n')
    slow.chmod(0o755)
    monkeypatch.setattr(m, 'LAST_GOOD', last)
    monkeypatch.setattr(m, 'DEADLINE', 0.2)
    monkeypatch.setattr(m, 'PATH_PREFIX', [str(tmp_path)])
    assert m.main(['--list', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['accounts'] == []
    assert not finished.exists()  # answered before t3-limits finished...
    time.sleep(1.5)
    assert finished.exists()  # ...which was not killed, so its stores still update
