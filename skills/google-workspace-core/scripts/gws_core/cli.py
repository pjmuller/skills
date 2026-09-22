"""The one Google Workspace command surface. Account facts come from --config only."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from . import auth as auth_module
from .config import load_config
from .drive import EXPORT_MIME
from .errors import WorkspaceError
from .inputs import (extract_id, parse_json_arg, parse_values, protected_write, read_json,
                     read_requests, read_text)
from .render import out, table, trunc, write_out
from .session import Workspace
from .slides import element_kind, element_text, notes_text, placeholder_type, slide_title

HOSTS = {  # shorthand path prefix -> API host, for the generic `api` passthrough
    "/gmail/": "https://gmail.googleapis.com",
    "/drive/": "https://www.googleapis.com",
    "/upload/": "https://www.googleapis.com",
    "/v1/documents": "https://docs.googleapis.com",
    "/v1/presentations": "https://slides.googleapis.com",
    "/v4/spreadsheets": "https://sheets.googleapis.com",
}


# --- shared output helpers --------------------------------------------------

def file_rows(files: list[dict]) -> str:
    rows: list[list] = [["ID", "NAME", "TYPE", "MODIFIED"]]
    for item in files:
        rows.append([item["id"], trunc(item.get("name", ""), 60),
                     item.get("mimeType", "").replace("application/vnd.google-apps.", "g."),
                     (item.get("modifiedTime") or "")[:10]])
    return table(rows) + f"\n\n{len(files)} file(s)"


def report_replies(result: dict, as_json: bool) -> None:
    replies = [reply for reply in result.get("replies", []) if reply]
    ids = [value.get("objectId") for reply in replies for value in reply.values()
           if isinstance(value, dict) and value.get("objectId")]
    out(result, as_json, f"ok — {len(result.get('replies', []))} replies"
        + (f"; object ids: {', '.join(ids)}" if ids else ""))


def format_message(view: dict, max_chars: int, heading: bool = False) -> str:
    subject = view["headers"].get("Subject", "(no subject)")
    lines = [f"## {subject}" if heading else subject, f"id: {view['id']}", f"thread: {view['threadId']}"]
    for name, value in view["headers"].items():
        if name != "Subject":
            lines.append(f"{name}: {value}")
    if view.get("codes"):
        lines.append(f"codes: {', '.join(view['codes'])}")
    if view["attachments"]:
        lines.append("attachments:")
        for item in view["attachments"]:
            lines.append(f"- {item['filename']} ({item['mimeType']}, {item['size']} bytes, "
                         f"id={item['attachmentId'] or '-'})")
    body = view["body"]
    if len(body) > max_chars:
        body = body[:max_chars] + "\n…[truncated]"
    return "\n".join([*lines, "", body or "(no text body)"])


def alternative_html(a) -> str | None:
    """An authored HTML alternative beside an authored plain-text body."""
    return read_text(a.html_file) if a.html_file else None


def body_text(a) -> str:
    if a.body_file:
        return read_text(a.body_file)
    if a.body is None:
        raise WorkspaceError("pass --body TEXT or --body-file PATH")
    return a.body


# --- auth -------------------------------------------------------------------

def cmd_auth_mint(a, ws):
    out(auth_module.mint(ws.config, force=a.force, port=a.port), a.json,
        f"saved offline token for {ws.config.account} at {ws.config.token_path}")


def cmd_auth_configure(a, ws):
    result = auth_module.configure(ws.config, a.client_env, force=a.force)
    out(result, a.json, f"configured OAuth client at {result['configured']}")


def cmd_auth_export_env(a, ws):
    for name, value in auth_module.export_env(ws.config).items():
        print(f"{name}={value}")


def cmd_auth_export_token(a, ws):
    if not a.out and not ws.config.offline_token_file:
        raise WorkspaceError("pass --out PATH (this wrapper configures no offline_token_file)")
    written = auth_module.export_token(ws.config, Path(a.out) if a.out else ws.config.offline_token_file)
    print(f"wrote refresh token to {written}")


def cmd_doctor(a, ws):
    from .doctor import run_doctor

    raise SystemExit(run_doctor(ws.config, live=a.live, as_json=a.json))


# --- generic ----------------------------------------------------------------

def cmd_whoami(a, ws):
    facts = ws.whoami()
    out(facts, a.json, f"{facts['email']}  (token valid until {facts['token_expiry']} UTC; "
                       f"scopes: {', '.join(facts['scopes'])})")


def cmd_token(a, ws):
    print(ws.token)


def cmd_api(a, ws):
    url = a.url
    if url.startswith(("http://", "https://")):
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or parsed.port not in (None, 443) or not (
                host == "www.googleapis.com" or host.endswith(".googleapis.com")):
            raise WorkspaceError("absolute api URLs must be HTTPS on a *.googleapis.com host")
    else:
        url = next((h for prefix, h in HOSTS.items() if url.startswith(prefix)),
                   "https://www.googleapis.com") + url
    params = dict(item.partition("=")[::2] for item in (a.param or []))
    kw: dict = {"params": params}
    if a.body:
        kw["json"] = read_json(a.body)
    out(ws.api(a.method, url, **kw), True)


# --- drive ------------------------------------------------------------------

def cmd_drive_list(a, ws):
    files = ws.drive.list_folder(a.folder, a.max)
    out(files, a.json, file_rows(files))


def cmd_drive_search(a, ws):
    files = ws.drive.search(a.query, a.max)
    out(files, a.json, file_rows(files))


def cmd_drive_get(a, ws):
    item = ws.drive.get(a.file)
    out(item, a.json, "\n".join(f"{k}: {v}" for k, v in item.items() if k != "owners"))


def cmd_drive_create(a, ws):
    item = ws.drive.create(a.name, a.mime, a.parent)
    out(item, a.json, f"created -> {item['id']}  {item['name']}\n{item.get('webViewLink')}")


def cmd_drive_copy(a, ws):
    item = ws.drive.copy(a.file, a.name, a.parent)
    out(item, a.json, f"copied -> {item['id']}  {item['name']}\n{item.get('webViewLink')}")


def cmd_drive_upload(a, ws):
    item = ws.drive.upload(a.file, a.name, a.parent, a.mime)
    out(item, a.json, f"uploaded -> {item['id']}  {item['name']}\n{item.get('webViewLink')}")


def cmd_drive_replace(a, ws):
    item = ws.drive.replace_content(a.file, a.local, a.mime)
    out(item, a.json, f"replaced content of {item['id']}  {item['name']}")


def cmd_drive_trash(a, ws):
    item = ws.drive.trash(a.file)
    out(item, a.json, f"trashed {item['id']}  {item['name']}")


def cmd_drive_download(a, ws):
    content = ws.drive.download(a.file)
    out({"id": extract_id(a.file), "out": a.out, "bytes": len(content)}, a.json,
        f"downloaded -> {write_out(a.out, content)}")


def cmd_drive_export(a, ws):
    content = ws.drive.export(a.file, a.format)
    out({"id": extract_id(a.file), "out": a.out, "bytes": len(content)}, a.json,
        f"exported -> {write_out(a.out, content)}")


# --- docs -------------------------------------------------------------------

def cmd_doc_read(a, ws):
    metadata, markdown = ws.drive.export_markdown(a.doc)
    if not a.out:
        sys.stdout.write(markdown)
        return
    written = protected_write(Path(a.out), markdown, a.force)
    out({"id": metadata.get("id"), "name": metadata.get("name"), "output": str(written),
         "characters": len(markdown)}, a.json, f"wrote {written} ({len(markdown)} chars)")


def cmd_doc_outline(a, ws):
    doc = ws.docs.outline(a.doc)
    rows: list[list] = [["RANGE", "STYLE", "TEXT"]]
    for element in doc.get("body", {}).get("content", []):
        span = f"{element.get('startIndex', 0)}-{element.get('endIndex', 0)}"
        if "paragraph" in element:
            paragraph = element["paragraph"]
            style = paragraph.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
            if paragraph.get("bullet"):
                style += "+bullet"
            bits = []
            for item in paragraph.get("elements", []):
                if "textRun" in item:
                    bits.append(item["textRun"].get("content", ""))
                elif "inlineObjectElement" in item:
                    bits.append(f"<image {item['inlineObjectElement'].get('inlineObjectId')}>")
                elif "pageBreak" in item:
                    bits.append("<page-break>")
            rows.append([span, style, trunc("".join(bits), 80)])
        elif "table" in element:
            rows.append([span, f"table {element['table'].get('rows')}x{element['table'].get('columns')}", ""])
        else:
            rows.append([span, next(iter(set(element) - {"startIndex", "endIndex"}), "?"), ""])
    out(doc.get("body", {}).get("content", []), a.json,
        f"{doc.get('title')}  (rev {doc.get('revisionId')})\n" + table(rows))


def cmd_doc_replace(a, ws):
    result = ws.docs.replace_text(a.doc, a.find, a.replace, match_case=a.match_case)
    changed = result["replies"][0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    out(result, a.json, f"replaced {changed} occurrence(s)")


def cmd_doc_insert(a, ws):
    result = ws.docs.insert_text(a.doc, a.text, index=a.index, end=a.end)
    out(result, a.json, f"inserted {len(a.text)} chars")


def cmd_doc_batch(a, ws):
    body = read_requests(a.body)
    report_replies(ws.docs.batch(a.doc, body), a.json)


# --- sheets -----------------------------------------------------------------

def cmd_sheet_meta(a, ws):
    data = ws.sheets.meta(a.sheet)
    rows: list[list] = [["TAB", "SHEET_ID", "ROWS", "COLS"]]
    for tab in data.get("sheets", []):
        properties = tab["properties"]
        grid = properties.get("gridProperties", {})
        rows.append([properties["title"], properties["sheetId"],
                     grid.get("rowCount"), grid.get("columnCount")])
    out(data, a.json, f"{data['properties']['title']}  ({data['spreadsheetId']})\n" + table(rows))


def cmd_sheet_read(a, ws):
    data = ws.sheets.read(a.sheet, a.range)
    values = data.get("values", [])
    out(data, a.json, f"{data.get('range')}\n"
        + table([[trunc(str(cell), 40) for cell in row] for row in values])
        + f"\n\n{len(values)} row(s)")


def cmd_sheet_write(a, ws):
    values = parse_values(a.values, a.csv)  # validate arguments before authenticating
    result = ws.sheets.write(a.sheet, a.range, values, raw=a.raw)
    out(result, a.json, f"wrote {result.get('updatedCells')} cell(s) in {result.get('updatedRange')}")


def cmd_sheet_append(a, ws):
    values = parse_values(a.values, a.csv)  # validate arguments before authenticating
    result = ws.sheets.append(a.sheet, a.range, values)
    updates = result.get("updates", {})
    out(result, a.json, f"appended {updates.get('updatedRows')} row(s) at {updates.get('updatedRange')}")


def cmd_sheet_clear(a, ws):
    result = ws.sheets.clear(a.sheet, a.range)
    out(result, a.json, f"cleared {result.get('clearedRange')}")


def cmd_sheet_batch_clear(a, ws):
    ranges = parse_json_arg(a.ranges, "ranges")
    result = ws.sheets.batch_clear(a.sheet, ranges)
    out(result, a.json, f"cleared {len(result.get('clearedRanges', []))} range(s)")


def cmd_sheet_batch_write(a, ws):
    updates = parse_json_arg(a.updates, "updates")
    result = ws.sheets.batch_write(a.sheet, updates)
    out(result, a.json, f"wrote {result.get('totalUpdatedCells')} cell(s) in "
                        f"{result.get('totalUpdatedSheets')} tab(s)")


def cmd_sheet_batch(a, ws):
    body = read_requests(a.body)
    report_replies(ws.sheets.batch(a.sheet, body), a.json)


def cmd_sheet_add_tab(a, ws):
    result = ws.sheets.add_tab(a.sheet, a.title)
    properties = result["replies"][0]["addSheet"]["properties"]
    out(result, a.json, f"added tab {properties['title']} (sheetId {properties['sheetId']})")


def cmd_sheet_delete_rows(a, ws):
    result = ws.sheets.delete_rows(a.sheet, a.tab_sheet_id, a.start_row, a.end_row)
    out(result, a.json, f"deleted rows {a.start_row}-{a.end_row} on tab {a.tab_sheet_id}")


def cmd_sheet_freeze_rows(a, ws):
    result = ws.sheets.freeze_rows(a.sheet, a.tab_sheet_id, a.rows)
    out(result, a.json, f"froze {a.rows} row(s) on tab {a.tab_sheet_id}")


def cmd_sheet_format_rows(a, ws):
    result = ws.sheets.format_rows(a.sheet, a.tab_sheet_id, a.row_count, a.col_count,
                                   pixel_size=a.height)
    out(result, a.json, f"formatted {a.row_count}x{a.col_count} on tab {a.tab_sheet_id}")


def cmd_sheet_named_ranges(a, ws):
    ranges = ws.sheets.named_ranges(a.sheet)
    out(ranges, a.json, table([["NAME", "RANGE"]] + [[r["name"], r["range"]] for r in ranges]))


def cmd_sheet_add_named_range(a, ws):
    result = ws.sheets.add_named_range(a.sheet, a.name, a.tab_sheet_id, a.a1_cell)
    out(result, a.json, f"named range {a.name} -> tab {a.tab_sheet_id} {a.a1_cell}")


def cmd_sheet_tables(a, ws):
    tables = ws.sheets.tables(a.sheet)
    out(tables, a.json, table([["ID", "NAME", "RANGE", "COLUMNS"]]
        + [[t["id"], t["name"], t["range"], ", ".join(t["columns"])] for t in tables]))


def cmd_table_read(a, ws):
    rows = ws.sheets.read_table(a.sheet, a.table)
    out(rows, True)


def cmd_table_append(a, ws):
    rows = parse_json_arg(a.rows, "rows")
    result = ws.sheets.append_table(a.sheet, a.table, rows)
    out(result, a.json, f"appended {len(rows)} row(s) to {a.table}")


def cmd_table_rename(a, ws):
    result = ws.sheets.rename_table(a.sheet, a.table, a.new_name)
    out(result, a.json, f"renamed table {a.table} -> {a.new_name}")


# --- gmail ------------------------------------------------------------------

def cmd_gmail_search(a, ws):
    messages = ws.gmail.search(a.query, a.max)
    rows: list[list] = [["DATE", "FROM", "SUBJECT", "ID"]]
    for item in messages:
        rows.append([trunc(item["date"], 28), trunc(item["from"], 42),
                     trunc(item["subject"], 70), item["id"]])
    out(messages, a.json, table(rows) + f"\n\n{len(messages)} message(s)")


def cmd_gmail_export(a, ws):
    result = ws.gmail.export(a.query, a.out, limit=a.max, by_thread=a.by_thread,
                             trim=not a.full, attachments=a.attachments)
    human = (f"wrote {result['written']} file(s), {result['skipped']} already present "
             f"-> {result['dir']}\nindex: {result['index']}")
    if result["errors"]:
        human += (f"\n{len(result['errors'])} fetch(es) failed; rerun the same command to retry them:"
                  + "".join(f"\n  {e['id']}: {trunc(e['error'], 160)}" for e in result["errors"][:5])
                  + ("\n  …" if len(result["errors"]) > 5 else ""))
    out(result, a.json, human)


def cmd_gmail_get(a, ws):
    message = ws.gmail.get(a.id)
    out(message, a.json, format_message(ws.gmail.view(message, trim=not a.full), a.max_chars))


def cmd_gmail_thread(a, ws):
    thread = ws.gmail.thread(a.id)
    views = [ws.gmail.view(message, trim=not a.full) for message in thread.get("messages", [])]
    human = "\n\n---\n\n".join(format_message(view, a.max_chars, heading=True) for view in views)
    out(thread, a.json, human or "(empty thread)")


def cmd_gmail_recent(a, ws):
    views = ws.gmail.recent(a.word, minutes=a.minutes, limit=a.max, codes=not a.no_codes)
    human = "\n\n---\n\n".join(format_message(view, a.max_chars, heading=True) for view in views)
    out(views, a.json, human or f"no mail matching {a.word!r} in the last {a.minutes} minute(s)")


def cmd_gmail_draft(a, ws):
    body, html_body = body_text(a), alternative_html(a)
    draft = ws.gmail.create_draft(a.to, a.subject, body, cc=a.cc, html=a.html,
                                  html_body=html_body, reply_to_message=a.reply_to_message)
    message = draft.get("message") or {}
    out(draft, a.json, f"draft created: {draft['id']}  message={message.get('id')}  "
                       f"thread={message.get('threadId')}")


def cmd_gmail_send(a, ws):
    body, html_body = body_text(a), alternative_html(a)
    sent = ws.gmail.send(a.to, a.subject, body, cc=a.cc, html=a.html,
                         html_body=html_body, reply_to_message=a.reply_to_message)
    out(sent, a.json, f"sent {sent.get('id')} (thread {sent.get('threadId')})")


def cmd_gmail_draft_list(a, ws):
    drafts = ws.gmail.drafts(a.max)
    out(drafts, a.json, table([["DRAFT_ID", "MESSAGE_ID"]]
        + [[d.get("id"), (d.get("message") or {}).get("id", "")] for d in drafts])
        + f"\n\n{len(drafts)} draft(s)")


def cmd_gmail_draft_get(a, ws):
    draft = ws.gmail.get_draft(a.id)
    out(draft, a.json, f"draft {draft['id']}\n" + format_message(draft["message"], a.max_chars))


def cmd_gmail_draft_send(a, ws):
    sent = ws.gmail.send_draft(a.id)
    out(sent, a.json, f"sent draft {a.id} as message {sent.get('id')}")


def cmd_gmail_draft_delete(a, ws):
    out(ws.gmail.delete_draft(a.id), a.json, f"deleted draft {a.id}")


def cmd_gmail_labels(a, ws):
    labels = sorted(ws.gmail.labels(),
                    key=lambda item: (item.get("type", ""), item.get("name", "").casefold()))
    out(labels, a.json, table([["ID", "NAME", "TYPE"]]
        + [[item.get("id", ""), item.get("name", ""), item.get("type", "")] for item in labels]))


def cmd_gmail_label(a, ws):
    result = ws.gmail.modify_labels(a.id, a.add, a.remove)
    out(result, a.json, f"updated {a.id}: labels now {', '.join(result.get('labelIds', []))}")


def cmd_gmail_attachments(a, ws):
    saved = ws.gmail.download_files(a.id, a.out)
    out(saved, a.json, "\n".join(f"{item['path']}  ({item['size']} bytes)" for item in saved)
        or "(no file parts)")


def cmd_gmail_save_text(a, ws):
    result = ws.gmail.save_text(a.id, a.out)
    out(result, a.json, f"wrote {result['path']} ({result['size']} bytes)")


# --- slides -----------------------------------------------------------------

def cmd_slides_outline(a, ws):
    deck = ws.slides.outline(a.pres)
    layouts = {item["objectId"]: item.get("layoutProperties", {}).get("displayName", "?")
               for item in deck.get("layouts", [])}
    rows: list[list] = [["#", "OBJECT_ID", "LAYOUT", "EL", "TITLE / FIRST TEXT", "NOTES"]]
    for index, slide in enumerate(deck.get("slides", []), 1):
        layout = layouts.get((slide.get("slideProperties") or {}).get("layoutObjectId"), "-")
        rows.append([index, slide["objectId"], trunc(layout, 22), len(slide.get("pageElements", [])),
                     trunc(slide_title(slide), 60), trunc(notes_text(slide), 24)])
    out(deck.get("slides", []), a.json,
        f"{deck.get('title')}  ({deck.get('presentationId')})  {len(deck.get('slides', []))} slides\n"
        + table(rows))


def cmd_slides_slide(a, ws):
    deck = ws.slides.presentation(
        a.pres, "presentationId,title,slides(objectId),layouts(objectId,layoutProperties.displayName)")
    index, stub = ws.slides.resolve(deck, a.slide)
    page = ws.slides.page(a.pres, stub["objectId"])
    if a.json:
        return out(page, True)
    layouts = {item["objectId"]: item.get("layoutProperties", {}).get("displayName", "?")
               for item in deck.get("layouts", [])}
    layout = layouts.get((page.get("slideProperties") or {}).get("layoutObjectId"), "-")
    print(f"slide {index}  objectId={page['objectId']}  layout={layout}  "
          f"elements={len(page.get('pageElements', []))}")
    for element in page.get("pageElements", []):
        placeholder = ((element.get("shape") or {}).get("placeholder") or {})
        # `type` is omitted from the JSON when it is the NONE default (inherited placeholders)
        label = ""
        if placeholder:
            label = f" placeholder={placeholder.get('type', 'NONE')}" + (
                f"#{placeholder['index']}" if placeholder.get("index") else "")
        print(f"\n  [{element['objectId']}] {element_kind(element)}{label}")
        if "table" in element:
            grid = element["table"]
            print(f"    table {grid.get('rows')}x{grid.get('columns')}")
            for row in grid.get("tableRows", []):
                cells = ["".join((item.get("textRun") or {}).get("content", "")
                                 for item in (cell.get("text") or {}).get("textElements", [])).strip()
                         for cell in row.get("tableCells", [])]
                print("    | " + " | ".join(trunc(cell, 30) for cell in cells))
            continue
        if "image" in element:
            print(f"    contentUrl: {element['image'].get('contentUrl', '')[:160]}")
        text = element_text(element).replace("\v", "\n").rstrip()
        if text:
            body = text if len(text) <= a.max_chars else text[: a.max_chars] + "\n    …[truncated]"
            print("\n".join(f"    {line}" for line in body.split("\n")))
    notes = (page.get("slideProperties") or {}).get("notesPage") or {}
    notes_id = (notes.get("notesProperties") or {}).get("speakerNotesObjectId")
    print(f"\n  notes [{notes_id}]: {notes_text(page) or '(none)'}")


def cmd_slides_text(a, ws):
    deck = ws.slides.presentation(
        a.pres, "title,slides(objectId,pageElements,slideProperties.notesPage(pageElements))")
    slides = deck.get("slides", [])
    start, end = a.from_ or 1, a.to or len(slides)
    lines = [f"# {deck.get('title')}", ""]
    for index, slide in enumerate(slides[start - 1:end], start):
        lines.append(f"## Slide {index} — {slide_title(slide) or '(no title)'}   `{slide['objectId']}`")
        for element in slide.get("pageElements", []):
            if placeholder_type(element) == "SLIDE_NUMBER":
                continue
            text = element_text(element).replace("\v", "\n").strip()
            lines += [f"- {line.strip()}" for line in text.split("\n") if line.strip()]
        notes = notes_text(slide)
        if notes:
            lines.append(f"> notes: {notes}")
        lines.append("")
    body = "\n".join(lines)
    print(f"wrote {write_out(a.out, body)}" if a.out else body)


def cmd_slides_replace(a, ws):
    result = ws.slides.replace_text(a.pres, a.find, a.replace, slides=a.slides,
                                    match_case=a.match_case)
    changed = result["replies"][0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    out(result, a.json, f"replaced {changed} occurrence(s)")


def cmd_slides_set_text(a, ws):
    result = ws.slides.set_text(a.pres, a.element, a.text)
    out(result, a.json, f"set text on {a.element} ({len(a.text)} chars)")


def cmd_slides_batch(a, ws):
    body = read_requests(a.body)
    report_replies(ws.slides.batch(a.pres, body), a.json)


def cmd_slides_add(a, ws):
    if a.spec:
        specs = read_json(a.spec)
        specs = [specs] if isinstance(specs, dict) else specs
    else:
        if not (a.title or a.body):
            raise WorkspaceError("pass --title/--body or --spec FILE")
        specs = [{"layout": a.layout, "title": a.title, "body": a.body, "notes": a.notes}]
    created = ws.slides.add_slides(a.pres, specs, after=a.after, default_layout=a.layout, like=a.like)
    out(created, a.json, "\n".join(
        f"slide {item['position']}  {item['objectId']}  {trunc(item.get('title') or '', 60)}"
        for item in created))


def cmd_slides_notes(a, ws):
    deck = ws.slides.presentation(a.pres, "slides(objectId)")
    index, slide = ws.slides.resolve(deck, a.slide)
    ws.slides.set_notes(a.pres, slide["objectId"], a.text or "")
    out({"slide": index, "objectId": slide["objectId"]}, a.json,
        f"notes set on slide {index} ({len(a.text or '')} chars)")


def cmd_slides_delete(a, ws):
    deck = ws.slides.presentation(a.pres, "slides(objectId)")
    targets = [ws.slides.resolve(deck, ref) for ref in a.slides]
    if not a.yes:
        listing = ", ".join(f"{index} ({slide['objectId']})" for index, slide in targets)
        raise WorkspaceError(f"refusing without --yes: would delete slide(s) {listing}")
    deleted = ws.slides.delete_slides(a.pres, a.slides)
    out(deleted, a.json, f"deleted {len(deleted)} slide(s)")


def cmd_slides_move(a, ws):
    moved = ws.slides.move_slides(a.pres, a.slides, a.to)
    out({"moved": moved, "to": a.to}, a.json, f"moved {len(moved)} slide(s) to position {a.to}")


def cmd_slides_image(a, ws):
    result = ws.slides.insert_image(a.pres, a.slide, drive=ws.drive, url=a.url, file=a.file,
                                    x=a.x, y=a.y, width=a.w, height=a.h, name=a.name, parent=a.parent)
    out(result, a.json, f"image {result['objectId']} on slide {result['slide']}"
        + (f" (drive file {result['driveFileId']})" if result["driveFileId"] else ""))


def cmd_slides_thumbnail(a, ws):
    index, object_id, png = ws.slides.thumbnail(a.pres, a.slide)
    out({"slide": index, "objectId": object_id, "out": a.out}, a.json,
        f"slide {index} -> {write_out(a.out, png)}")


def cmd_slides_export_pdf(a, ws):
    content = ws.slides.export_pdf(a.pres)
    out({"out": a.out, "bytes": len(content)}, a.json, f"exported -> {write_out(a.out, content)}")


# --- parser -----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """The full command surface. Built without reading config, so --help always works."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS, metavar="PATH",
                        help="wrapper workspace.json (default: $GWS_CONFIG)")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="raw API JSON instead of compact text")

    parser = argparse.ArgumentParser(
        prog="gws.py", parents=[common],
        description="Google Workspace CLI (Drive, Docs, Sheets, Slides, Gmail). "
                    "The account, scopes and credential locations come from --config.")
    sub = parser.add_subparsers(
        dest="cmd", required=True,
        parser_class=lambda **kw: argparse.ArgumentParser(parents=[common], **kw))

    def add(name: str, fn, help_: str):
        command = sub.add_parser(name, help=help_, description=help_)
        command.set_defaults(fn=fn)
        return command

    # auth
    auth = sub.add_parser("auth", help="explicit consent and credential provisioning",
                          description="Explicit consent and credential provisioning. "
                                      "Data commands never open a browser.")
    auth_sub = auth.add_subparsers(
        dest="auth_cmd", required=True,
        parser_class=lambda **kw: argparse.ArgumentParser(parents=[common], **kw))

    command = auth_sub.add_parser("mint", help="browser consent; writes the offline token")
    command.set_defaults(fn=cmd_auth_mint)
    command.add_argument("--force", action="store_true", help="replace an existing token")
    command.add_argument("--port", type=int, default=0, help="redirect port (default: random free)")

    command = auth_sub.add_parser("configure", help="import an installed-app OAuth client from a .env")
    command.set_defaults(fn=cmd_auth_configure)
    command.add_argument("--client-env", required=True)
    command.add_argument("--force", action="store_true")

    command = auth_sub.add_parser(
        "export-env", help="print the cloud GWS_* triplet (SECRETS: never log or paste)")
    command.set_defaults(fn=cmd_auth_export_env)

    command = auth_sub.add_parser(
        "export-token", help="write the refresh token to a file (SECRET: for provisioning only)")
    command.set_defaults(fn=cmd_auth_export_token)
    command.add_argument("-o", "--out", help="destination path")

    command = add("doctor", cmd_doctor, "secret-safe credential diagnostics for this config")
    command.add_argument("--live", action="store_true",
                         help="refresh in memory and verify the account after offline checks pass")

    # generic
    add("whoami", cmd_whoami, "show the authenticated Google account and granted scopes")
    add("token", cmd_token, "print the short-lived access token (for ad-hoc curl)")

    command = add("api", cmd_api, "authenticated raw call; path may be a full URL or /drive/v3/files")
    command.add_argument("method")
    command.add_argument("url")
    command.add_argument("--body", help="JSON request body: FILE or - for stdin")
    command.add_argument("--param", action="append", metavar="k=v", help="query parameter (repeatable)")

    # drive
    command = add("drive-list", cmd_drive_list, "list a Drive folder")
    command.add_argument("folder")
    command.add_argument("-n", "--max", type=int, default=100)

    command = add("drive-search", cmd_drive_search, "search Drive (Drive query syntax)")
    command.add_argument("query")
    command.add_argument("-n", "--max", type=int, default=50)

    command = add("drive-get", cmd_drive_get, "file metadata")
    command.add_argument("file")

    command = add("drive-create", cmd_drive_create, "create an empty file or folder (metadata only)")
    command.add_argument("name")
    command.add_argument("mime", help="e.g. application/vnd.google-apps.spreadsheet")
    command.add_argument("--parent", help="target folder id/url")

    command = add("drive-copy", cmd_drive_copy, "copy a file (use before risky bulk edits)")
    command.add_argument("file")
    command.add_argument("--name", required=True)
    command.add_argument("--parent", help="target folder id/url (default: same parents)")

    command = add("drive-upload", cmd_drive_upload, "upload a local file to Drive")
    command.add_argument("file", help="local path")
    command.add_argument("--name", help="Drive name (default: the file name)")
    command.add_argument("--parent", help="target folder id/url (default: My Drive root)")
    command.add_argument("--mime", help="MIME type (default: guessed)")

    command = add("drive-replace", cmd_drive_replace, "overwrite an existing file's bytes")
    command.add_argument("file", help="Drive file id/url")
    command.add_argument("local", help="local path with the new content")
    command.add_argument("--mime", help="MIME type (default: guessed)")

    command = add("drive-trash", cmd_drive_trash, "move a file to the trash (never permanent)")
    command.add_argument("file")

    command = add("drive-download", cmd_drive_download, "download a binary file's content")
    command.add_argument("file")
    command.add_argument("-o", "--out", required=True)

    command = add("drive-export", cmd_drive_export, "export a Google file to a local path")
    command.add_argument("file")
    command.add_argument("--format", required=True, help="/".join(sorted(EXPORT_MIME)))
    command.add_argument("-o", "--out", required=True)

    # docs
    command = add("doc-read", cmd_doc_read, "export a Google Doc as Markdown")
    command.add_argument("doc")
    command.add_argument("-o", "--out", help="write to a file instead of stdout")
    command.add_argument("--force", action="store_true", help="replace an existing output file")

    command = add("doc-outline", cmd_doc_outline, "structural elements with indexes (find edit positions)")
    command.add_argument("doc")

    command = add("doc-replace", cmd_doc_replace, "replaceAllText in a Doc")
    command.add_argument("doc")
    command.add_argument("--find", required=True)
    command.add_argument("--replace", required=True)
    command.add_argument("--match-case", action="store_true")

    command = add("doc-insert", cmd_doc_insert, "insert text at an index or at the end")
    command.add_argument("doc")
    command.add_argument("--text", required=True)
    command.add_argument("--index", type=int)
    command.add_argument("--end", action="store_true")

    command = add("doc-batch", cmd_doc_batch, "raw documents.batchUpdate")
    command.add_argument("doc")
    command.add_argument("--body", required=True, help="FILE or -")

    # sheets
    command = add("sheet-meta", cmd_sheet_meta, "spreadsheet + tab metadata")
    command.add_argument("sheet")

    command = add("sheet-read", cmd_sheet_read, "read an A1 range")
    command.add_argument("sheet")
    command.add_argument("range")

    command = add("sheet-write", cmd_sheet_write, "write an A1 range")
    command.add_argument("sheet")
    command.add_argument("range")
    command.add_argument("--values", help="JSON array of arrays")
    command.add_argument("--csv", help="CSV file instead of --values")
    command.add_argument("--raw", action="store_true", help="RAW input (default: USER_ENTERED)")

    command = add("sheet-append", cmd_sheet_append, "append rows below a tab's data")
    command.add_argument("sheet")
    command.add_argument("range", help="tab name or A1 range")
    command.add_argument("--values")
    command.add_argument("--csv")

    command = add("sheet-clear", cmd_sheet_clear, "clear the values in an A1 range")
    command.add_argument("sheet")
    command.add_argument("range")

    command = add("sheet-batch-clear", cmd_sheet_batch_clear, "clear many ranges in one call")
    command.add_argument("sheet")
    command.add_argument("ranges", help='JSON list, e.g. \'["Tab!A1:B2","named_range"]\'')

    command = add("sheet-batch-write", cmd_sheet_batch_write, "write many ranges in one call")
    command.add_argument("sheet")
    command.add_argument("updates", help='JSON dict, e.g. \'{"Tab!A1":[["x"]]}\'')

    command = add("sheet-batch", cmd_sheet_batch, "raw spreadsheets.batchUpdate")
    command.add_argument("sheet")
    command.add_argument("--body", required=True, help="FILE or -")

    command = add("sheet-add-tab", cmd_sheet_add_tab, "create a new tab")
    command.add_argument("sheet")
    command.add_argument("title")

    command = add("sheet-delete-rows", cmd_sheet_delete_rows,
                  "delete rows from a tab (1-based, inclusive); shrinks a native Table")
    command.add_argument("sheet")
    command.add_argument("tab_sheet_id", type=int, help="numeric sheetId of the tab (see sheet-meta)")
    command.add_argument("start_row", type=int)
    command.add_argument("end_row", type=int)

    command = add("sheet-freeze-rows", cmd_sheet_freeze_rows, "freeze the top rows of a tab")
    command.add_argument("sheet")
    command.add_argument("tab_sheet_id", type=int)
    command.add_argument("--rows", type=int, default=1)

    command = add("sheet-format-rows", cmd_sheet_format_rows,
                  "clip cell text and reset row heights for dense dumps")
    command.add_argument("sheet")
    command.add_argument("tab_sheet_id", type=int)
    command.add_argument("row_count", type=int)
    command.add_argument("col_count", type=int)
    command.add_argument("--height", type=int, default=21)

    command = add("sheet-named-ranges", cmd_sheet_named_ranges, "list named ranges as name + A1")
    command.add_argument("sheet")

    command = add("sheet-add-named-range", cmd_sheet_add_named_range,
                  "create a single-cell named range")
    command.add_argument("sheet")
    command.add_argument("name")
    command.add_argument("tab_sheet_id", type=int)
    command.add_argument("a1_cell", help="plain A1 without a tab prefix, e.g. D4")

    command = add("sheet-tables", cmd_sheet_tables, "list native Sheets Tables")
    command.add_argument("sheet")

    command = add("table-read", cmd_table_read, "read a native Table as JSON rows (header skipped)")
    command.add_argument("sheet")
    command.add_argument("table", help="table name or tableId")

    command = add("table-append", cmd_table_append, "append dict rows to a native Table")
    command.add_argument("sheet")
    command.add_argument("table")
    command.add_argument("rows", help='JSON list of objects, e.g. \'[{"col":"v"}]\'')

    command = add("table-rename", cmd_table_rename, "rename a native Table (columns untouched)")
    command.add_argument("sheet")
    command.add_argument("table")
    command.add_argument("new_name")

    # gmail
    command = add("gmail-search", cmd_gmail_search, "search Gmail; one compact line per message")
    command.add_argument("query", help="Gmail search query")
    command.add_argument("-n", "--max", type=int, default=25,
                         help="(paginates; up to 500 per page)")

    command = add("gmail-export", cmd_gmail_export,
                  "write matching mail as markdown files in a directory, for grepping")
    command.add_argument("query", help="Gmail search query")
    command.add_argument("-o", "--out", required=True, help="output directory")
    command.add_argument("-n", "--max", type=int, default=100)
    command.add_argument("--by-thread", action="store_true", help="one file per thread")
    command.add_argument("--full", action="store_true", help="keep quoted chains and signatures")
    command.add_argument("--attachments", action="store_true",
                         help="also download file parts to <dir>/files/<messageId>/")

    command = add("gmail-get", cmd_gmail_get, "message headers, body text and attachment index")
    command.add_argument("id", help="message id")
    command.add_argument("--max-chars", type=int, default=12000)
    command.add_argument("--full", action="store_true", help="keep quoted chains and signatures")

    command = add("gmail-thread", cmd_gmail_thread, "all messages in a thread")
    command.add_argument("id", help="thread id")
    command.add_argument("--max-chars", type=int, default=12000)
    command.add_argument("--full", action="store_true")

    command = add("gmail-recent", cmd_gmail_recent,
                  "mail containing WORD in the last N minutes, with extracted one-time codes")
    command.add_argument("word", help="Gmail search term; quote a multi-word phrase")
    command.add_argument("--minutes", type=int, default=5)
    command.add_argument("-n", "--max", type=int, default=5)
    command.add_argument("--max-chars", type=int, default=4000)
    command.add_argument("--no-codes", action="store_true")

    def compose(command):
        command.add_argument("--to", required=True)
        command.add_argument("--cc")
        command.add_argument("--subject", required=True)
        body = command.add_mutually_exclusive_group(required=True)
        body.add_argument("--body", help="message body text")
        body.add_argument("--body-file", help="read the body from a UTF-8 file, or - for stdin")
        alternative = command.add_mutually_exclusive_group()
        alternative.add_argument("--html", action="store_true",
                                 help="the body is HTML; a plain-text alternative is generated")
        alternative.add_argument("--html-file",
                                 help="keep the body as plain text and attach this HTML alternative")
        command.add_argument("--reply-to-message",
                             help="message id to thread and quote; subject must match")
        return command

    compose(add("gmail-draft", cmd_gmail_draft, "create a draft (never sends)"))
    compose(add("gmail-send", cmd_gmail_send, "send a mail immediately (not idempotent)"))

    command = add("gmail-draft-list", cmd_gmail_draft_list, "list drafts")
    command.add_argument("-n", "--max", type=int, default=20)

    command = add("gmail-draft-get", cmd_gmail_draft_get, "read one draft")
    command.add_argument("id", help="draft id")
    command.add_argument("--max-chars", type=int, default=12000)

    command = add("gmail-draft-send", cmd_gmail_draft_send, "send an existing draft by id")
    command.add_argument("id", help="draft id")

    command = add("gmail-draft-delete", cmd_gmail_draft_delete, "delete a draft by id")
    command.add_argument("id", help="draft id")

    add("gmail-labels", cmd_gmail_labels, "list Gmail labels and ids")

    command = add("gmail-label", cmd_gmail_label, "add/remove labels on a message")
    command.add_argument("id", help="message id")
    command.add_argument("--add", action="append", help="label id/name (repeatable or comma-separated)")
    command.add_argument("--remove", action="append", help="label id/name (repeatable or comma-separated)")

    command = add("gmail-attachments", cmd_gmail_attachments,
                  "download the file parts of one message")
    command.add_argument("id", help="message id")
    command.add_argument("-o", "--out", required=True, help="output directory")

    command = add("gmail-save-text", cmd_gmail_save_text,
                  "save headers and the complete readable body to a file")
    command.add_argument("id", help="message id")
    command.add_argument("-o", "--out", required=True)

    # slides
    command = add("slides-outline", cmd_slides_outline, "one compact line per slide")
    command.add_argument("pres")

    command = add("slides-slide", cmd_slides_slide, "every element + notes of one slide")
    command.add_argument("pres")
    command.add_argument("slide", help="1-based slide number or objectId")
    command.add_argument("--max-chars", type=int, default=2000)

    command = add("slides-text", cmd_slides_text, "markdown-ish dump of all slide text")
    command.add_argument("pres")
    command.add_argument("--from", dest="from_", type=int)
    command.add_argument("--to", type=int)
    command.add_argument("-o", "--out")

    command = add("slides-replace", cmd_slides_replace, "replaceAllText across (some) slides")
    command.add_argument("pres")
    command.add_argument("--find", required=True)
    command.add_argument("--replace", required=True)
    command.add_argument("--slides", help="comma-separated slide objectIds (default: whole deck)")
    command.add_argument("--match-case", action="store_true")

    command = add("slides-set-text", cmd_slides_set_text,
                  "replace a shape's whole text (styling is lost)")
    command.add_argument("pres")
    command.add_argument("element", help="page element objectId (see slides-slide)")
    command.add_argument("--text", required=True)

    command = add("slides-batch", cmd_slides_batch, "raw presentations.batchUpdate")
    command.add_argument("pres")
    command.add_argument("--body", required=True, help="FILE or -")

    command = add("slides-add", cmd_slides_add,
                  "insert slide(s); --spec = JSON list of {layout,title,body,notes}")
    command.add_argument("pres")
    command.add_argument("--after", help="1-based slide number or objectId; default: end of deck")
    command.add_argument("--layout", default="Title and body",
                         help="layout display name / API name / id")
    command.add_argument("--title")
    command.add_argument("--body", help="lines become bullets; leading tabs nest")
    command.add_argument("--notes", help="speaker notes")
    command.add_argument("--spec", help="JSON FILE or - : one object or a list, inserted in order")
    command.add_argument("--like", help="copy title/body colours from this slide "
                                        "(default: the --after slide; 'none' to skip)")

    command = add("slides-notes", cmd_slides_notes, "replace a slide's speaker notes")
    command.add_argument("pres")
    command.add_argument("slide", help="1-based slide number or objectId")
    command.add_argument("--text", required=True, help="new notes ('' clears)")

    command = add("slides-delete", cmd_slides_delete, "delete slide(s) (needs --yes)")
    command.add_argument("pres")
    command.add_argument("slides", nargs="+", help="1-based numbers or objectIds")
    command.add_argument("--yes", action="store_true")

    command = add("slides-move", cmd_slides_move, "move slide(s) so the first becomes slide N")
    command.add_argument("pres")
    command.add_argument("slides", nargs="+", help="1-based numbers or objectIds")
    command.add_argument("--to", type=int, required=True, help="target 1-based position")

    command = add("slides-image", cmd_slides_image, "insert an image (local file or public URL)")
    command.add_argument("pres")
    command.add_argument("slide", help="1-based slide number or objectId")
    source = command.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="local image; uploaded to Drive first")
    source.add_argument("--url", help="publicly fetchable image URL")
    command.add_argument("--x", type=float, default=30, help="left offset in pt (slide is 720x405 pt)")
    command.add_argument("--y", type=float, default=110, help="top offset in pt")
    command.add_argument("--w", type=float, help="width in pt (default 660 if no --h)")
    command.add_argument("--h", type=float, help="height in pt; give one of --w/--h to keep the ratio")
    command.add_argument("--name", help="Drive name for the uploaded image")
    command.add_argument("--parent", help="Drive folder for the upload (default: the deck's folder)")

    command = add("slides-thumbnail", cmd_slides_thumbnail, "render one slide to PNG (LARGE)")
    command.add_argument("pres")
    command.add_argument("slide", help="1-based slide number or objectId")
    command.add_argument("-o", "--out", required=True)

    command = add("slides-export-pdf", cmd_slides_export_pdf, "export the whole deck to PDF")
    command.add_argument("pres")
    command.add_argument("-o", "--out", required=True)

    return parser


def main(argv: list[str] | None = None) -> None:
    import httpx

    args = build_parser().parse_args(argv)
    args.json = getattr(args, "json", False)
    config_arg = getattr(args, "config", None)
    workspace = None
    try:
        workspace = Workspace(load_config(config_arg))
        args.fn(args, workspace)
    except WorkspaceError as exc:
        sys.exit(f"error: {exc}")
    except httpx.RequestError as exc:
        sys.exit(f"error: network failure talking to Google: {exc}")
    except BrokenPipeError:  # `| head` is a normal way to use this CLI
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except (OSError, ValueError) as exc:
        sys.exit(f"error: {exc}")
    finally:
        if workspace is not None:
            workspace.close()
