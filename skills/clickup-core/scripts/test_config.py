"""Offline operator-contract tests; no requests may leave this process."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def cli(monkeypatch):
    spec = importlib.util.spec_from_file_location("clickup_under_test", Path(__file__).with_name("clickup.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def reject(*args, **kwargs):
        pytest.fail("unexpected network call")
    monkeypatch.setattr(module.requests, "request", reject)
    monkeypatch.delenv("CLICKUP_CONFIG", raising=False)
    monkeypatch.setenv("CLICKUP_API_PERSONAL_TOKEN", "offline-token")
    return module


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "workspace.toml"
    path.write_text('''[workspace]
id = "10"
space_id = "20"
default_list = "queue"
[lists.queue]
id = "30"
statuses = ["todo", "done"]
default_status = "todo"
[members.author]
id = 101
[members.reviewer]
id = 102
[members.third]
id = 103
[policy]
handoff_pair = ["author", "reviewer"]
[custom_fields.level]
id = "field-uuid"
[custom_fields.level.options]
high = "option-uuid"
''')
    return path


def test_config_nearest_root_agents_precedence_and_overrides(cli, tmp_path, monkeypatch, config):
    outer = tmp_path / ".agents/skills/clickup/clickup.toml"
    inner = tmp_path / "project/.claude/skills/clickup/clickup.toml"
    agents = tmp_path / "project/.agents/skills/clickup/clickup.toml"
    for path in (outer, inner):
        path.parent.mkdir(parents=True)
        path.write_text("")
    cwd = tmp_path / "project/src"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert cli.find_config() == inner
    agents.parent.mkdir(parents=True)
    agents.write_text("")
    assert cli.find_config() == agents
    monkeypatch.setenv("CLICKUP_CONFIG", str(outer))
    assert cli.find_config() == outer
    assert cli.find_config(str(config)) == config
    with pytest.raises(SystemExit, match="does not exist"):
        cli.find_config(str(tmp_path / "missing.toml"))


def test_auth_relative_file_quoted_export_and_environment_precedence(cli, config, monkeypatch):
    config.write_text(config.read_text() + '\n[auth]\nenv_var = "TEST_CLICKUP_TOKEN"\nenv_file = "auth.env"\n')
    config.with_name("auth.env").write_text('OTHER=ignored\n export TEST_CLICKUP_TOKEN = "quoted # token" # comment\n')
    cli.configure(config)
    monkeypatch.delenv("TEST_CLICKUP_TOKEN", raising=False)
    assert cli.token_from_env() == "quoted # token"
    monkeypatch.setenv("TEST_CLICKUP_TOKEN", " env-wins ")
    assert cli.token_from_env() == "env-wins"


@pytest.mark.parametrize("flags", [["--json", "workspaces"], ["workspaces", "--json"]])
def test_json_flag_positions(cli, config, monkeypatch, capsys, flags):
    monkeypatch.setattr(cli, "api", lambda *args, **kw: {"teams": [{"id": "10"}]})
    cli.main(["--config", str(config), *flags])
    assert json.loads(capsys.readouterr().out) == {"teams": [{"id": "10"}]}


def test_filtered_tasks_paginate_and_resolve_list_and_member(cli, config, monkeypatch):
    cli.configure(config)
    calls = []
    def api(method, path, **kw):
        calls.append((method, path, kw["params"]))
        return {"tasks": [{"id": str(len(calls))}], "last_page": len(calls) == 2}
    monkeypatch.setattr(cli, "api", api)
    assert cli.fetch_tasks("queue", "reviewer", ["todo"], False, ["bug"]) == [{"id": "1"}, {"id": "2"}]
    for index, (method, path, params) in enumerate(calls):
        assert (method, path) == ("GET", "/list/30/task")
        assert dict(params) == {"include_closed": "false", "subtasks": "true", "assignees[]": "102", "statuses[]": "todo", "tags[]": "bug", "page": index}
    assert cli.list_id("999") == "999"


def test_custom_field_enum_and_raw_json_payload(cli, config, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "api", lambda method, path, **kw: calls.append((method, path, kw)))
    monkeypatch.setattr(cli, "read_back", lambda *args: None)
    for value in ("high", '["one", "two"]'):
        cli.main(["field", "abc123", "level", "--value", value, "--config", str(config)])
    assert [(m, p, json.loads(kw["data"])) for m, p, kw in calls] == [
        ("POST", "/task/abc123/field/field-uuid", {"value": "option-uuid"}),
        ("POST", "/task/abc123/field/field-uuid", {"value": ["one", "two"]})]


def test_handoff_pair_assignee_exclusions_and_ambiguity(cli, config, monkeypatch):
    cli.configure(config)
    monkeypatch.setattr(cli, "api", lambda *args, **kw: {"user": {"id": 101}})
    assert cli.counterpart({}) == 102
    assert cli.counterpart({}, "third") == 103
    cli.CONFIG["policy"].update(handoff_mode="assignee", ignored_assignees=[999])
    assert cli.counterpart({"assignees": [{"id": 101}, {"id": 999}, {"id": 103}]}) == 103
    with pytest.raises(SystemExit, match="one recipient"):
        cli.counterpart({"assignees": [{"id": 102}, {"id": 103}]})


def test_create_keeps_tags_and_optional_priority(cli, config, monkeypatch):
    calls = []
    def api(method, path, **kw):
        calls.append((method, path, json.loads(kw["data"])))
        return {"id": "abc123"}
    monkeypatch.setattr(cli, "api", api)
    monkeypatch.setattr(cli, "read_back", lambda *args: None)
    cli.main(["--config", str(config), "create", "--name", "Example", "--assignee", "reviewer", "--tag", "bug"])
    assert calls == [("POST", "/list/30/task", {"name": "Example", "assignees": [102], "status": "todo", "tags": ["bug"]})]


def test_lists_discovery_includes_folderless_and_folder_lists(cli, config, monkeypatch, capsys):
    responses = {
        "/space/20/list": {"lists": [{"id": "30"}]},
        "/space/20/folder": {"folders": [{"id": "40"}]},
        "/folder/40/list": {"lists": [{"id": "50"}]},
    }
    monkeypatch.setattr(cli, "api", lambda method, path: responses[path])
    cli.main(["lists", "--json", "--config", str(config)])
    assert json.loads(capsys.readouterr().out) == {"lists": [{"id": "30"}, {"id": "50"}]}


def test_task_json_keeps_markdown_and_lossless_content(cli, config, monkeypatch, capsys):
    def get_task(tid, markdown=False):
        assert tid == "abc123" and markdown is True
        return {"id": tid, "markdown_description": "**Useful**"}
    monkeypatch.setattr(cli, "get_task", get_task)
    monkeypatch.setattr(cli, "get_task_content", lambda tid: '{"ops":[{"insert":"Useful"}]}')
    cli.main(["task", "abc123", "--json", "--config", str(config)])
    task = json.loads(capsys.readouterr().out)["task"]
    assert task["markdown_description"] == "**Useful**"
    assert json.loads(task["content"])["ops"] == [{"insert": "Useful"}]


def test_ignored_service_account_cannot_be_assigned_or_mentioned(cli, config):
    cli.configure(config)
    cli.CONFIG["policy"]["ignored_assignees"] = [103]
    for who in ("third", "103"):
        with pytest.raises(SystemExit, match="forbids"):
            cli.user_id(who)
    for text in ("ping @third", "ping [@Service](#user_mention#103)"):
        with pytest.raises(SystemExit, match="forbids"):
            cli.comment_parts(text)
        with pytest.raises(SystemExit, match="forbids"):
            cli.md_to_delta(text)
