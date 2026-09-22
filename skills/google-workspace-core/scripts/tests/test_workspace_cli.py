"""One command surface for every account: help without credentials, and correct dispatch."""

from types import SimpleNamespace

import pytest

from gws_core.cli import build_parser, cmd_api, main
from gws_core.errors import WorkspaceError

EXPECTED_COMMANDS = {
    "auth", "doctor", "whoami", "token", "api",
    "drive-list", "drive-search", "drive-get", "drive-create", "drive-copy", "drive-upload",
    "drive-replace", "drive-trash", "drive-download", "drive-export",
    "doc-read", "doc-outline", "doc-replace", "doc-insert", "doc-batch",
    "sheet-meta", "sheet-read", "sheet-write", "sheet-append", "sheet-clear", "sheet-batch-clear",
    "sheet-batch-write", "sheet-batch", "sheet-add-tab", "sheet-delete-rows", "sheet-freeze-rows",
    "sheet-format-rows", "sheet-named-ranges", "sheet-add-named-range", "sheet-tables",
    "table-read", "table-append", "table-rename",
    "gmail-search", "gmail-export", "gmail-recent", "gmail-get", "gmail-thread", "gmail-send", "gmail-draft",
    "gmail-draft-list", "gmail-draft-get", "gmail-draft-send", "gmail-draft-delete",
    "gmail-labels", "gmail-label", "gmail-attachments", "gmail-save-text",
    "slides-outline", "slides-slide", "slides-text", "slides-replace", "slides-set-text",
    "slides-batch", "slides-add", "slides-notes", "slides-delete", "slides-move", "slides-image",
    "slides-thumbnail", "slides-export-pdf",
}


def commands(parser):
    action = next(item for item in parser._actions if item.choices and item.dest == "cmd")
    return action.choices


def test_every_account_gets_the_same_complete_command_set():
    assert set(commands(build_parser())) == EXPECTED_COMMANDS


def test_help_needs_no_config_and_no_credentials(monkeypatch, capsys):
    monkeypatch.delenv("GWS_CONFIG", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    assert "--config" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["whoami"], ["gmail-send", "--to", "a@b.c", "--subject", "x",
                                              "--body", "y"]])
def test_a_command_without_config_says_which_flag_is_missing(monkeypatch, argv, capsys):
    monkeypatch.delenv("GWS_CONFIG", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert "--config" in str(exit_info.value)


def test_config_can_come_from_the_environment(monkeypatch, write_config):
    monkeypatch.setenv("GWS_CONFIG", str(write_config()))
    seen = {}
    parsed = build_parser().parse_args(["whoami"])
    parsed.fn = lambda a, ws: seen.update(account=ws.config.account)
    monkeypatch.setattr("gws_core.cli.build_parser", lambda: SimpleNamespace(parse_args=lambda argv: parsed))
    main(["whoami"])
    assert seen["account"] == "team@example.com"


def test_every_subcommand_is_wired_to_an_implementation():
    parser = build_parser()
    for name, sub in commands(parser).items():
        if name == "auth":
            for action in sub._actions:
                if action.choices:
                    assert all(callable(item.get_default("fn")) for item in action.choices.values())
            continue
        assert callable(sub.get_default("fn")), name


def test_api_passthrough_expands_shorthands_and_refuses_foreign_hosts():
    calls = []
    workspace = SimpleNamespace(api=lambda method, url, **kw: calls.append((method, url, kw)) or {})
    args = build_parser().parse_args(["api", "GET", "/v4/spreadsheets/abc", "--param", "fields=id"])
    args.json = True
    cmd_api(args, workspace)
    assert calls[0][1] == "https://sheets.googleapis.com/v4/spreadsheets/abc"
    assert calls[0][2]["params"] == {"fields": "id"}
    args = build_parser().parse_args(["api", "GET", "https://evil.example.com/v1/x"])
    args.json = True
    with pytest.raises(WorkspaceError, match="googleapis.com"):
        cmd_api(args, workspace)


def test_mail_body_is_either_inline_or_a_file():
    parser = build_parser()
    parsed = parser.parse_args(["gmail-draft", "--to", "a@b.c", "--subject", "s", "--body", "text"])
    assert parsed.body == "text" and parsed.body_file is None
    with pytest.raises(SystemExit):
        parser.parse_args(["gmail-draft", "--to", "a@b.c", "--subject", "s", "--body", "t",
                           "--body-file", "f"])
    with pytest.raises(SystemExit):
        parser.parse_args(["gmail-draft", "--to", "a@b.c", "--subject", "s"])


def test_html_flag_and_html_file_are_mutually_exclusive():
    parser = build_parser()
    parsed = parser.parse_args(["gmail-send", "--to", "a@b.c", "--subject", "s",
                                "--body-file", "body.txt", "--html-file", "body.html"])
    assert parsed.html is False and parsed.html_file == "body.html"
    with pytest.raises(SystemExit):
        parser.parse_args(["gmail-send", "--to", "a@b.c", "--subject", "s", "--body", "b",
                           "--html", "--html-file", "body.html"])


def test_json_flag_works_before_and_after_the_command():
    assert build_parser().parse_args(["--json", "whoami"]).json is True
    assert build_parser().parse_args(["whoami", "--json"]).json is True


def test_sheet_write_requires_values_or_csv(write_config, monkeypatch):
    monkeypatch.setenv("GWS_CONFIG", str(write_config()))
    with pytest.raises(SystemExit) as exit_info:
        main(["sheet-write", "1AAAAAAAAAAAAAAAA", "A1"])
    assert "--values or --csv" in str(exit_info.value)
