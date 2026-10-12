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


def test_missing_token_error_names_paths_without_contents(cli, config, monkeypatch):
    config.write_text(config.read_text() + '\n[auth]\nenv_var = "TEST_CLICKUP_TOKEN"\nenv_file = "auth.env"\n')
    env_file = config.with_name("auth.env")
    env_file.write_text("SERVICE_ACCOUNT_KEY=UNRELATED_SECRET_SENTINEL\nOTHER_TOKEN=TOKEN_SENTINEL\n")
    cli.configure(config)
    monkeypatch.delenv("TEST_CLICKUP_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.token_from_env()
    message = str(exc.value)
    assert "TEST_CLICKUP_TOKEN" in message and str(config.resolve()) in message
    assert str(env_file.resolve()) in message and "exists but lacks" in message
    assert "UNRELATED_SECRET_SENTINEL" not in message and "TOKEN_SENTINEL" not in message


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
        assert dict(params) == {"include_closed": "false", "subtasks": "true", "include_timl": "true", "assignees[]": "102", "statuses[]": "todo", "tags[]": "bug", "page": index}
    assert cli.list_id("999") == "999"


@pytest.mark.parametrize("value", ["2026-10-12", "2026-10-12T00:00", "2026-10-12T00:00:00Z",
                                   "2026-10-12T02:00:00+02:00"])
def test_lookup_dates_are_utc_milliseconds(cli, value):
    assert cli.updated_since(value) == 1791763200000
    assert cli.updated_since("2026-10-12T00:00:00.123Z") == 1791763200123


@pytest.mark.parametrize("value", ["1791763200", "1791763200000", "20261012", "12/10/2026",
                                   "2026-02-30", "2026-10-12junk00:00", "2026-10-12T25:00",
                                   "2026-10-12T00:00+01:99", "2026-10-12T00:00+24:00"])
def test_lookup_dates_reject_non_iso_or_invalid(cli, value):
    with pytest.raises(cli.argparse.ArgumentTypeError, match="ISO"):
        cli.updated_since(value)


def test_lookup_numeric_list_pagination_dedupes_multilist_tasks(cli, config, monkeypatch):
    cli.configure(config)
    calls = []
    foreign = {"id": "shared", "list": {"id": "999"}}
    def api(method, path, **kw):
        calls.append((method, path, dict(kw["params"])))
        return {"tasks": [foreign, {"id": str(len(calls))}], "last_page": len(calls) == 2}
    monkeypatch.setattr(cli, "api", api)
    assert cli.fetch_tasks("123", None, [], False, updated_after=1791763200000) == [foreign, {"id": "1"}, {"id": "2"}]
    assert cli.list_key_of(foreign) == "999"
    for page, (method, path, params) in enumerate(calls):
        assert (method, path) == ("GET", "/list/123/task")
        assert params == {"include_closed": "false", "subtasks": "true", "include_timl": "true",
                          "date_updated_gt": 1791763200000, "page": page}


@pytest.mark.parametrize("flags, expected", [([], ["a", "b"]), (["--titles-only"], ["a"])])
def test_search_or_terms_one_fetch_and_default_body_matching(cli, config, monkeypatch, capsys, flags, expected):
    tasks = [{"id": "a", "name": "ALPHA issue", "description": "unrelated"},
             {"id": "b", "name": "generic title", "description": "BETA symptom"},
             {"id": "c", "name": "other", "description": "none"}]
    calls = []
    def api(method, path, **kw):
        calls.append((method, path, kw))
        return {"tasks": tasks, "last_page": True}
    monkeypatch.setattr(cli, "api", api)
    cli.main(["search", "--search", "alpha", "--search", "beta", "--json", "--config", str(config), *flags])
    assert [t["id"] for t in json.loads(capsys.readouterr().out)] == expected
    assert len(calls) == 1
    cli.main(["tasks", "--search", "beta", "--json", "--config", str(config)])
    assert json.loads(capsys.readouterr().out) == [tasks[1]]


@pytest.mark.parametrize("closed", [False, True])
def test_summary_body_free_dates_sort_and_text(cli, config, monkeypatch, capsys, closed):
    base = {"list": {"id": "30"}, "status": {"status": "todo"}, "name": "Issue\nname",
            "assignees": [{"username": "Sam"}], "description": "BODY_SENTINEL",
            "markdown_description": "MARKDOWN_SENTINEL", "custom_fields": [{"id": "secret"}],
            "date_created": "1791763200000", "date_closed": None, "url": "https://app.clickup.com/t/example"}
    tasks = [{**base, "id": "old", "date_updated": "1791763200001"},
             {**base, "id": "new", "date_updated": "1791763200123", "parent": "parent-task"}]
    def api(method, path, **kw):
        assert dict(kw["params"])["date_updated_gt"] == 1791763200000
        assert dict(kw["params"])["include_closed"] == str(closed).lower()
        return {"tasks": tasks, "last_page": True}
    monkeypatch.setattr(cli, "api", api)
    flags = ["tasks", "--summary", "--updated-since", "2026-10-12", "--config", str(config)]
    if closed:
        flags.append("--include-closed")
    cli.main([*flags, "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["new", "old"]
    assert set(rows[0]) == {"id", "name", "list", "status", "assignees", "parent",
                            "date_created", "date_updated", "date_closed", "url"}
    assert rows[0]["date_updated"] == "2026-10-12T00:00:00.123Z"
    assert rows[0]["date_created"] == "2026-10-12T00:00:00.000Z"
    assert rows[0]["date_closed"] is None and rows[0]["parent"] == "parent-task"
    cli.main(flags)
    text = capsys.readouterr().out
    assert text.startswith("2026-10-12T00:00:00.123Z  new  queue  todo  Issue name  Sam  parent=parent-task")
    assert len(text.splitlines()) == 2 and "SENTINEL" not in text


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
