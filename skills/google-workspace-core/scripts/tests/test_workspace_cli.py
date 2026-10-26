"""One command surface for every account: help without credentials, and correct dispatch."""

from types import SimpleNamespace

import pytest

from gws_core.cli import build_parser, cmd_api, main
from gws_core.errors import WorkspaceError

EXPECTED_COMMANDS = {
    "accounts", "auth", "doctor", "whoami", "token", "api",
    "drive-list", "drive-search", "drive-get", "drive-create", "drive-copy", "drive-upload",
    "drive-replace", "drive-trash", "drive-download", "drive-export",
    "doc-read", "doc-outline", "doc-replace", "doc-insert", "doc-batch",
    "sheet-meta", "sheet-read", "sheet-write", "sheet-append", "sheet-clear", "sheet-batch-clear",
    "sheet-batch-write", "sheet-batch", "sheet-add-tab", "sheet-delete-rows", "sheet-freeze-rows",
    "sheet-format-rows", "sheet-named-ranges", "sheet-add-named-range", "sheet-tables",
    "table-read", "table-append", "table-rename",
    "gmail-search", "gmail-export", "gmail-recent", "gmail-get", "gmail-thread", "gmail-url", "gmail-send", "gmail-draft",
    "gmail-draft-list", "gmail-draft-get", "gmail-draft-update", "gmail-draft-send", "gmail-draft-delete",
    "gmail-labels", "gmail-label", "gmail-attachments", "gmail-save-text",
    "slides-resolve", "slides-outline", "slides-slide", "slides-text", "slides-replace", "slides-set-text",
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
        if name in ("auth", "accounts"):
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
    args = build_parser().parse_args(["api", "GET", "/slides/v1/presentations/abc"])
    args.json = True
    with pytest.raises(WorkspaceError, match="unknown API path"):
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


def test_network_failures_name_a_host_outside_googleapis():
    import httpx

    from gws_core.cli import network_failure

    request = httpx.Request("GET", "https://lh7-rt.googleusercontent.com/x")
    message = network_failure(httpx.ProxyError("403 Forbidden", request=request))
    assert message.startswith("network failure talking to lh7-rt.googleusercontent.com")
    assert "allow lh7-rt.googleusercontent.com" in message
    inside = httpx.Request("GET", "https://slides.googleapis.com/v1/x")
    assert "allow" not in network_failure(httpx.ConnectError("boom", request=inside))


def test_draft_prints_a_mail_ref_line_t3_mail_link_can_claim(capsys):
    from gws_core.cli import cmd_gmail_draft
    draft = {"id": "r-1", "message": {"id": "m1", "threadId": "19e875318442de06"}, "verified": {"files": 0}}
    ws = SimpleNamespace(config=SimpleNamespace(account="Operator@Example.com"),
                         gmail=SimpleNamespace(create_draft=lambda *a, **k: draft))
    args = build_parser().parse_args(["gmail-draft", "--to", "a@b.c", "--subject", "s", "--body", "b"])
    args.json = False
    cmd_gmail_draft(args, ws)
    assert "\nMail-ref: gmail:19e875318442de06 operator@example.com\n" in capsys.readouterr().out
    args.json = True
    cmd_gmail_draft(args, ws)
    captured = capsys.readouterr()
    assert captured.err.startswith("Mail-ref: gmail:19e875318442de06 operator@example.com\nOpen: ")


def test_draft_also_prints_a_clickable_gmail_link(capsys):
    from gws_core.cli import cmd_gmail_draft
    draft = {"id": "r-1", "message": {"id": "m1", "threadId": "19e875318442de06"}, "verified": {"files": 0}}
    ws = SimpleNamespace(config=SimpleNamespace(account="Operator@Example.com"),
                         gmail=SimpleNamespace(create_draft=lambda *a, **k: draft))
    args = build_parser().parse_args(["gmail-draft", "--to", "a@b.c", "--subject", "s", "--body", "b"])
    args.json = False
    cmd_gmail_draft(args, ws)
    assert ("\nOpen: https://mail.google.com/mail/?authuser=operator@example.com#all/19e875318442de06\n"
            in capsys.readouterr().out)


@pytest.mark.parametrize("ref", [
    ("https://mail.google.com/mail/u/1/?ik=85be6e80b2&view=pt&search=all"
     "&permthid=thread-f:1879530680048795886&simpl=msg-f:1879530680048795886"),
    "gmail:1a156f3200c1c0ee ops@example.com",
    "1A156F3200C1C0EE",
    "https://mail.google.com/mail/u/0/#inbox/1a156f3200c1c0ee",
    "https://mail.google.com/mail/u/0/?ui=2&view=pt&th=1a156f3200c1c0ee",
])
def test_gmail_url_turns_any_thread_reference_into_the_normal_view(ref, capsys):
    from gws_core.cli import cmd_gmail_url
    ws = SimpleNamespace(config=SimpleNamespace(account="ops@example.com"))
    args = build_parser().parse_args(["gmail-url", ref])
    args.json = False
    cmd_gmail_url(args, ws)
    assert capsys.readouterr().out.strip() == \
        "https://mail.google.com/mail/?authuser=ops@example.com#all/1a156f3200c1c0ee"


def test_gmail_url_refuses_new_ui_tokens():
    from gws_core.errors import WorkspaceError
    from gws_core.gmail import thread_id_from
    with pytest.raises(WorkspaceError, match="FMfcg"):
        thread_id_from("https://mail.google.com/mail/u/1/#all/FMfcgzQhWxXfGRwBsRKGdvFDwQGJbQrS")


def test_gmail_thread_runs_with_its_own_display_flags(capsys):
    from gws_core.cli import cmd_gmail_thread
    seen = {}
    gmail = SimpleNamespace(thread=lambda tid: {"id": tid, "messages": [{"id": "m1"}]},
                            view=lambda message, trim: seen.update(trim=trim) or {
                                "id": "m1", "threadId": "t1", "headers": {}, "attachments": [],
                                "body": "x" * 80})
    ws = SimpleNamespace(config=SimpleNamespace(account="ops@example.com"), gmail=gmail)
    args = build_parser().parse_args(["gmail-thread", "1a156f3200c1c0ee", "--full", "--max-chars", "50"])
    args.json = False
    cmd_gmail_thread(args, ws)
    assert seen["trim"] is False and "x" * 50 + "\n…[truncated]" in capsys.readouterr().out


def test_links_name_the_account_by_email_never_by_slot():
    from gws_core.links import gmail_draft_url, gmail_url, with_account
    assert gmail_url("Ops@Example.com", "drafts") == "https://mail.google.com/mail/?authuser=ops@example.com#drafts"
    assert gmail_draft_url("ops@example.com", "1a172010846bc05a") == \
        "https://mail.google.com/mail/?authuser=ops@example.com#drafts?compose=1a172010846bc05a"
    assert with_account("https://script.google.com/u/2/home/projects/abc/edit", "ops@example.com") == \
        "https://script.google.com/home/projects/abc/edit?authuser=ops@example.com"
    assert with_account("https://console.cloud.google.com/apis/credentials?authuser=2&project=p#x",
                        "ops@example.com") == \
        "https://console.cloud.google.com/apis/credentials?project=p&authuser=ops@example.com#x"


def test_draft_commands_print_the_draft_compose_link(capsys):
    from gws_core.cli import cmd_gmail_draft, cmd_gmail_draft_get, cmd_gmail_draft_list
    draft = {"id": "r-1", "message": {"id": "m1", "threadId": "19e875318442de06", "headers": {},
                                     "attachments": [], "body": "b"},
             "verified": {"files": 0}}
    ws = SimpleNamespace(config=SimpleNamespace(account="Operator@Example.com"),
                         gmail=SimpleNamespace(create_draft=lambda *a, **k: draft, get_draft=lambda _id: draft,
                                               drafts=lambda _max: [draft]))
    link = "https://mail.google.com/mail/?authuser=operator@example.com#drafts?compose=m1"
    args = build_parser().parse_args(["gmail-draft", "--to", "a@b.c", "--subject", "s", "--body", "b"])
    args.json = False
    cmd_gmail_draft(args, ws)
    assert f"\nDraft: {link}\n" in capsys.readouterr().out
    args = build_parser().parse_args(["gmail-draft-get", "r-1"])
    args.json = True
    cmd_gmail_draft_get(args, ws)
    assert f"Draft: {link}\n" in capsys.readouterr().err
    args = build_parser().parse_args(["gmail-draft-list"])
    args.json = False
    cmd_gmail_draft_list(args, ws)
    assert link in capsys.readouterr().out
