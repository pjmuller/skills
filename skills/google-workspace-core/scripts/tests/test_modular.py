"""Offline contracts for legacy client APIs and account-safe authentication.

Run: uv run --no-project --with pytest --with httpx --with python-dotenv
     --with google-auth --with google-auth-oauthlib --with requests pytest <this-file>
"""
import base64
from email import message_from_bytes
from pathlib import Path
import sys
import types
from unittest.mock import Mock

import httpx
import pytest

CORE = Path(__file__).resolve().parents[1] / "modular"


def load(name, monkeypatch, **initial):
    namespace = {"__file__": str(CORE / name), "__name__": "fixture_module", **initial}
    exec(compile((CORE / name).read_text(), str(CORE / name), "exec"), namespace)
    return namespace


@pytest.fixture
def clients(monkeypatch):
    base = types.ModuleType("base")
    base.BaseClient = object
    auth = types.ModuleType("auth")
    auth.EXPECTED_EMAIL = "team@example.org"
    monkeypatch.setitem(sys.modules, "base", base)
    monkeypatch.setitem(sys.modules, "auth", auth)
    return lambda name: load(name, monkeypatch)


def response(payload):
    return httpx.Response(200, json=payload, request=httpx.Request("GET", "https://example.org"))


@pytest.mark.parametrize("family", ["gmail_rich.py", "gmail_drafts.py"])
def test_me_and_draft_positional_contract(clients, family):
    client = clients(family)["GmailClient"]()
    client.http = Mock()
    client.http.get.return_value = response({"emailAddress": "team@example.org"})
    assert client.me() == {"emailAddress": "team@example.org"}
    client.http.get.return_value = response({"threadId": "thread-1", "payload": {"headers": [{"name": "Message-ID", "value": "<original@example.org>"}]}})
    client.http.post.return_value = response({"id": "draft-1"})
    fourth = "copy@example.org" if family == "gmail_rich.py" else "original-id"
    assert client.create_draft("recipient@example.org", "Subject", "Body", fourth) == {"id": "draft-1"}
    payload = client.http.post.call_args.kwargs["json"]["message"]
    msg = message_from_bytes(base64.urlsafe_b64decode(payload["raw"]))
    assert msg["From"] == "team@example.org"
    if family == "gmail_rich.py":
        assert msg["Cc"] == fourth
        assert "threadId" not in payload
    else:
        assert msg["Cc"] is None
        assert msg["In-Reply-To"] == "<original@example.org>"
        assert payload["threadId"] == "thread-1"


@pytest.mark.parametrize("family", ["drive.py", "drive_named_upload.py"])
def test_upload_positional_contract_and_failures(clients, family, tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("local fixture")
    client = clients(family)["DriveClient"]()
    client.http = Mock()
    client.http.post.return_value = response({"id": "new-file"})
    if family == "drive.py":
        result = client.upload(source, "destination.txt", "folder")
        assert b'destination.txt' in client.http.post.call_args.kwargs["content"]
        assert client.http.post.call_args.kwargs["headers"]["Content-Type"].startswith("multipart/related;")
    else:
        result = client.upload("destination.txt", str(source), "folder", "text/plain")
        assert client.http.post.call_args.kwargs["files"]["file"] == ("destination.txt", b"local fixture", "text/plain")
    assert result == {"id": "new-file"}
    client.http.get.return_value = httpx.Response(403, request=httpx.Request("GET", "https://example.org"))
    with pytest.raises(httpx.HTTPStatusError):
        client.metadata("forbidden")


def test_sheets_raw_and_tables(clients):
    client = clients("sheets.py")["SheetsClient"]()
    client.http = Mock()
    client.http.put.return_value = response({"updatedCells": 1})
    client.update("sheet", "A1", [["001"]], raw=True)
    assert client.http.put.call_args.kwargs["params"] == {"valueInputOption": "RAW"}
    client.http.get.return_value = response({"sheets": [{"properties": {"sheetId": 7, "title": "Tab"}, "tables": [{"tableId": "t1", "name": "Rows", "range": {"sheetId": 7, "endRowIndex": 2, "endColumnIndex": 1}, "columnProperties": [{"columnIndex": 0, "columnName": "Name"}]}]}]})
    assert client.tables("sheet") == [{"id": "t1", "name": "Rows", "range": "'Tab'!A1:A2", "columns": ["Name"]}]


@pytest.fixture
def auth_module(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_SECRET", "fixture-secret")
    wrapper = tmp_path / "repo/.agents/skills/workspace/scripts/auth.py"
    wrapper.parent.mkdir(parents=True)
    config = {"expected_email": "team@example.org", "config_dir": str(tmp_path / "config"), "scopes": ["https://www.googleapis.com/auth/gmail.modify"], "legacy_token": ".google_token.json"}
    ns = load("auth.py", monkeypatch, __file__=str(wrapper), WORKSPACE_CONFIG=config)
    ns["_client_credentials"] = lambda: ("fixture-client", "fixture-secret")
    return ns


def test_missing_cache_never_prompts(auth_module, monkeypatch):
    flow = Mock()
    monkeypatch.setattr(auth_module["InstalledAppFlow"], "from_client_config", flow)
    with pytest.raises(SystemExit, match="run auth explicitly"):
        auth_module["get_credentials"]()
    flow.assert_not_called()


def test_wrong_cached_account_is_refused_without_writing(auth_module, monkeypatch):
    legacy = auth_module["_LEGACY_TOKEN"]
    legacy.write_text("placeholder")
    creds = Mock(valid=True, client_id="fixture-client", refresh_token="fixture-refresh", scopes=auth_module["SCOPES"])
    monkeypatch.setattr(auth_module["Credentials"], "from_authorized_user_file", lambda *a: creds)
    auth_module["_email_for_token"] = lambda token: "other@example.org"
    with pytest.raises(SystemExit, match="expected team@example.org"):
        auth_module["get_credentials"]()
    assert not auth_module["TOKEN_PATH"].exists()
    assert legacy.read_text() == "placeholder"


def test_rejected_consent_preserves_existing_cache(auth_module, monkeypatch):
    token = auth_module["TOKEN_PATH"]
    token.parent.mkdir()
    token.write_text("previous-token")
    creds = Mock(token="new-access", refresh_token="new-refresh")
    flow = Mock()
    flow.run_local_server.return_value = creds
    monkeypatch.setattr(auth_module["InstalledAppFlow"], "from_client_config", lambda *a: flow)
    auth_module["_email_for_token"] = lambda token: "wrong@example.org"
    with pytest.raises(SystemExit, match="nothing saved"):
        auth_module["authorize"](True)
    assert token.read_text() == "previous-token"


def test_refresh_externalizes_only_verified_credentials(auth_module, monkeypatch):
    legacy = auth_module["_LEGACY_TOKEN"]
    legacy.write_text("unchanged-legacy")
    creds = Mock(valid=False, client_id="fixture-client", refresh_token="fixture-refresh", scopes=auth_module["SCOPES"])
    creds.to_json.return_value = '{"fixture":true}'
    monkeypatch.setattr(auth_module["Credentials"], "from_authorized_user_file", lambda *a: creds)
    auth_module["_email_for_token"] = lambda token: "team@example.org"
    assert auth_module["get_credentials"]() is creds
    assert legacy.read_text() == "unchanged-legacy"
    assert auth_module["TOKEN_PATH"].read_text() == '{"fixture":true}\n'
    assert auth_module["TOKEN_PATH"].stat().st_mode & 0o777 == 0o600


def test_missing_scopes_refused_before_use(auth_module, monkeypatch):
    auth_module["_LEGACY_TOKEN"].write_text("placeholder")
    creds = Mock(valid=True, client_id="fixture-client", refresh_token="fixture-refresh", scopes=[])
    monkeypatch.setattr(auth_module["Credentials"], "from_authorized_user_file", lambda *a: creds)
    with pytest.raises(SystemExit, match="missing required scopes"):
        auth_module["get_credentials"]()
    creds.refresh.assert_not_called()


def test_offline_fallback_and_export(auth_module, monkeypatch, tmp_path):
    auth_module["WORKSPACE_CONFIG"]["offline_token_file"] = str(tmp_path / "offline.txt")
    auth_module["OFFLINE_TOKEN_FILE"] = tmp_path / "offline.txt"
    auth_module["OFFLINE_TOKEN_FILE"].write_text("fixture-refresh")
    creds = Mock(token="fixture-access", refresh_token="fixture-refresh")
    creds.to_json.return_value = '{"fixture":true}'
    monkeypatch.setitem(auth_module, "Credentials", Mock(return_value=creds))
    auth_module["_email_for_token"] = lambda token: "team@example.org"
    assert auth_module["get_credentials"]() is creds
    creds.refresh.assert_called_once()
    auth_module["get_credentials"] = lambda: creds
    destination = tmp_path / "export" / "token.txt"
    assert auth_module["export_offline_token"](destination) == destination
    assert destination.read_text() == "fixture-refresh\n"
    assert destination.stat().st_mode & 0o777 == 0o600


def test_auth_import_needs_no_httpx(tmp_path):
    """Legacy auth-only callers declare requests but do not declare httpx."""
    import subprocess
    script = '''
import builtins
from pathlib import Path
original_import = builtins.__import__
def without_httpx(name, *args, **kwargs):
    if name == "httpx" or name.startswith("httpx."):
        raise ImportError("httpx deliberately unavailable")
    return original_import(name, *args, **kwargs)
builtins.__import__ = without_httpx
source = Path(SOURCE)
namespace = {"__file__": str(Path(WRAPPER).resolve()), "__name__": "isolated_auth",
             "WORKSPACE_CONFIG": {"expected_email": "team@example.org",
                                  "config_dir": CONFIG, "scopes": []}}
exec(compile(source.read_text(), str(source), "exec"), namespace)
assert callable(namespace["get_credentials"])
'''
    script = "SOURCE = " + repr(str(CORE / "auth.py")) + "\nWRAPPER = " + repr(str(tmp_path / "repo/.agents/skills/w/scripts/auth.py")) + "\nCONFIG = " + repr(str(tmp_path / "config")) + "\n" + script
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
