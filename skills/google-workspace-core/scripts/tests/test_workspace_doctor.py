"""`gws.py doctor`: offline by default, secret-safe, one actionable next step."""

import io
import json
from urllib import error

import pytest

from gws_core import load_config
from gws_core.doctor import inspect, run_doctor

from workspace_testkit import ACCOUNT, SCOPES

SECRET = "refresh-secret-value"


def write_token(path, *, scopes=SCOPES, client_id="client-1", mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "token": "old", "refresh_token": SECRET, "client_id": client_id,
        "client_secret": "client-secret-value", "scopes": scopes,
        "token_uri": "https://oauth2.googleapis.com/token"}), encoding="utf-8")
    path.chmod(mode)
    return path


@pytest.fixture
def client_json(config):
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.client_path.write_text(json.dumps({"installed": {
        "client_id": "client-1", "client_secret": "client-secret-value"}}), encoding="utf-8")
    config.client_path.chmod(0o600)
    return config.client_path


def test_no_token_is_unhealthy_with_a_mint_next_step(config, client_json):
    facts = inspect(config)
    assert facts["healthy"] is False and facts["token"]["source"] == "none"
    assert "auth mint" in facts["next"]


def test_healthy_offline_state_reports_no_next_step(config, client_json):
    write_token(config.token_path)
    facts = inspect(config)
    assert facts["healthy"] is True and facts["next"] is None
    assert facts["client"]["client_id"].startswith("sha256:")


def test_json_output_never_contains_a_secret(config, client_json, capsys):
    write_token(config.token_path)
    assert run_doctor(config, as_json=True) == 0
    printed = capsys.readouterr().out
    assert SECRET not in printed and "client-secret-value" not in printed


def test_permissions_scopes_and_client_drift_each_get_their_own_step(config, client_json):
    write_token(config.token_path, mode=0o644)
    assert "chmod 600" in inspect(config)["next"]
    write_token(config.token_path, scopes=["https://www.googleapis.com/auth/drive"])
    assert inspect(config)["next"].endswith("--force")
    write_token(config.token_path, client_id="other-client")
    facts = inspect(config)
    assert facts["token"]["client_match"] is False and facts["healthy"] is False
    assert "differs" in facts["next"]


def test_a_broken_client_source_is_never_healthy(config, client_json, monkeypatch):
    write_token(config.token_path)
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_ID", "half-a-pair")
    facts = inspect(config)
    assert facts["client"]["source"] == "BROKEN" and facts["healthy"] is False
    assert "only part of the OAuth client" in facts["next"]


def test_legacy_cloud_and_offline_sources_are_named(write_config, tmp_path, monkeypatch):
    legacy = tmp_path / "scripts" / ".google_token.json"
    write_token(legacy)
    config = load_config(write_config(legacy_token="scripts/.google_token.json"))
    assert inspect(config)["token"]["source"] == "legacy"

    shared = tmp_path / "offline.txt"
    shared.write_text("shared\n", encoding="utf-8")
    shared.chmod(0o600)
    config = load_config(write_config(offline_token_file=str(shared)))
    assert inspect(config)["token"]["source"] == "offline file"

    monkeypatch.setenv("GWS_REFRESH_TOKEN", SECRET)
    config = load_config(write_config(cloud_token_env=True))
    facts = inspect(config)
    assert facts["token"]["source"] == "cloud env" and "GWS_CLIENT_ID" in facts["next"]


def live(monkeypatch, *, identity=None, refresh_error=None):
    def urlopen(request_object, timeout=30):
        url = request_object.full_url
        if "token" in url and refresh_error:
            raise refresh_error
        payload = {"access_token": "fresh"} if "oauth2.googleapis.com/token" in url else identity
        return io.BytesIO(json.dumps(payload).encode())

    class Context(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def wrapped(request_object, timeout=30):
        return Context(urlopen(request_object, timeout).read())

    monkeypatch.setattr("gws_core.doctor.request.urlopen", wrapped)


def test_live_confirms_the_account(config, client_json, monkeypatch):
    write_token(config.token_path)
    live(monkeypatch, identity={"email": ACCOUNT})
    facts = inspect(config, live=True)
    assert facts["live"]["account_match"] is True and facts["healthy"] is True


def test_live_mismatch_revocation_and_outage_have_distinct_recoveries(config, client_json, monkeypatch):
    write_token(config.token_path)
    live(monkeypatch, identity={"email": "someone-else@example.com"})
    facts = inspect(config, live=True)
    assert facts["healthy"] is False and "--force" in facts["next"]

    revoked = error.HTTPError("https://oauth2.googleapis.com/token", 400, "Bad", {},
                              io.BytesIO(json.dumps({"error": "invalid_grant"}).encode()))
    live(monkeypatch, refresh_error=revoked)
    facts = inspect(config, live=True)
    assert facts["live"]["error_code"] == "invalid_grant" and "revoked" in facts["next"]

    live(monkeypatch, refresh_error=error.URLError("offline"))
    facts = inspect(config, live=True)
    assert "retry" in facts["live"]["error"] and facts["healthy"] is False
