"""Offline checks for the configurable read facade; no Google requests."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


@pytest.fixture
def facade(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'readonly.py'
    spec = importlib.util.spec_from_file_location('readonly_test', source)
    module = importlib.util.module_from_spec(spec)
    module.WORKSPACE_CONFIG = {
        'expected_email': 'operator@example.org',
        'config_dir': tmp_path / 'credentials',
        'scopes': ['openid', 'scope:read'],
    }
    spec.loader.exec_module(module)
    return module


def client_config(facade):
    facade.CONFIG_DIR.mkdir()
    facade.CLIENT_PATH.write_text(json.dumps({'installed': {'client_id': 'client'}}))


def cached(facade, monkeypatch, **overrides):
    client_config(facade)
    facade.TOKEN_PATH.write_text('{}')
    values = dict(scopes=facade.SCOPES, client_id='client', refresh_token='offline',
                  expired=False, valid=True, token='access')
    values.update(overrides)
    creds = SimpleNamespace(**values)
    monkeypatch.setattr(facade.Credentials, 'from_authorized_user_file', lambda _: creds)
    monkeypatch.setattr(facade, '_email_for_token', lambda _: facade.EXPECTED_EMAIL)
    return creds


def test_account_scopes_client_and_offline_cache_rejected(facade, monkeypatch):
    creds = cached(facade, monkeypatch)
    assert facade._credentials() is creds
    for name, wrong, fragment in [('scopes', [], 'scopes'), ('client_id', 'other', 'client changed'),
                                  ('refresh_token', None, 'offline-capable')]:
        original = getattr(creds, name)
        setattr(creds, name, wrong)
        with pytest.raises(RuntimeError, match=fragment):
            facade._credentials()
        setattr(creds, name, original)
    monkeypatch.setattr(facade, '_email_for_token', lambda _: 'other@example.org')
    with pytest.raises(RuntimeError, match='expected operator@example.org'):
        facade._credentials()


def test_no_implicit_consent(facade, monkeypatch):
    client_config(facade)
    monkeypatch.setattr(facade.InstalledAppFlow, 'from_client_secrets_file',
                        lambda *_: pytest.fail('implicit consent'))
    with pytest.raises(RuntimeError, match='run auth explicitly'):
        facade._credentials()


def test_explicit_auth_checks_grants_and_identity_before_persisting(facade, monkeypatch):
    client_config(facade)
    creds = SimpleNamespace(refresh_token='offline', token='access', to_json=lambda: '{}')
    options = {}
    def consent(**kwargs):
        options.update(kwargs)
        return creds
    monkeypatch.setattr(facade.InstalledAppFlow, 'from_client_secrets_file',
                        lambda *_: SimpleNamespace(run_local_server=consent))
    monkeypatch.setattr(facade, '_granted_scopes_for_token', lambda _: set())
    with pytest.raises(RuntimeError, match='every required'):
        facade._credentials(allow_auth=True)
    assert not facade.TOKEN_PATH.exists()
    monkeypatch.setattr(facade, '_granted_scopes_for_token', lambda _: set(facade.SCOPES))
    monkeypatch.setattr(facade, '_email_for_token', lambda _: 'wrong@example.org')
    with pytest.raises(RuntimeError, match='expected'):
        facade._credentials(allow_auth=True)
    assert not facade.TOKEN_PATH.exists()
    monkeypatch.setattr(facade, '_email_for_token', lambda _: facade.EXPECTED_EMAIL)
    assert facade._credentials(allow_auth=True) is creds
    assert options['login_hint'] == facade.EXPECTED_EMAIL
    assert options['access_type'] == 'offline'
    assert facade.TOKEN_PATH.stat().st_mode & 0o777 == 0o600


def test_exports_and_output_safety(facade, tmp_path):
    assert facade._extract_id('https://docs.google.com/document/d/example_file_123/edit') == 'example_file_123'
    args = facade._parser().parse_args(['doc-read', 'example_file_123', '-o', 'result.md', '--force'])
    assert args.output == 'result.md' and args.force
    output = tmp_path / 'result.md'
    facade._write_document(output, 'first', False)
    with pytest.raises(RuntimeError, match='output exists'):
        facade._write_document(output, 'second', False)
    assert output.read_text() == 'first'
    facade._write_document(output, 'second', True)
    assert output.read_text() == 'second'
    alias = tmp_path / 'alias.md'
    alias.symlink_to(output)
    with pytest.raises(OSError):
        facade._write_document(alias, 'unsafe', True)
    assert output.read_text() == 'second'


def test_paginated_drive_and_sheet_contract(facade, monkeypatch):
    requests = []
    def request(req):
        requests.append(req)
        if req.url.path.endswith('/files'):
            page = req.url.params.get('pageToken')
            return httpx.Response(200, json={'files': [{'id': 'second' if page else 'first'}],
                                            **({} if page else {'nextPageToken': 'next'})})
        return httpx.Response(200, json={'range': 'Tab!A1', 'values': [['value']]})
    monkeypatch.setattr(facade, '_api_client', lambda: httpx.Client(transport=httpx.MockTransport(request)))
    assert facade._drive_list('root', 2) == [{'id': 'first'}, {'id': 'second'}]
    assert requests[1].url.params['pageToken'] == 'next'
    assert requests[1].url.params['pageSize'] == '1'
    assert facade._sheet_read('example_file_123', 'Tab!A1')['values'] == [['value']]
    assert requests[-1].url.params['valueRenderOption'] == 'FORMATTED_VALUE'
