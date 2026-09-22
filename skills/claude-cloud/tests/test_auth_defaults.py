import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

loader = importlib.machinery.SourceFileLoader('cloud_auth', str(Path(__file__).parents[1] / 'scripts/claude-cloud'))
spec = importlib.util.spec_from_loader(loader.name, loader)
cloud = importlib.util.module_from_spec(spec)
loader.exec_module(cloud)


@pytest.fixture
def profiles(monkeypatch):
    for key in ('CLAUDE_CONFIG_DIR', 'CLAUDE_CLOUD_PROFILE'):
        monkeypatch.delenv(key, raising=False)
    rows = [('default', 'Default', ''), ('other', 'Other', '/tmp/other')]
    monkeypatch.setattr(cloud, 't3_lib', lambda: (None, lambda _: rows, lambda home: 'key:' + home))
    return rows


def test_profile_precedence_and_ambiguity(monkeypatch, profiles):
    with pytest.raises(cloud.Failure, match='2 Claude profiles') as exc:
        cloud.resolve_profile(None)
    assert exc.value.code == 2
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', '/tmp/config')
    assert cloud.resolve_profile(None)[3].endswith('via CLAUDE_CONFIG_DIR')
    monkeypatch.setenv('CLAUDE_CLOUD_PROFILE', 'other')
    assert cloud.resolve_profile(None)[0] == Path('/tmp/other')
    assert cloud.resolve_profile('default')[2] is True
    assert cloud.resolve_profile('default')[3].endswith('via --profile')
    monkeypatch.delenv('CLAUDE_CONFIG_DIR')
    monkeypatch.delenv('CLAUDE_CLOUD_PROFILE')
    profiles.pop()
    assert cloud.resolve_profile(None)[3].endswith('via only profile')


@pytest.mark.parametrize('default', [False, True])
def test_refresh_reloads_once_and_selects_home(monkeypatch, default):
    api = object.__new__(cloud.API)
    api.home, api.default_home, api.refresh_attempted = Path('/tmp/profile'), default, False
    monkeypatch.setattr(cloud.time, 'time', lambda: 1000)
    credentials = iter([('old', 999000), ('new', 2000000), ('new', 1500000)])
    monkeypatch.setattr(api, 'stored_credentials', lambda: next(credentials))
    calls = []
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', '/tmp/wrong')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-only')
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'test-only')
    monkeypatch.setattr(cloud.subprocess, 'run', lambda argv, **kw: calls.append((argv, kw)))
    assert api.credentials() == 'new'
    assert api.credentials() == 'new'
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == ['claude', '-p', 'reply with ok', '--model', 'haiku', '--max-turns', '1']
    assert kwargs['env'].get('CLAUDE_CONFIG_DIR') == (None if default else '/tmp/profile')
    assert 'ANTHROPIC_API_KEY' not in kwargs['env']
    assert 'CLAUDE_CODE_OAUTH_TOKEN' not in kwargs['env']
    assert kwargs['cwd'] != str(Path.cwd())


def test_failed_refresh_keeps_auth_exit(monkeypatch):
    api = object.__new__(cloud.API)
    api.home, api.default_home, api.refresh_attempted = Path('/tmp/profile'), False, False
    monkeypatch.setattr(cloud.time, 'time', lambda: 1000)
    monkeypatch.setattr(api, 'stored_credentials', lambda: ('expired', 999000))
    monkeypatch.setattr(cloud.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(cloud.Failure, match='OAuth expired') as exc:
        api.credentials()
    assert exc.value.code == 3
    assert api.refresh_attempted


def test_create_wait_defaults_and_title(monkeypatch, capsys):
    calls = []
    class API:
        resolved = 'profile: Work via CLAUDE_CLOUD_PROFILE'
        def __init__(self, profile):
            pass
        def environments(self):
            return [{'name': 'Cloud', 'environment_id': 'env_1', 'kind': 'anthropic_cloud'}]
        def call(self, path, body):
            calls.append(body)
            return {'session': {'id': 'cse_test'}}
        def events(self, sid):
            return [{'payload': {'type': 'assistant', 'message': {'content': 'ok'}}}], None
    monkeypatch.setattr(cloud, 'API', API)
    def wait(api, sid, timeout, quiet=False):
        assert capsys.readouterr().out == 'cse_test\nhttps://claude.ai/code/cse_test\n'
        assert quiet
    monkeypatch.setattr(cloud, 'wait', wait)
    monkeypatch.setenv('CLAUDE_CLOUD_REPO', 'example/project')
    monkeypatch.setenv('CLAUDE_CLOUD_BRANCH', 'stable')
    monkeypatch.delenv('CLAUDE_CLOUD_ENV', raising=False)
    monkeypatch.setattr(cloud.sys, 'argv', ['claude-cloud', 'create', '--wait', '--title', 'Check', 'Test'])
    cloud.main()
    assert calls[0]['title'] == 'Check'
    assert calls[0]['config']['sources'][0]['revision'] == 'stable'
    assert capsys.readouterr().out == '### Assistant\n\nok\n\n'


def test_gate_wraps_prompt_and_rejects_short_shas():
    sha = "1eda7a4c11ce37875f9ff64a0d8a2793a9020564"
    text = cloud.gated("Run X.", sha)
    assert text.startswith(f"Dry run, expected {sha}") and "Run X." in text and text.endswith(cloud.GATE_FOOTER)
    follow = cloud.gated("Re-run 6.", sha, "main", follow_up=True)
    assert f"git fetch origin main && git checkout --detach {sha}" in follow
    with pytest.raises(cloud.Failure, match="40-hex"):
        cloud.gated("x", "abc")
