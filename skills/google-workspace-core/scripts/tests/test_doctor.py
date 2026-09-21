"""Secret-safe doctor contracts; every check is offline."""

import importlib.util
import io
import json
import os
from pathlib import Path
import sys

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "doctor.py"
CLIENT_SECRET = "CLIENT_SECRET_SENTINEL"
REFRESH_TOKEN = "REFRESH_TOKEN_SENTINEL"
ACCESS_TOKEN = "ACCESS_TOKEN_SENTINEL"
UNRELATED_SECRET = "UNRELATED_SECRET_SENTINEL"


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def http_failure(doctor, status, payload):
    body = io.BytesIO(json.dumps(payload).encode())
    return doctor.error.HTTPError("https://example.org", status, "fixture", {}, body)


@pytest.fixture
def doctor():
    spec = importlib.util.spec_from_file_location("workspace_doctor_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wrapper(tmp_path, *, interface="modular", client="file-client", token=True):
    scripts = tmp_path / "repo/.agents/skills/example-workspace/scripts"
    scripts.mkdir(parents=True)
    config_dir = tmp_path / "credentials"
    config_dir.mkdir(mode=0o700)
    common = {"expected_email": "team@example.org", "config_dir": str(config_dir)}
    if interface == "REST":
        common.update(required_scopes=["scope:a"], mint_scopes=["scope:a"])
    elif interface == "modular":
        common.update(scopes=["scope:a"], env_file=".env", legacy_token="legacy-token.json")
    else:
        common.update(scopes=["scope:a"])
    config = scripts / ("google_workspace.py" if interface == "readonly" else "workspace_config.py")
    config.write_text(
        "import os\nfrom pathlib import Path\n"
        f"WORKSPACE_CONFIG = {common!r}\n"
        "raise RuntimeError('trailing wrapper code ran')\n"
    )
    (scripts / ("gws_auth.py" if interface == "REST" else "google_workspace.py")).touch(exist_ok=True)
    (config_dir / "client.json").write_text(json.dumps({"installed": {"client_id": client, "client_secret": CLIENT_SECRET}}))
    if token:
        write_token(config_dir / "token.json", client=client)
    return config, scripts, config_dir


def write_token(path, *, client="file-client", scopes=("scope:a",), refresh=REFRESH_TOKEN, mode=0o600):
    path.write_text(json.dumps({"token": ACCESS_TOKEN, "refresh_token": refresh, "client_id": client, "client_secret": CLIENT_SECRET, "token_uri": "https://oauth2.googleapis.com/token", "scopes": list(scopes)}))
    path.chmod(mode)


def emitted(doctor, capsys, config, scripts):
    assert doctor.main([str(config)]) in (0, 1)
    human = capsys.readouterr()
    human_output = human.out + human.err
    for sentinel in (CLIENT_SECRET, REFRESH_TOKEN, ACCESS_TOKEN, UNRELATED_SECRET):
        assert sentinel not in human_output
    assert doctor.main([str(config), "--json"]) in (0, 1)
    output = capsys.readouterr()
    combined = output.out + output.err
    for sentinel in (CLIENT_SECRET, REFRESH_TOKEN, ACCESS_TOKEN, UNRELATED_SECRET):
        assert sentinel not in combined
    return json.loads(output.out)["wrappers"][0]


def test_ast_loader_sources_do_not_run_wrapper_and_partial_env_never_mixes(doctor, tmp_path, monkeypatch):
    config, scripts, config_dir = wrapper(tmp_path)
    env_file = scripts / ".env"
    env_file.write_text(f"GOOGLE_WORKSPACE_CLIENT_ID=file-client\nGOOGLE_WORKSPACE_CLIENT_SECRET={CLIENT_SECRET}\nSERVICE_ACCOUNT_KEY={UNRELATED_SECRET}\n")
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_ID", "environment-client")
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_SECRET", CLIENT_SECRET)
    assert doctor.inspect_wrapper(config, scripts).facts["client"]["source"] == "environment"
    monkeypatch.delenv("GOOGLE_WORKSPACE_CLIENT_SECRET")
    facts = doctor.inspect_wrapper(config, scripts).facts
    assert facts["client"]["source"] == "wrapper .env path"
    env_file.write_text(f"GOOGLE_WORKSPACE_CLIENT_SECRET={CLIENT_SECRET}\nSERVICE_ACCOUNT_KEY={UNRELATED_SECRET}\n")
    assert doctor.inspect_wrapper(config, scripts).facts["client"]["source"] == "external client.json"
    (config_dir / "client.json").unlink()
    facts = doctor.inspect_wrapper(config, scripts).facts
    assert facts["client"]["source"] == "MISSING"
    assert "GOOGLE_WORKSPACE_CLIENT_ID" in facts["client"]["missing_variables"]
    assert "set GOOGLE_WORKSPACE_CLIENT_ID" in facts["next"]
    assert "mise exec --" in facts["next"]


@pytest.mark.parametrize("state", ["healthy", "mismatch", "scopes", "refresh", "mode", "symlink"])
def test_json_redacts_every_token_state(doctor, tmp_path, monkeypatch, capsys, state):
    for name in (*doctor.CLIENT_VARS, *doctor.CLOUD_VARS):
        monkeypatch.delenv(name, raising=False)
    config, scripts, config_dir = wrapper(tmp_path)
    (scripts / ".env").write_text(f"SERVICE_ACCOUNT_KEY={UNRELATED_SECRET}\n")
    monkeypatch.setenv("SERVICE_ACCOUNT_KEY", UNRELATED_SECRET)
    token = config_dir / "token.json"
    if state == "mismatch":
        write_token(token, client="other-client")
    elif state == "scopes":
        write_token(token, scopes=())
    elif state == "refresh":
        write_token(token, refresh="")
    elif state == "mode":
        token.chmod(0o644)
    elif state == "symlink":
        target = tmp_path / "token-target.json"
        token.replace(target)
        token.symlink_to(target)
    report = emitted(doctor, capsys, config, scripts)
    assert report["healthy"] is (state == "healthy")
    if state == "scopes":
        assert report["token"]["missing_scopes"] == ["scope:a"]
    if state == "symlink":
        assert report["token"]["symlink"] is True


def test_rest_cloud_all_or_none_and_no_secret_output(doctor, tmp_path, monkeypatch, capsys):
    config, scripts, _ = wrapper(tmp_path, interface="REST")
    monkeypatch.setenv("GWS_REFRESH_TOKEN", REFRESH_TOKEN)
    report = emitted(doctor, capsys, config, scripts)
    assert report["client"]["source"] == "MISSING"
    assert set(report["client"]["missing_variables"]) == {"GWS_CLIENT_ID", "GWS_CLIENT_SECRET"}
    assert "set all of GWS_REFRESH_TOKEN" in report["next"]


def test_default_is_read_only_offline_and_zero_arg_discovery(doctor, tmp_path, monkeypatch):
    core_script = tmp_path / "repo/skills/google-workspace-core/scripts/doctor.py"
    core_script.parent.mkdir(parents=True)
    config, scripts, config_dir = wrapper(tmp_path)
    before = {path: (path.stat().st_mtime_ns, path.stat().st_mode) for path in (config_dir / "client.json", config_dir / "token.json")}
    monkeypatch.setattr(doctor, "__file__", str(core_script))
    monkeypatch.setattr(doctor.request, "urlopen", lambda *a, **k: pytest.fail("network used"))
    discovered = doctor._discover()
    assert discovered == [(config.resolve(), scripts.resolve())]
    report = doctor.inspect_wrapper(*discovered[0])
    assert report.facts["healthy"] is True
    assert before == {path: (path.stat().st_mtime_ns, path.stat().st_mode) for path in before}


def test_live_refreshes_in_memory_and_checks_identity(doctor, tmp_path, monkeypatch):
    config, scripts, config_dir = wrapper(tmp_path)
    token = config_dir / "token.json"
    before = (token.stat().st_mtime_ns, token.read_bytes())
    seen = []

    def urlopen(req, timeout):
        seen.append(req.full_url)
        return Response({"access_token": ACCESS_TOKEN} if len(seen) == 1 else {"emailAddress": "team@example.org"})

    monkeypatch.setattr(doctor.request, "urlopen", urlopen)
    report = doctor.inspect_wrapper(config, scripts, live=True).facts
    assert report["healthy"] is True and report["live"]["account_match"] is True
    assert seen == [doctor.TOKEN_URI, "https://gmail.googleapis.com/gmail/v1/users/me/profile"]
    assert before == (token.stat().st_mtime_ns, token.read_bytes())


def test_live_mismatch_and_network_failure_have_distinct_recovery(doctor, tmp_path, monkeypatch):
    config, scripts, _ = wrapper(tmp_path)
    responses = iter((Response({"access_token": ACCESS_TOKEN}), Response({"emailAddress": "other@example.org"})))
    monkeypatch.setattr(doctor.request, "urlopen", lambda *a, **k: next(responses))
    report = doctor.inspect_wrapper(config, scripts, live=True).facts
    assert report["healthy"] is False and report["live"]["account_match"] is False
    assert report["next"].endswith("google_workspace.py auth --force")
    monkeypatch.setattr(doctor.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    report = doctor.inspect_wrapper(config, scripts, live=True).facts
    assert report["live"]["error"] == "network or Google unavailable; retry"
    assert report["next"] is None


@pytest.mark.parametrize(
    ("code", "next_fragment"),
    [("invalid_grant", "token revoked or expired"),
     ("invalid_client", "fix client source"),
     (UNRELATED_SECRET, None)],
)
def test_live_refresh_4xx_whitelists_code_and_redacts_body(doctor, tmp_path, monkeypatch, capsys, code, next_fragment):
    config, scripts, _ = wrapper(tmp_path)
    failure = http_failure(doctor, 400, {"error": code, "error_description": CLIENT_SECRET})
    monkeypatch.setattr(doctor.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(failure))
    report = doctor.inspect_wrapper(config, scripts, live=True).facts
    doctor._print_text(report)
    rendered = json.dumps(report) + capsys.readouterr().out
    assert CLIENT_SECRET not in rendered and UNRELATED_SECRET not in rendered
    if doctor.OAUTH_ERROR.fullmatch(code):
        assert report["live"]["error"] == f"refresh rejected: {code}"
    else:
        assert report["live"]["error"] == "refresh rejected (HTTP 400)"
    assert (next_fragment in report["next"]) if next_fragment else report["next"] is None


def test_live_refresh_5xx_is_retryable_and_redacted(doctor, tmp_path, monkeypatch, capsys):
    config, scripts, _ = wrapper(tmp_path)
    failure = http_failure(doctor, 503, {"error": "server_error", "detail": CLIENT_SECRET})
    monkeypatch.setattr(doctor.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(failure))
    report = doctor.inspect_wrapper(config, scripts, live=True).facts
    doctor._print_text(report)
    assert CLIENT_SECRET not in json.dumps(report) + capsys.readouterr().out
    assert report["live"]["error"] == "network or Google unavailable; retry"
    assert report["next"] is None


@pytest.mark.parametrize(("status", "force"), [(403, True), (500, False)])
def test_live_identity_http_status_controls_recovery(doctor, tmp_path, monkeypatch, capsys, status, force):
    config, scripts, _ = wrapper(tmp_path)
    responses = iter((Response({"access_token": ACCESS_TOKEN}), http_failure(doctor, status, {"detail": CLIENT_SECRET})))

    def urlopen(*args, **kwargs):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(doctor.request, "urlopen", urlopen)
    report = doctor.inspect_wrapper(config, scripts, live=True).facts
    doctor._print_text(report)
    assert CLIENT_SECRET not in json.dumps(report) + capsys.readouterr().out
    assert report["live"]["error"] == f"identity lookup failed (HTTP {status})"
    assert (report["next"] or "").endswith("auth --force") is force


def test_rest_token_health_does_not_require_mint_client_or_match(doctor, tmp_path, monkeypatch):
    config, scripts, config_dir = wrapper(tmp_path, interface="REST", client="mint-client")
    write_token(config_dir / "token.json", client="cached-client")
    assert doctor.inspect_wrapper(config, scripts).facts["healthy"] is True
    (config_dir / "client.json").unlink()
    report = doctor.inspect_wrapper(config, scripts).facts
    assert report["healthy"] is True and report["next"] is None
    assert report["warnings"]


def test_readonly_inline_config_and_rest_overrides(doctor, tmp_path, monkeypatch):
    config, scripts, _ = wrapper(tmp_path, interface="readonly")
    resolved = doctor._resolve_wrapper(scripts.parent)
    assert resolved == (config.resolve(), scripts.resolve())
    assert doctor.inspect_wrapper(*resolved).facts["interface"] == "readonly"

    rest_config, rest_scripts, _ = wrapper(tmp_path / "other", interface="REST")
    override = tmp_path / "override"
    override.mkdir()
    (override / "client.json").write_text(json.dumps({"installed": {"client_id": "override-client", "client_secret": CLIENT_SECRET}}))
    write_token(override / "token.json", client="override-client")
    monkeypatch.setenv("GWS_CONFIG_DIR", str(override))
    monkeypatch.setenv("GWS_EXPECTED_EMAIL", "override@example.org")
    report = doctor.inspect_wrapper(rest_config, rest_scripts).facts
    assert report["expected_account"] == "override@example.org" and report["token"]["path"] == str(override / "token.json")


def test_repo_env_cloud_env_missing_offline_and_parent_symlink_parity(doctor, tmp_path, monkeypatch):
    config, scripts, config_dir = wrapper(tmp_path)
    loaded = doctor._load_config(config)
    loaded.pop("env_file")
    loaded["repo_env"] = True
    config.write_text(f"WORKSPACE_CONFIG = {loaded!r}\n")
    (scripts.parents[3] / ".env").write_text(f"GOOGLE_WORKSPACE_CLIENT_ID=file-client\nGOOGLE_WORKSPACE_CLIENT_SECRET={CLIENT_SECRET}\n")
    assert doctor.inspect_wrapper(config, scripts).facts["client"]["source"] == "repo .env path"

    (config_dir / "token.json").unlink()
    loaded["offline_token_file"] = str(tmp_path / "missing-offline-token")
    config.write_text(f"WORKSPACE_CONFIG = {loaded!r}\n")
    assert doctor.inspect_wrapper(config, scripts).facts["next"].endswith("google_workspace.py auth")

    rest_config, rest_scripts, rest_dir = wrapper(tmp_path / "rest", interface="REST")
    link = tmp_path / "config-parent-link"
    link.symlink_to(rest_dir.parent, target_is_directory=True)
    rest_loaded = doctor._load_config(rest_config)
    rest_loaded["config_dir"] = str(link / rest_dir.name)
    rest_config.write_text(f"WORKSPACE_CONFIG = {rest_loaded!r}\n")
    assert doctor.inspect_wrapper(rest_config, rest_scripts).facts["healthy"] is True

    for name, value in zip(doctor.CLOUD_VARS, (REFRESH_TOKEN, "cloud-client", CLIENT_SECRET)):
        monkeypatch.setenv(name, value)
    assert doctor.inspect_wrapper(rest_config, rest_scripts).facts["healthy"] is True


def test_bad_wrapper_does_not_abort_other_reports(doctor, tmp_path, capsys):
    good, _, _ = wrapper(tmp_path)
    bad = tmp_path / "bad.py"
    bad.write_text("WORKSPACE_CONFIG = MISSING_HELPER\n")
    assert doctor.main([str(bad), str(good), "--json"]) == 1
    reports = json.loads(capsys.readouterr().out)["wrappers"]
    assert len(reports) == 2 and reports[0]["healthy"] is False and reports[1]["healthy"] is True


def test_offline_file_and_legacy_resolution(doctor, tmp_path, monkeypatch):
    config, scripts, config_dir = wrapper(tmp_path)
    (config_dir / "token.json").unlink()
    legacy = scripts / "legacy-token.json"
    write_token(legacy)
    assert doctor.inspect_wrapper(config, scripts).facts["token"]["source"] == "legacy"
    legacy.unlink()
    offline = tmp_path / "offline-token"
    offline.write_text(REFRESH_TOKEN)
    offline.chmod(0o600)
    loaded = doctor._load_config(config)
    loaded["offline_token_file"] = str(offline)
    config.write_text(f"WORKSPACE_CONFIG = {loaded!r}\n")
    assert doctor.inspect_wrapper(config, scripts).facts["token"]["source"] == "offline-file"
