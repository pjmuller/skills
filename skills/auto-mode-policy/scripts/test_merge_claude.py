import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from merge_claude import BASELINE, combine, merged  # noqa: E402


def test_defaults_first_dedup_and_order():
    auto, deny = combine([{'autoMode': {'allow': ['a', '$defaults', 'b']}, 'permissions': {'deny': ['x']}},
                          {'autoMode': {'allow': ['b', 'c'], 'environment': ['e']}, 'permissions': {'deny': ['x', 'y']}}])
    assert auto == {'allow': ['$defaults', 'a', 'b', 'c'], 'environment': ['$defaults', 'e']}
    assert deny == ['x', 'y']


def test_merge_replaces_rule_lists_keeps_everything_else():
    settings = {'theme': 'dark', 'autoMode': {'allow': ['stale'], 'classifyAllShell': True},
                'permissions': {'allow': ['Bash(ls *)'], 'deny': ['mine']}}
    out = merged(settings, {'allow': ['$defaults', 'new']}, ['mine', 'x'])
    assert out == {'theme': 'dark', 'autoMode': {'classifyAllShell': True, 'allow': ['$defaults', 'new']},
                   'permissions': {'allow': ['Bash(ls *)'], 'deny': ['mine', 'x']}}
    assert merged(out, {'allow': ['$defaults', 'new']}, ['x']) == out


def test_apply_is_idempotent(tmp_path):
    (tmp_path / 'settings.json').write_text('{"theme": "dark"}')
    overlay = tmp_path / 'overlay.json'
    overlay.write_text(json.dumps({'autoMode': {'environment': ['Source control: GitHub owner example-org']}}))
    run = lambda *a: subprocess.run([sys.executable, str(Path(__file__).parent / 'merge_claude.py'), str(overlay),
                                     '--home', str(tmp_path), *a], capture_output=True, text=True, check=True).stdout
    assert 'SET' in run('--apply')
    assert 'KEEP' in run('--apply')
    data = json.loads((tmp_path / 'settings.json').read_text())
    assert data['theme'] == 'dark' and data['autoMode']['environment'][0] == '$defaults'
    assert len(data['autoMode']['allow']) == len(json.loads(BASELINE.read_text())['autoMode']['allow']) + 1
