"""The wrapper config is the only place an account, scope or credential path is named."""

import json

import pytest

from gws_core import ConfigError, load_config

from workspace_testkit import ACCOUNT


def test_unknown_key_and_missing_required_are_refused(write_config, tmp_path):
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(write_config(expected_email="other@example.com"))
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"account": ACCOUNT}), encoding="utf-8")
    with pytest.raises(ConfigError, match="missing required key"):
        load_config(path)


def test_paths_resolve_against_the_config_file_and_home(write_config, tmp_path):
    config = load_config(write_config(client_env=[".env"], legacy_token="legacy/.google_token.json",
                                      config_dir="~/.config/example"))
    assert config.client_env == (tmp_path / ".env",)
    assert config.legacy_token == (tmp_path / "legacy/.google_token.json")
    assert config.config_dir.is_absolute() and "~" not in str(config.config_dir)


def test_account_override_only_through_the_named_variable(write_config, monkeypatch):
    monkeypatch.setenv("GWS_EXPECTED_EMAIL", "someone-else@example.com")
    monkeypatch.setenv("GOOGLE_WORKSPACE_ACCOUNT", "override@example.com")
    assert load_config(write_config()).account == ACCOUNT
    assert load_config(write_config(account_env="GOOGLE_WORKSPACE_ACCOUNT")).account == "override@example.com"
    assert load_config(write_config(account_env="GWS_EXPECTED_EMAIL")).account == "someone-else@example.com"


def test_config_dir_and_offline_overrides_are_opt_in(write_config, monkeypatch, tmp_path):
    monkeypatch.setenv("GWS_CONFIG_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("GOOGLE_WORKSPACE_OFFLINE_TOKEN_FILE", str(tmp_path / "shared.txt"))
    plain = load_config(write_config())
    assert plain.config_dir == tmp_path / "creds"
    assert plain.offline_token_file is None
    opted_in = load_config(write_config(config_dir_env="GWS_CONFIG_DIR",
                                        offline_token_file="~/Downloads/token.txt"))
    assert opted_in.config_dir == tmp_path / "elsewhere"
    assert opted_in.offline_token_file == tmp_path / "shared.txt"


def test_mint_scopes_are_exactly_what_the_wrapper_configured(write_config):
    drive_only = ["https://www.googleapis.com/auth/drive"]
    config = load_config(write_config(scopes=drive_only))
    assert list(config.mint_scopes) == drive_only  # consent is never widened by the core
    assert not config.wants_openid  # such a token is identified through the Gmail profile
    config = load_config(write_config(scopes=drive_only, mint_scopes=[*drive_only, "openid"]))
    assert list(config.mint_scopes) == [*drive_only, "openid"]


def test_cloud_token_env_is_opt_in(write_config):
    assert load_config(write_config()).cloud_token_env is False
    assert load_config(write_config(cloud_token_env=True)).cloud_token_env is True


def test_missing_config_names_the_flag(monkeypatch):
    monkeypatch.delenv("GWS_CONFIG", raising=False)
    with pytest.raises(ConfigError, match="--config"):
        load_config()
