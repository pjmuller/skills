"""Credential sources, account verification and the refusal to authenticate implicitly."""

import json
import os
import subprocess
import sys

import pytest
import requests

from gws_core import AuthError, credentials, load_config
from gws_core.auth import client_credentials, export_env, export_token, mint

from workspace_testkit import ACCOUNT, SCOPES, SCRIPTS


def write_token(config, *, account_scopes=None, refresh_token="refresh-1", client_id="client-1"):
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.token_path.write_text(json.dumps({
        "token": "old-access", "refresh_token": refresh_token, "client_id": client_id,
        "client_secret": "secret-1", "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": account_scopes if account_scopes is not None else SCOPES,
        "expiry": "2020-01-01T00:00:00Z",
    }), encoding="utf-8")
    config.token_path.chmod(0o600)
    return config.token_path


@pytest.fixture
def google(monkeypatch):
    """Minimal Google stand-in: refresh, identity and tokeninfo."""
    state = {"email": ACCOUNT, "refreshes": 0, "granted": set(SCOPES)}

    class Response:
        def __init__(self, payload, status=200):
            self._payload = payload
            self.status_code = status

        def json(self):
            return self._payload

    def post(url, **kw):
        state["refreshes"] += 1
        if state.get("refresh_status"):
            return Response({"error": "invalid_grant", "leaked": "s3cr3t"}, state["refresh_status"])
        return Response({"access_token": "fresh-access", "expires_in": 3600})

    def get(url, **kw):
        if "userinfo" in url:
            return Response({"email": state["email"]})
        if "profile" in url:
            return Response({"emailAddress": state["email"]})
        return Response({"scope": " ".join(state["granted"])})

    def request(method, url, **kw):
        # tokeninfo is a POST in the auth layer but answers with the granted scopes.
        return post(url, **kw) if url.endswith("/token") else get(url, **kw)

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr("httpx.get", lambda *a, **kw: pytest.fail("auth must not need httpx"))
    monkeypatch.setattr("httpx.post", lambda *a, **kw: pytest.fail("auth must not need httpx"))
    return state


def test_missing_token_never_starts_consent(config, google, monkeypatch):
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
                        lambda *a, **kw: pytest.fail("data access must never open consent"))
    with pytest.raises(AuthError, match="no offline token"):
        credentials(config)


def test_wrong_account_is_refused_and_nothing_is_written(config, google):
    path = write_token(config)
    before = path.read_text()
    google["email"] = "someone-else@example.com"
    with pytest.raises(AuthError, match="authorized as someone-else@example.com"):
        credentials(config)
    assert path.read_text() == before


def test_scope_superset_is_fine_and_a_gap_is_refused(config, google):
    write_token(config, account_scopes=[*SCOPES, "https://www.googleapis.com/auth/calendar"])
    assert credentials(config).token == "fresh-access"
    write_token(config, account_scopes=["https://www.googleapis.com/auth/drive"])
    with pytest.raises(AuthError, match="missing required scopes"):
        credentials(config)


def test_refresh_externalizes_a_legacy_cache_without_touching_it(write_config, google, tmp_path):
    legacy = tmp_path / "scripts" / ".google_token.json"
    legacy.parent.mkdir(parents=True)
    config = load_config(write_config(legacy_token="scripts/.google_token.json"))
    legacy.write_text(json.dumps({
        "token": "old", "refresh_token": "legacy-refresh", "client_id": "client-1",
        "client_secret": "secret-1", "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": SCOPES, "expiry": "2020-01-01T00:00:00Z"}), encoding="utf-8")
    before = legacy.read_text()
    assert credentials(config).token == "fresh-access"
    assert legacy.read_text() == before
    assert json.loads(config.token_path.read_text())["refresh_token"] == "legacy-refresh"
    assert config.token_path.stat().st_mode & 0o777 == 0o600


def test_cloud_triplet_is_opt_in_and_all_or_nothing(write_config, google, monkeypatch):
    monkeypatch.setenv("GWS_REFRESH_TOKEN", "cloud-refresh")
    not_opted_in = load_config(write_config())
    with pytest.raises(AuthError, match="no offline token"):
        credentials(not_opted_in)  # a stray env var never redirects a file-based wrapper
    opted_in = load_config(write_config(cloud_token_env=True))
    with pytest.raises(AuthError, match="set all of"):
        credentials(opted_in)
    monkeypatch.setenv("GWS_CLIENT_ID", "cloud-client")
    monkeypatch.setenv("GWS_CLIENT_SECRET", "cloud-secret")
    assert credentials(load_config(write_config(cloud_token_env=True))).token == "fresh-access"
    assert not opted_in.token_path.exists()  # cloud credentials are never persisted


def test_offline_token_file_is_imported_once(write_config, google, tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_ID", "client-1")
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_SECRET", "secret-1")
    shared = tmp_path / "offline.txt"
    shared.write_text("shared-refresh\n", encoding="utf-8")
    config = load_config(write_config(offline_token_file=str(shared)))
    assert credentials(config).token == "fresh-access"
    assert json.loads(config.token_path.read_text())["refresh_token"] == "shared-refresh"


def test_client_sources_are_ordered_and_never_half_mixed(write_config, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_WORKSPACE_CLIENT_ID=from-env-file\n"
                        "GOOGLE_WORKSPACE_CLIENT_SECRET=secret-file\n", encoding="utf-8")
    config = load_config(write_config(client_env=[".env"]))
    assert client_credentials(config).client_id == "from-env-file"
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_ID", "from-environment")
    with pytest.raises(AuthError, match="only part of the OAuth client"):
        client_credentials(config)
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_SECRET", "secret-env")
    assert client_credentials(config).client_id == "from-environment"


def test_client_errors_name_paths_and_never_echo_a_secret(config):
    with pytest.raises(AuthError) as missing:
        client_credentials(config)
    assert str(config.client_path) in str(missing.value)
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.client_path.write_text(json.dumps({"installed": {"client_secret": "s3cr3t-value"}}),
                                  encoding="utf-8")
    with pytest.raises(AuthError) as broken:
        client_credentials(config)
    assert "s3cr3t-value" not in str(broken.value)


def test_symlinked_credential_paths_are_refused(config, google, tmp_path):
    write_token(config)
    real = config.token_path.rename(tmp_path / "real-token.json")
    config.token_path.symlink_to(real)
    with pytest.raises(AuthError, match="symlink"):
        credentials(config)


def test_rejected_consent_preserves_the_existing_token(config, google, monkeypatch):
    path = write_token(config)
    before = path.read_text()
    google["email"] = ACCOUNT

    class Flow:
        @classmethod
        def from_client_config(cls, *a, **kw):
            return cls()

        def run_local_server(self, **kw):
            raise RuntimeError("user closed the consent screen")

    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_ID", "client-1")
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_SECRET", "secret-1")
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow", Flow)
    with pytest.raises(AuthError, match="exists; pass --force"):
        mint(config)
    with pytest.raises(RuntimeError):
        mint(config, force=True)
    assert path.read_text() == before


def test_mint_refuses_a_wrong_account_or_missing_scope_before_saving(config, google, monkeypatch):
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_ID", "client-1")
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_SECRET", "secret-1")

    class Credentials:
        token = "new-access"
        refresh_token = "new-refresh"

        def to_json(self):
            return json.dumps({"refresh_token": "new-refresh"})

    class Flow:
        @classmethod
        def from_client_config(cls, *a, **kw):
            return cls()

        def run_local_server(self, **kw):
            return Credentials()

    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow", Flow)
    google["email"] = "someone-else@example.com"
    with pytest.raises(AuthError, match="authorized as"):
        mint(config)
    assert not config.token_path.exists()
    google["email"] = ACCOUNT
    google["granted"] = {"https://www.googleapis.com/auth/drive"}
    with pytest.raises(AuthError, match="scopes not granted"):
        mint(config)
    assert not config.token_path.exists()
    google["granted"] = set(config.mint_scopes)
    assert mint(config)["account"] == ACCOUNT
    assert config.token_path.stat().st_mode & 0o777 == 0o600


def test_a_configured_client_that_disagrees_with_the_token_is_refused(config, google, monkeypatch):
    write_token(config, client_id="client-1")
    assert credentials(config).token == "fresh-access"  # no client configured: the token refreshes
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_ID", "other-client")
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_SECRET", "other-secret")
    with pytest.raises(AuthError, match="differs from the cached token"):
        credentials(config)
    monkeypatch.delenv("GOOGLE_WORKSPACE_CLIENT_SECRET")
    with pytest.raises(AuthError, match="only part of the OAuth client"):
        credentials(config)  # a broken client source is never silently ignored


def test_refresh_failures_never_echo_the_response_body(config, google):
    write_token(config)
    google["refresh_status"] = 400
    with pytest.raises(AuthError) as exc:
        credentials(config)
    assert "invalid_grant" in str(exc.value) and "s3cr3t" not in str(exc.value)


def test_network_and_body_failures_never_leak_the_access_token(config, google, monkeypatch):
    """A prepared URL or an untrusted body must never reach a message or a traceback."""
    import traceback

    from gws_core.auth import granted_scopes

    write_token(config)
    sentinel = "ya29.SENTINEL-ACCESS-TOKEN"

    def exploding(method, url, **kw):
        raise requests.ConnectionError(f"failed to connect to {url}?access_token={sentinel}")

    monkeypatch.setattr(requests, "request", exploding)
    with pytest.raises(AuthError) as exc:
        granted_scopes(sentinel)
    rendered = "".join(traceback.format_exception(exc.value))
    assert sentinel not in str(exc.value) and sentinel not in rendered
    assert "oauth2.googleapis.com/tokeninfo" in str(exc.value)

    class Garbage:
        status_code = 200

        def json(self):
            raise ValueError(f"not JSON: access_token={sentinel}")

    monkeypatch.setattr(requests, "request", lambda *a, **kw: Garbage())
    with pytest.raises(AuthError) as exc:
        granted_scopes(sentinel)
    rendered = "".join(traceback.format_exception(exc.value))
    assert sentinel not in str(exc.value) and sentinel not in rendered


def test_refresh_failures_stay_sanitized_when_the_token_endpoint_is_unreachable(config, monkeypatch):
    import traceback

    from google.oauth2.credentials import Credentials

    from gws_core.auth import refresh

    secret = "1//SENTINEL-REFRESH-TOKEN"
    credentials = Credentials(None, refresh_token=secret, client_id="c", client_secret="s",
                              token_uri="https://oauth2.googleapis.com/token")

    def exploding(url, **kw):
        raise requests.ConnectionError(f"POST {url} data={kw.get('data')!r}")

    monkeypatch.setattr(requests, "post", exploding)
    with pytest.raises(AuthError) as exc:
        refresh(credentials)
    rendered = "".join(traceback.format_exception(exc.value))
    assert secret not in str(exc.value) and secret not in rendered


def test_the_tokeninfo_call_keeps_the_token_out_of_the_query_string(config, monkeypatch):
    from gws_core.auth import granted_scopes

    seen = {}

    class Response:
        status_code = 200

        def json(self):
            return {"scope": "https://www.googleapis.com/auth/drive"}

    def record(method, url, **kw):
        seen.update(method=method, url=url, **kw)
        return Response()

    monkeypatch.setattr(requests, "request", record)
    assert granted_scopes("ya29.token") == {"https://www.googleapis.com/auth/drive"}
    assert seen["method"] == "POST" and "?" not in seen["url"]
    assert seen["data"] == {"access_token": "ya29.token"}


def test_auth_layer_needs_neither_httpx_nor_the_cli():
    """DA's Sheets caller runs with the auth dependencies only; importing must not pull in more."""
    program = """
import builtins, sys
real = builtins.__import__
def blocked(name, *a, **kw):
    if name.split('.')[0] == 'httpx':
        raise ImportError('httpx is not installed in this caller')
    return real(name, *a, **kw)
builtins.__import__ = blocked
from gws_core import credentials, load_config
assert 'httpx' not in sys.modules
assert 'gws_core.cli' not in sys.modules and 'gws_core.session' not in sys.modules
"""
    environment = {**os.environ, "PYTHONPATH": str(SCRIPTS)}
    subprocess.run([sys.executable, "-c", program], check=True, env=environment)


def test_exports_are_explicit_and_owner_only(config, google, tmp_path):
    write_token(config)
    assert export_env(config)["GWS_REFRESH_TOKEN"] == "refresh-1"
    destination = export_token(config, tmp_path / "out" / "offline.txt")
    assert destination.read_text().strip() == "refresh-1"
    assert destination.stat().st_mode & 0o777 == 0o600
