"""Request payloads of the shared implementations, without touching Google."""

import base64
from email import message_from_bytes

import pytest

from gws_core.drive import DriveClient
from gws_core.errors import WorkspaceError
from gws_core.gmail import GmailClient, extract_codes, trim_quotes
from gws_core.sheets import SheetsClient
from gws_core.slides import SlidesClient

from workspace_testkit import ACCOUNT, FakeSession, Recorded, RoutedSession


def body_part(text, mime="text/plain"):
    return {"mimeType": mime, "body": {"data": base64.urlsafe_b64encode(text.encode()).decode()}}


def test_drive_paginates_and_opts_into_shared_drives():
    session = FakeSession([
        Recorded({"files": [{"id": "a"}], "nextPageToken": "next"}),
        Recorded({"files": [{"id": "b"}]}),
    ])
    files = DriveClient(session).search("name contains 'x'", 5)
    assert [item["id"] for item in files] == ["a", "b"]
    first = session.calls[0][2]["params"]
    assert first["supportsAllDrives"] == "true" and first["includeItemsFromAllDrives"] == "true"
    assert session.calls[1][2]["params"]["pageToken"] == "next"


def test_drive_upload_is_multipart_and_replace_keeps_the_file(tmp_path):
    source = tmp_path / "report.csv"
    source.write_text("a,b\n", encoding="utf-8")
    session = FakeSession([Recorded({"id": "new"}), Recorded({"id": "same"})])
    drive = DriveClient(session)
    drive.upload(source, name="Report", parent="1AAAAAAAAAAAAAAAA")
    method, url, kw = session.calls[0]
    assert method == "POST" and url.endswith("/upload/drive/v3/files")
    assert kw["params"]["uploadType"] == "multipart"
    assert b'"name": "Report"' in kw["content"] and b"a,b" in kw["content"]
    drive.replace_content("1BBBBBBBBBBBBBBBB", source)
    method, url, kw = session.calls[1]
    assert method == "PATCH" and kw["params"]["uploadType"] == "media"
    assert kw["content"] == b"a,b\n"


def test_upload_endpoints_opt_into_shared_drives(tmp_path):
    """Both the create and the content-replacement upload URLs need supportsAllDrives."""
    from gws_core.session import Session

    source = tmp_path / "a.txt"
    source.write_text("x", encoding="utf-8")
    session = Session("token")
    recorded = []
    session._http = type("Http", (), {
        "request": lambda self, method, url, **kw: recorded.append((url, kw["params"]))
        or Recorded({"id": "x"})})()
    drive = DriveClient(session)
    drive.upload(source)
    drive.replace_content("1BBBBBBBBBBBBBBBB", source)
    assert all(params.get("supportsAllDrives") == "true" for _, params in recorded)


def test_drive_export_rejects_an_unknown_format():
    with pytest.raises(WorkspaceError, match="unknown format"):
        DriveClient(FakeSession()).export("1AAAAAAAAAAAAAAAA", "wat")


def test_sheets_values_and_native_tables():
    session = FakeSession([Recorded({"updatedCells": 2})])
    sheets = SheetsClient(session)
    sheets.write("1AAAAAAAAAAAAAAAA", "'Tab'!A1:B1", [["x", "y"]], raw=True)
    method, url, kw = session.calls[0]
    assert method == "PUT" and kw["params"]["valueInputOption"] == "RAW"
    assert "%27Tab%27%21A1%3AB1" in url and kw["json"] == {"values": [["x", "y"]]}

    table = {"tableId": "t1", "name": "behandelaars", "range": {"sheetId": 0, "startRowIndex": 0,
             "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 2},
             "columnProperties": [{"columnIndex": 0, "columnName": "naam"},
                                  {"columnIndex": 1, "columnName": "email"}]}
    listing = Recorded({"sheets": [{"properties": {"sheetId": 0, "title": "Blad1"},
                                    "tables": [table]}]})
    session = FakeSession([listing, Recorded({"values": [["naam", "email"], ["Ann"]]}),
                           listing, Recorded({"updates": {"updatedRows": 1}})])
    sheets = SheetsClient(session)
    assert sheets.read_table("1AAAAAAAAAAAAAAAA", "behandelaars") == [{"naam": "Ann", "email": ""}]
    sheets.append_table("1AAAAAAAAAAAAAAAA", "t1", [{"email": "a@b.c", "unknown": "dropped"}])
    assert session.calls[-1][2]["json"] == {"values": [["", "a@b.c"]]}


def test_gmail_reply_threads_quotes_and_guards_the_subject():
    original = {"id": "m1", "threadId": "t1", "payload": {
        "headers": [{"name": "Subject", "value": "Offerte"},
                    {"name": "Message-ID", "value": "<abc@mail>"},
                    {"name": "From", "value": "her@example.com"},
                    {"name": "Date", "value": "Mon, 1 Sep 2026 10:00:00 +0200"}],
        **body_part("Graag een offerte.\n\n> oude tekst")}}
    session = FakeSession([Recorded(original), Recorded({"id": "d1", "message": {"id": "m2"}})])
    gmail = GmailClient(session, sender=ACCOUNT)
    gmail.create_draft("her@example.com", "Re: Offerte", "Hier is ze.", reply_to_message="m1")
    payload = session.calls[-1][2]["json"]["message"]
    assert payload["threadId"] == "t1"
    message = message_from_bytes(base64.urlsafe_b64decode(payload["raw"]))
    assert message["In-Reply-To"] == "<abc@mail>" and message["From"] == ACCOUNT
    assert "> Graag een offerte." in message.get_payload(decode=True).decode()

    session = FakeSession([Recorded(original)])
    with pytest.raises(WorkspaceError, match="reply subject must match"):
        GmailClient(session, sender=ACCOUNT).send("her@example.com", "Iets anders", "x",
                                                  reply_to_message="m1")


def test_gmail_html_send_carries_both_alternatives():
    session = FakeSession([Recorded({"id": "sent"})])
    GmailClient(session, sender=ACCOUNT).send("a@b.c", "Hi", "<p>Hallo <b>daar</b></p>", html=True)
    raw = session.calls[0][2]["json"]["raw"]
    message = message_from_bytes(base64.urlsafe_b64decode(raw))
    types = {part.get_content_type() for part in message.walk()}
    assert {"text/plain", "text/html"} <= types
    plain = next(p for p in message.walk() if p.get_content_type() == "text/plain")
    assert "Hallo daar" in plain.get_payload(decode=True).decode()


def test_gmail_keeps_an_authored_plain_text_body_beside_an_html_alternative():
    session = FakeSession([Recorded({"id": "sent"})])
    GmailClient(session, sender=ACCOUNT).send("a@b.c", "Report", "Plain report",
                                              html_body="<h1>Rich report</h1>")
    message = message_from_bytes(base64.urlsafe_b64decode(session.calls[0][2]["json"]["raw"]))
    parts = {part.get_content_type(): part.get_payload(decode=True).decode()
             for part in message.walk() if part.get_content_type().startswith("text/")}
    assert parts["text/plain"].strip() == "Plain report"
    assert parts["text/html"].strip() == "<h1>Rich report</h1>"


def test_gmail_view_trims_quotes_only_when_asked():
    message = {"id": "m1", "threadId": "t1", "payload": {
        "headers": [{"name": "Subject", "value": "Code"}],
        **body_part("Your code is 4821\n\nOn Mon someone wrote:\n> old")}}
    gmail = GmailClient(FakeSession(), sender=ACCOUNT)
    assert "old" not in gmail.view(message)["body"]
    assert "old" in gmail.view(message, trim=False)["body"]
    assert extract_codes("Your code is 4821 and A1B2C3") == ["4821", "A1B2C3"]
    assert trim_quotes("keep\n-- \nsignature") == "keep"
    wrapped = "keep\n\nOn Mon, 11 Mar 2024 at 08:19, Someone <s@example.com>\nwrote:\n> old"
    assert trim_quotes(wrapped) == "keep"


def test_gmail_body_decoding_and_export_cleanup():
    from gws_core.gmail import _clean_body, _decode_text

    assert _decode_text("gegevens …".encode(), 'text/plain; charset="Windows-1252"') == "gegevens …"
    assert _decode_text("caf\xe9".encode("cp1252"), 'text/plain; charset="Windows-1252"') == "café"
    tracking = "<http://k3o5.mjt.lu/lnk/" + "A" * 120 + ">"
    assert _clean_body(f"https://juumo.io {tracking}\n\n\n\nbye ") == "https://juumo.io\n\nbye"


def mail(mid, tid, subject, date, sender, body="Hallo daar"):
    return {"id": mid, "threadId": tid, "payload": {
        "headers": [{"name": "Date", "value": date}, {"name": "From", "value": sender},
                    {"name": "To", "value": ACCOUNT}, {"name": "Subject", "value": subject}],
        **body_part(body)}}


M1 = mail("m1", "t1", "Offerte", "Mon, 17 Aug 2026 12:23:00 +0200", "Kim <kim@kbc.be>")
M2 = mail("m2", "t1", "Re: Offerte", "Tue, 18 Aug 2026 09:00:00 +0200", "Jan <jan@x.be>", "Bedankt")


def test_gmail_message_ids_paginate_up_to_the_limit():
    session = FakeSession([Recorded({"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "n"}),
                           Recorded({"messages": [{"id": "c"}, {"id": "d"}]})])
    ids = GmailClient(session, sender=ACCOUNT).message_ids("from:x", 3)
    assert [item["id"] for item in ids] == ["a", "b", "c"]
    assert session.calls[0][2]["params"]["maxResults"] == 3
    assert session.calls[1][2]["params"] == {"q": "from:x", "maxResults": 1, "pageToken": "n"}


def test_gmail_export_writes_greppable_files_and_skips_them_on_a_second_run(tmp_path):
    other = mail("m2", "t2", "Factuur", "Tue, 18 Aug 2026 09:00:00 +0200", "Jan <jan@x.be>")
    session = RoutedSession({"messages/m1": M1, "messages/m2": other,
                             "messages": {"messages": [{"id": "m1", "threadId": "t1"},
                                                       {"id": "m2", "threadId": "t2"}]}})
    gmail = GmailClient(session, sender=ACCOUNT)
    result = gmail.export("label:inbox", tmp_path)
    assert (result["written"], result["skipped"]) == (2, 0)
    text = (tmp_path / "2026-08-17_m1.md").read_text(encoding="utf-8")
    assert text.startswith("# Offerte\ndate: 2026-08-17 12:23\nfrom: Kim <kim@kbc.be>\n"
                           f"to: {ACCOUNT}\nid: m1  thread: t1\n\nHallo daar")
    index = (tmp_path / "index.md").read_text(encoding="utf-8").splitlines()
    assert [line.split("  ")[-1] for line in index] == ["2026-08-17_m1.md", "2026-08-18_m2.md"]
    assert index[0] == "2026-08-17 12:23  Kim <kim@kbc.be>  Offerte  2026-08-17_m1.md"
    again = gmail.export("label:inbox", tmp_path)
    assert (again["written"], again["skipped"], again["errors"]) == (0, 2, [])
    assert (tmp_path / "index.md").read_text(encoding="utf-8").splitlines() == index


def test_gmail_export_by_thread_writes_one_file_per_thread(tmp_path):
    session = RoutedSession({"threads/t1": {"id": "t1", "messages": [M1, M2]},
                             "messages": {"messages": [{"id": "m1", "threadId": "t1"},
                                                       {"id": "m2", "threadId": "t1"}]}})
    result = GmailClient(session, sender=ACCOUNT).export("label:inbox", tmp_path, by_thread=True)
    assert result["written"] == 1
    text = (tmp_path / "2026-08-17_t1.md").read_text(encoding="utf-8")
    assert text.startswith("# Offerte\nthread: t1\nmessages: 2\n\n"
                           "## 2026-08-17 12:23 \u00b7 Kim <kim@kbc.be>\n")
    assert text.count("\n## ") == 2 and "## 2026-08-18 09:00 \u00b7 Jan <jan@x.be>" in text
    assert (tmp_path / "index.md").read_text(encoding="utf-8").strip() == (
        "2026-08-17 12:23  Kim <kim@kbc.be>  Offerte (2 msgs)  2026-08-17_t1.md")


def test_gmail_attachment_names_are_safe_and_unique(tmp_path):
    payload = {"mimeType": "multipart/mixed", "parts": [
        body_part("body text"),
        {"mimeType": "application/pdf", "filename": "../../etc/pas:swd.pdf",
         "body": {"data": base64.urlsafe_b64encode(b"%PDF").decode(), "size": 4}},
        {"mimeType": "application/pdf", "filename": "../../etc/pas:swd.pdf",
         "body": {"data": base64.urlsafe_b64encode(b"%PDF").decode(), "size": 4}},
    ]}
    session = FakeSession([Recorded({"id": "m1", "payload": payload})])
    saved = GmailClient(session, sender=ACCOUNT).download_files("m1", tmp_path)
    names = [item["filename"] for item in saved]
    assert names == ["pas_swd.pdf", "pas_swd-2.pdf"]
    assert all((tmp_path / name).parent == tmp_path for name in names)


def test_gmail_label_names_resolve_and_unknown_labels_are_refused():
    labels = Recorded({"labels": [{"id": "Label_7", "name": "Klanten"}, {"id": "INBOX", "name": "INBOX"}]})
    session = FakeSession([labels, Recorded({"labelIds": ["Label_7"]})])
    GmailClient(session, sender=ACCOUNT).modify_labels("m1", ["klanten"], ["INBOX"])
    assert session.calls[-1][2]["json"] == {"addLabelIds": ["Label_7"], "removeLabelIds": ["INBOX"]}
    with pytest.raises(WorkspaceError, match="unknown Gmail label"):
        GmailClient(FakeSession([labels]), sender=ACCOUNT).modify_labels("m1", ["nope"], None)


def test_slides_move_puts_the_first_slide_at_the_requested_position():
    deck = {"slides": [{"objectId": "s1"}, {"objectId": "s2"}, {"objectId": "s3"}]}
    session = FakeSession([Recorded(deck), Recorded({})])
    SlidesClient(session).move_slides("1AAAAAAAAAAAAAAAA", ["3"], 2)
    request = session.calls[-1][2]["json"]["requests"][0]["updateSlidesPosition"]
    assert request == {"slideObjectIds": ["s3"], "insertionIndex": 1}


def test_slides_add_copies_colours_and_bullets_multiline_bodies():
    layout = {"objectId": "L1", "layoutProperties": {"displayName": "Title and body"},
              "pageElements": [
                  {"objectId": "p1", "shape": {"placeholder": {"type": "TITLE"}}},
                  {"objectId": "p2", "shape": {"placeholder": {"type": "BODY", "index": 0}}}]}
    deck = {"slides": [{"objectId": "s1"}], "layouts": [layout]}
    colors = {"pageElements": [{"shape": {"placeholder": {"type": "TITLE"}, "text": {"textElements": [
        {"textRun": {"style": {"foregroundColor": {"opaqueColor": {"rgbColor": {"red": 1}}}}}}]}}}]}
    session = FakeSession([Recorded(deck), Recorded(colors), Recorded({})])
    created = SlidesClient(session).add_slides(
        "1AAAAAAAAAAAAAAAA", [{"title": "T", "body": "een\ntwee"}], after="1",
        default_layout="Title and body", like=None)
    requests = session.calls[-1][2]["json"]["requests"]
    kinds = [next(iter(item)) for item in requests]
    assert kinds[0] == "createSlide" and "createParagraphBullets" in kinds
    assert requests[0]["createSlide"]["insertionIndex"] == 1
    assert created[0]["position"] == 2
    assert any(item.get("updateTextStyle") for item in requests)


def test_slides_image_opens_access_only_for_the_failing_create(tmp_path):
    image = tmp_path / "logo.png"
    image.write_bytes(b"\x89PNG")
    session = FakeSession([
        Recorded({"slides": [{"objectId": "s1"}]}),          # presentation
        Recorded({"parents": ["1FOLDERAAAAAAAAAA"]}),         # deck parents
        Recorded({"id": "1FILEAAAAAAAAAAAAA"}),              # upload
        Recorded(status=403, content=b"forbidden"),          # createImage attempt 1
        Recorded({"id": "perm-1"}),                          # permission
        Recorded({"replies": []}),                           # createImage attempt 2
        Recorded({}),                                        # permission delete
        Recorded({"pageElements": [{"objectId": "x", "size": {
            "width": {"magnitude": 1270000}, "height": {"magnitude": 635000}}}]}),
        Recorded({}),                                        # transform
    ])
    from gws_core.drive import DriveClient as Drive

    slides = SlidesClient(session)
    result = slides.insert_image("1AAAAAAAAAAAAAAAA", "1", drive=Drive(session), file=str(image))
    assert result["driveFileId"] == "1FILEAAAAAAAAAAAAA"
    methods = [(method, url.rsplit("/", 2)[-2:]) for method, url, _ in session.calls]
    assert ("DELETE", ["permissions", "perm-1"]) in methods


def test_gmail_fetch_retries_quota_answers_with_backoff(monkeypatch):
    from gws_core import gmail as gmail_module

    calls = []
    monkeypatch.setattr(gmail_module.time, "sleep", calls.append)
    quota = Recorded({"error": {"message": "Quota exceeded for quota metric 'Total Query Cost'"}},
                     status=403)
    session = FakeSession([quota, quota, Recorded({"id": "m1"})])
    gmail = GmailClient(session, sender=ACCOUNT)
    assert gmail._fetch_all(gmail.get, ["m1"], workers=1) == [{"id": "m1"}]
    assert calls == [2, 4]


def test_slides_image_names_the_upload_folder_when_the_deck_folder_is_unreadable(tmp_path):
    image = tmp_path / "logo.png"
    image.write_bytes(b"\x89PNG")
    session = FakeSession([
        Recorded({"slides": [{"objectId": "s1"}]}),          # presentation
        Recorded({}),                                        # deck parents: none visible
        Recorded({"id": "1FILEAAAAAAAAAAAAA"}),              # upload
        Recorded({"replies": []}),                           # createImage
        Recorded({"pageElements": []}),                      # no natural size: skip rescale
    ])
    from gws_core.drive import DriveClient as Drive

    result = SlidesClient(session).insert_image(
        "1AAAAAAAAAAAAAAAA", "1", drive=Drive(session), file=str(image))
    assert result["driveFolder"].startswith("My Drive root")


def test_slides_paragraphs_keep_bullet_nesting_and_geometry_is_in_pt():
    from gws_core.slides import element_geometry, element_paragraphs

    shape = {"shape": {"text": {"textElements": [
        {"paragraphMarker": {"bullet": {"nestingLevel": 0}}}, {"textRun": {"content": "top\n"}},
        {"paragraphMarker": {"bullet": {"nestingLevel": 1}}}, {"textRun": {"content": "nested\n"}},
    ]}}}
    assert element_paragraphs(shape) == [(0, "top"), (1, "nested")]
    image = {"image": {}, "size": {"width": {"magnitude": 12700 * 300}, "height": {"magnitude": 12700 * 100}},
             "transform": {"scaleX": 2, "scaleY": 2, "translateX": 12700 * 30, "translateY": 0}}
    assert element_geometry(image) == "600x200 pt at (30, 0)"


def test_session_keeps_a_query_string_inside_the_url():
    from gws_core.session import Session

    session = Session("token")
    recorded = []
    session._http = type("Http", (), {
        "request": lambda self, method, url, **kw: recorded.append((url, kw["params"]))
        or Recorded({})})()
    session.send("GET", "https://slides.googleapis.com/v1/presentations/p?fields=title", params={"x": "1"})
    assert recorded == [("https://slides.googleapis.com/v1/presentations/p", {"fields": "title", "x": "1"})]
