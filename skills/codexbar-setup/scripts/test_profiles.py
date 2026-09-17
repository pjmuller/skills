import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest

loader = importlib.machinery.SourceFileLoader('codexbar_profiles', str(Path(__file__).with_name('codexbar-profiles')))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


def credential(expiry, token='test-token', refresh_expiry=9999999999999):
    return json.dumps({'claudeAiOauth': {'expiresAt': expiry, 'refreshToken': token,
                      'accessToken': 'fake', 'refreshTokenExpiresAt': refresh_expiry}})


@pytest.mark.parametrize('live,stash,expected', [
    (credential(10), credential(20), 'stash->live'),
    (credential(20), credential(10), 'live->stash'),
    ('{}', credential(20), 'stash->live'),
    (credential(20), '{}', 'live->stash'),
    ('{}', '{}', None),
    (credential(10), credential(10), None),
    (credential(10, 'a'), credential(10, 'b'), None),
    (credential(10, refresh_expiry=1), '{}', None),
])
def test_generation_selection(live, stash, expected):
    assert m.direction(live, stash)[0] == expected


def test_sync_rechecks_and_verifies(monkeypatch):
    row = {'home': None, 'slot': 2, 'email': 'test@example.org'}
    monkeypatch.setattr(m, 'verify_mapping', lambda _: None)
    old, new = credential(10), credential(20)
    merged = m.merge_oauth(old, new)
    reads = iter([old, new, old, new, merged])
    writes = []
    monkeypatch.setattr(m, 'read_item', lambda _: next(reads))
    def run(argv, **kwargs):
        writes.append((argv, kwargs))
        return type('Result', (), {'returncode': 0})()
    monkeypatch.setattr(m.subprocess, 'run', run)
    assert m.sync(row, True) == 'SYNC stash->live'
    assert writes[0][0] == ['/usr/bin/security', '-i']
    assert merged.encode().hex() in writes[0][1]['input']
    reads = iter([old, new, credential(30)])
    writes.clear()
    assert m.sync(row, True) == 'changed during read; deferred'
    assert writes == []


def test_unreadable_never_written(monkeypatch):
    def fail(_):
        raise RuntimeError('unreadable')
    monkeypatch.setattr(m, 'verify_mapping', lambda _: None)
    monkeypatch.setattr(m, 'read_item', fail)
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **kw: pytest.fail('unexpected write'))
    with pytest.raises(RuntimeError):
        m.sync({'home': None, 'slot': 1, 'email': 'test@example.org'}, True)


def test_config_duplicate_slot_rejected(tmp_path):
    path = tmp_path / 'profiles.json'
    path.write_text(json.dumps({'profiles': [
        {'name': 'one', 'home': None, 'slot': 1, 'email': 'one@example.org'},
        {'name': 'two', 'home': '/tmp/two', 'slot': 1, 'email': 'two@example.org'},
    ]}))
    with pytest.raises(ValueError, match='unique positive slot'):
        m.profiles(path)


def test_jobs_schedule_absolute_paths_and_remove_only_own(tmp_path, monkeypatch):
    monkeypatch.setattr(m.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(m, 'launch_uv', lambda: '/opt/bin/uv')
    calls = []
    monkeypatch.setattr(m.subprocess, 'run', lambda argv, **kw: calls.append(argv))
    config = tmp_path / 'config.json'
    m.jobs(config)
    paths = list((tmp_path / 'Library/LaunchAgents').glob('*.plist'))
    assert len(paths) == 2
    sync = m.plistlib.loads(next(p for p in paths if '.sync.' in p.name).read_bytes())
    assert sync['StartInterval'] == 60
    assert sync['ProgramArguments'][0] == '/opt/bin/uv'
    assert sync['ProgramArguments'][-2:] == ['sync', '--apply']
    unrelated = paths[0].with_name('unrelated.plist')
    unrelated.write_text('keep')
    m.jobs(config, remove=True)
    assert unrelated.exists() and not any(p.exists() for p in paths)


def test_launch_uv_skips_inactive_shim(tmp_path, monkeypatch):
    shim, actual = tmp_path / 'shims', tmp_path / 'bin'
    for directory in [shim, actual]:
        directory.mkdir()
        (directory / 'uv').write_text('fake')
        (directory / 'uv').chmod(0o755)
    monkeypatch.setattr(m.os, 'get_exec_path', lambda: [str(shim), str(actual)])
    def probe(argv, **kwargs):
        assert kwargs['env']['PATH'] == '/usr/bin:/bin:/usr/sbin:/sbin'
        return type('Result', (), {'returncode': 1 if 'shims' in argv[0] else 0})()
    monkeypatch.setattr(m.subprocess, 'run', probe)
    assert m.launch_uv() == str(actual / 'uv')


def test_merge_preserves_target_fields_without_copying_source_secrets():
    target = json.dumps({'claudeAiOauth': {}, 'mcpOAuth': {'target': 'keep'}})
    source = json.loads(credential(20)); source['mcpOAuth'] = {'source': 'never-copy'}
    merged = json.loads(m.merge_oauth(target, json.dumps(source)))
    assert merged['mcpOAuth'] == {'target': 'keep'}
    assert merged['claudeAiOauth']['expiresAt'] == 20
    with pytest.raises(RuntimeError):
        m.merge_oauth('unparseable', credential(20))


def test_mapping_identity_and_fallback_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(m.Path, 'home', lambda: tmp_path)
    row = {'home': None, 'slot': 2, 'email': 'work@example.org'}
    identity = tmp_path / '.claude.json'
    identity.write_text(json.dumps({'oauthAccount': {'emailAddress': 'wrong@example.org'}}))
    with pytest.raises(RuntimeError, match='email differs'):
        m.verify_mapping(row)
    identity.write_text(json.dumps({'oauthAccount': {'emailAddress': row['email']}}))
    m.verify_mapping(row)
    fallback = tmp_path / '.claude-swap-backup/credentials/.creds-2-work@example.org.enc'
    fallback.parent.mkdir(parents=True); fallback.write_text('fake')
    with pytest.raises(RuntimeError, match='fallback .enc'):
        m.verify_mapping(row)


def test_slotless_check_reads_live(monkeypatch):
    monkeypatch.setattr(m, 'read_item', lambda _: '{}')
    with pytest.raises(RuntimeError, match='native credential invalid'):
        m.sync({'home': None})


def test_oversized_write_never_uses_argv(monkeypatch):
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **kw: pytest.fail('unexpected write'))
    with pytest.raises(RuntimeError, match='safe stdin size'):
        m.write_item(('test-service', 'test-account'), 'x' * 3000)
