#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Workspace-configured ClickUp CLI. See ../SKILL.md and --help."""
import argparse
import json
import mimetypes
import os
import random
import re
import string
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

API = "https://api.clickup.com/api/v2"
API_V1 = "https://api.clickup.com/api/v1"  # undocumented; task `content` is lossless only here
CONFIG = {}
CONFIG_PATH = None
TEAM_ID = SPACE_ID = CUSTOMER_FIELD_ID = ""
LISTS = {}
STATUSES = {}
USERS = {}
USER_NAMES = {}
PRIORITY = {"urgent": 1, "high": 2, "normal": 3, "low": 4}
TOKEN = None


def find_config(explicit=None):
    candidate = explicit or os.environ.get("CLICKUP_CONFIG")
    if candidate:
        path = Path(candidate).expanduser().resolve()
        if not path.is_file():
            sys.exit(f"ClickUp config does not exist: {path}")
        return path
    for root in (Path.cwd(), *Path.cwd().parents):
        for rel in (".agents/skills/clickup/clickup.toml", ".claude/skills/clickup/clickup.toml"):
            path = root / rel
            if path.is_file():
                return path.resolve()
    return None


def configure(path):
    import tomllib
    global CONFIG, CONFIG_PATH, TEAM_ID, SPACE_ID, LISTS, STATUSES, USERS, USER_NAMES, PRIORITY, CUSTOMER_FIELD_ID
    CONFIG_PATH = Path(path) if path else None
    CONFIG = tomllib.loads(CONFIG_PATH.read_text()) if path else {}
    workspace = CONFIG.get("workspace", {})
    TEAM_ID, SPACE_ID = str(workspace.get("id", "")), str(workspace.get("space_id", ""))
    LISTS = {k: str(v["id"]) for k, v in CONFIG.get("lists", {}).items()}
    STATUSES = {k: v.get("statuses", []) for k, v in CONFIG.get("lists", {}).items()}
    USERS = {k: int(v["id"]) for k, v in CONFIG.get("members", {}).items()}
    USER_NAMES = {k: v.get("name", k) for k, v in CONFIG.get("members", {}).items()}
    PRIORITY = {"urgent": 1, "high": 2, "normal": 3, "low": 4, **CONFIG.get("priorities", {})}
    CUSTOMER_FIELD_ID = CONFIG.get("custom_fields", {}).get("customer", {}).get("id", "")


def token_from_env():
    import shlex
    auth = CONFIG.get("auth", {})
    name = auth.get("env_var", "CLICKUP_API_PERSONAL_TOKEN")
    tok = os.environ.get(name, "").strip()
    filename = auth.get("env_file")
    if not tok and filename:
        path = Path(filename).expanduser()
        if not path.is_absolute() and CONFIG_PATH:
            path = CONFIG_PATH.parent / path
        if path.is_file():
            for line in path.read_text().splitlines():
                match = re.match(r"^(?:export\s+)?" + re.escape(name) + r"\s*=\s*(.*)$", line.strip())
                if match:
                    values = shlex.split(match[1], comments=True)
                    tok = values[0] if len(values) == 1 else ""
                    break
    if not tok:
        sys.exit(f"{name} is empty; set your personal token in the environment or configured auth.env_file")
    return tok


def list_id(key=None):
    key = key or CONFIG.get("workspace", {}).get("default_list")
    if not key:
        sys.exit("choose --list or configure workspace.default_list")
    if key in LISTS:
        return LISTS[key]
    if str(key).isdigit():
        return str(key)
    sys.exit(f"unknown list {key!r}; configured aliases: {', '.join(LISTS)}")


def _api(base: str, method: str, path: str, **kw):
    import time
    for attempt in range(3):
        r = requests.request(method, f"{base}{path}",
                             headers={"Authorization": TOKEN, "Content-Type": "application/json"},
                             timeout=30, **kw)
        if r.status_code != 429 or method != "GET" or attempt == 2:
            break
        reset = r.headers.get("X-RateLimit-Reset", "")
        delay = max(1, float(reset) - time.time()) if reset.replace(".", "", 1).isdigit() else 2 ** attempt
        if delay > 30:
            sys.exit("ClickUp rate limit: reset exceeds 30 seconds; retry after the reset")
        time.sleep(delay)
    if not r.ok:
        sys.exit(f"HTTP {r.status_code} on {method} {path}\n{r.text}")
    if not r.content:
        return {}
    try:
        return r.json()
    except ValueError:
        # ClickUp occasionally echoes descriptions with raw control characters.
        return json.loads(r.text.replace("\n", "\\n").replace("\r", "\\r"))


def api(method: str, path: str, **kw):
    return _api(API, method, path, **kw)


def api_v1(method: str, path: str, **kw):
    return _api(API_V1, method, path, **kw)


def user_id(who: str) -> int:
    uid = USERS.get(who)
    if uid is None and str(who).isdigit():
        uid = int(who)
    if uid is None:
        sys.exit(f"unknown user {who!r}; use a configured alias or numeric id")
    if uid in CONFIG.get("policy", {}).get("ignored_assignees", []):
        sys.exit(f"workspace policy forbids assigning or mentioning user {uid}")
    return uid


def task_id_of(ref: str) -> str:
    """Accept a bare id or any ClickUp task URL (…/t/<team>/<id>, …/t/<id>)."""
    m = re.search(r"/t/(?:\d+/)?([a-z0-9]+)", ref)
    return m.group(1) if m else ref


def list_key_of(task: dict) -> str:
    lid = task["list"]["id"]
    return next((k for k, v in LISTS.items() if v == lid), lid)


def check_status(list_key: str, status: str | None):
    """`list_key` may be a raw list id (a list outside LISTS) — then fetch its live status set."""
    if status is None:
        return
    valid = STATUSES.get(list_key) or [s["status"] for s in api("GET", f"/list/{list_id(list_key)}")["statuses"]]
    if status not in valid:
        sys.exit(f"status {status!r} is not valid on list {list_key!r}; valid: {valid}")


def out(data, as_json: bool, table=None):
    if as_json or table is None:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(table)


def customer_of(t: dict):
    for f in t.get("custom_fields", []):
        if f["id"] == CUSTOMER_FIELD_ID:
            return [{"id": v["id"], "name": v.get("name")} for v in (f.get("value") or [])]
    return None


def attachment_rows(t: dict) -> list[dict]:
    return [{"id": a["id"], "title": a.get("title"), "mimetype": a.get("mimetype"),
             "size": a.get("size"), "url": a.get("url")}
            for a in t.get("attachments", []) if not a.get("is_folder")]


def task_row(t: dict) -> dict:
    row = {
        "id": t["id"],
        "name": t["name"],
        "list": list_key_of(t),
        "status": t["status"]["status"],
        "priority": (t.get("priority") or {}).get("priority"),
        "assignees": [a["username"] for a in t.get("assignees", [])],
        "url": t["url"],
    }
    row["tags"] = [x["name"] for x in t.get("tags", [])]
    c = customer_of(t)
    if c is not None:
        row["customer"] = c
    atts = attachment_rows(t)
    if atts:
        row["attachments"] = atts
    return row


def download_attachments(t: dict, directory: str | None) -> list[dict]:
    """Fetch every attachment to disk so an agent can open images with native vision.

    Attachment URLs live on *.clickup-attachments.com and are pre-signed — never send the personal
    token to that host.
    """
    d = Path(directory or f"/tmp/cu-{t['id']}")
    d.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, a in enumerate(attachment_rows(t), 1):
        name = a["title"] or unquote(Path(urlparse(a["url"]).path).name) or a["id"]
        name = re.sub(r"[^\w.@ +-]", "_", name)
        p = d / f"{i:02d}-{name}"
        r = requests.get(a["url"], timeout=60)  # no Authorization header on purpose
        if not r.ok:
            sys.exit(f"HTTP {r.status_code} downloading {a['url']}")
        p.write_bytes(r.content)
        saved.append({**a, "path": str(p), "bytes": len(r.content)})
    return saved


def download_looms(t: dict, comments: list[dict], directory: str | None) -> list[dict]:
    """Run scripts/loom.py for every Loom share URL in the body or comments -> transcript + frames."""
    import subprocess
    text = "\n".join([t.get("markdown_description") or t.get("description") or ""]
                     + [c.get("comment_text") or "" for c in comments])
    base = Path(directory or f"/tmp/cu-{t['id']}")
    done = []
    for vid in dict.fromkeys(re.findall(r"loom\.com/(?:share|embed)/([0-9a-f]{32})", text)):
        d = base / f"loom-{vid}"
        subprocess.run(["uv", "run", str(Path(__file__).resolve().with_name("loom.py")), vid, "--dir", str(d)],
                       check=True, stdout=subprocess.DEVNULL)
        done.append(json.loads((d / "meta.json").read_text()))
    return done


def fetch_tasks(list_key: str, assignee: str | None, statuses: list[str], include_closed: bool, tags=()) -> list[dict]:
    params = [("include_closed", "true" if include_closed else "false"), ("subtasks", "true")]
    if assignee:
        params.append(("assignees[]", str(user_id(assignee))))
    for s in statuses:
        params.append(("statuses[]", s))
    params += [("tags[]", tag) for tag in tags]
    tasks, page = [], 0
    while True:
        d = api("GET", f"/list/{list_id(list_key)}/task", params=params + [("page", page)])
        tasks += d.get("tasks", [])
        if d.get("last_page") is True or not d.get("tasks") or ("last_page" not in d and len(d["tasks"]) < 100):
            return tasks
        page += 1


def read_back(task_id: str, as_json: bool):
    t = api("GET", f"/task/{task_id}", params={"include_markdown_description": "true"})
    out(t if as_json else task_row(t), as_json, json.dumps(task_row(t), indent=2, ensure_ascii=False))
    return t


def set_customer(task_id: str, customer_task_id: str):
    """Point an Onboardings task's `Customer` relationship at one Customers item, then verify."""
    c = api("GET", f"/task/{customer_task_id}")
    target = CONFIG.get("custom_fields", {}).get("customer", {}).get("target_list", "customers")
    if not CUSTOMER_FIELD_ID:
        sys.exit("configure custom_fields.customer before using --customer")
    if c["list"]["id"] != list_id(target):
        sys.exit(f"{customer_task_id} is not in the configured customer target list (it is in {list_key_of(c)!r})")
    current = [x["id"] for x in (customer_of(api("GET", f"/task/{task_id}")) or [])]
    value = {"add": [customer_task_id], "rem": [x for x in current if x != customer_task_id]}
    api("POST", f"/task/{task_id}/field/{CUSTOMER_FIELD_ID}", data=json.dumps({"value": value}))
    linked = customer_of(api("GET", f"/task/{task_id}")) or []
    if [x["id"] for x in linked] != [customer_task_id]:
        sys.exit(f"Customer link verification failed on {task_id}: now {linked}")


# --- markdown -> block events (shared by descriptions and comments) ---------
# ClickUp descriptions only accept rich mentions through the undocumented `content` field (a
# JSON-encoded Quill delta). The v2 read fields are lossy; v1 `fields[]=content` returns the exact
# delta and is therefore mandatory before appending to an existing description.
# `_md_blocks()` is the ONE markdown parser; `md_to_delta()` (delta ops) and `comment_parts()`
# (comment parts) are thin emitters over its events. Supported constructs (verified by readback on
# a live task, 2026-09-07):
#   paragraphs · blank lines · `#`/`##`/`###` headings
#   `-`/`*` bullets · `1.` ordered lists · two-space indent nests · `- [ ]`/`- [x]` checklists
#   `> quote` · fenced ```lang code blocks · `|` tables (native embed) · `---` dividers
#   `![alt](https://…)` images
#   `**bold**` · `*italic*` / `_italic_` · `~~strike~~` · `` `code` `` · `[text](url)`
#   `[@Name](#user_mention#ID)` · `@reviewer` / `@author` · task mentions as `[[task-id]]`, a ClickUp
#   task URL, or a markdown link to one
# Descriptions need the NESTED attribute shapes ClickUp normalizes to (`{"list": {"list": …}}`,
# `{"blockquote": {}}`, `{"code-block": {"code-block": lang}}`) — emitting the flat form round-trips
# as the nested one and would break the exact-op readback in `content_signature`. Comments keep the
# flat shapes (`{"list": "bullet"}`, `{"code-block": "plain"}`).
# NOT supported: nested inline markup (e.g. bold inside a link), reference links, HTML.

_MD_INLINE = re.compile(
    r"\[@(?P<mname>[^\]]+)\]\(#user_mention#(?P<mid>\d+)\)"      # [@Name](#user_mention#ID)
    r"|(?<![\w@])@(?P<alias>" + r"[A-Za-z][\w-]*" + r")\b"          # configured alias shorthand
    r"|\[\[(?P<tshort>[a-z0-9]+)\]\]"                              # [[task-id]]
    r"|\[(?P<ltext>[^\]]+)\]\((?P<lurl>[^)]+)\)"                  # [text](url)
    r"|(?P<turl>https://app\.clickup\.com/t/(?:\d+/)?[a-z0-9]+)"  # bare ClickUp task URL
    r"|\*\*(?P<bold>[^*\n]+)\*\*"                                 # **bold** (before *italic*)
    r"|~~(?P<strike>[^~\n]+)~~"                                    # ~~strike~~
    r"|(?<!\w)\*(?P<ital>[^*\n]+)\*(?!\w)"                        # *italic*
    r"|(?<!\w)_(?P<ital2>[^_\n]+)_(?!\w)"                         # _italic_ (snake_case survives)
    r"|`(?P<code>[^`]+)`"                                          # `code`
)
_MD_BLOCK = re.compile(
    r"^(?P<ind>[ \t]*)"
    r"(?:(?P<h>#{1,3})\s+"
    r"|(?P<q>>)\s?"
    r"|(?P<b>[-*])\s+(?:\[(?P<chk>[ xX])\]\s+)?"
    r"|(?P<o>\d+)\.\s+)?(?P<rest>.*)$"
)
_MD_ESCAPE = re.compile(r"\\([\\`*_~{}\[\]()#+.!-])")
_MD_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_MD_DIVIDER = re.compile(r"^ {0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")
_MD_IMAGE = re.compile(r"^\s*!\[[^\]]*\]\((?P<url>https?://[^)\s]+)\)\s*$")


def _table_rows(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        if _MD_TABLE_SEP.match(line):
            continue
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


def _table_embed(rows: list[list[str]]) -> dict:
    """Native ClickUp table (the shape the UI writes; ids are opaque, cells are plain text)."""
    ncols = max(map(len, rows))
    rid = lambda p: p + "-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))  # noqa: E731
    return {
        "rows": [{"insert": {"id": rid("row")}} for _ in rows],
        "columns": [{"insert": {"id": rid("column")}, "attributes": {"width": "150"}} for _ in range(ncols)],
        "cells": {f"{r + 1}:{c + 1}": {"content": [{"insert": row[c] if c < len(row) else ""},
                                                   {"insert": "\n"}],
                                       "attributes": {"colspan": "1", "rowspan": "1"}}
                  for r, row in enumerate(rows) for c in range(ncols)},
    }


def _md_blocks(md: str) -> list[tuple]:
    """Markdown -> block events: ("line", attrs, inline text) | ("code", lang, text)
    | ("table", rows) | ("divider",) | ("image", url).

    `attrs` is emitter-neutral: {"header": n} | {"list": bullet|ordered|checked|unchecked,
    "indent": n} | {"blockquote": True}.
    """
    lines = md.replace("\r\n", "\n").split("\n")
    events: list[tuple] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            events.append(("code", line.strip()[3:].strip() or "plain", "\n".join(lines[i + 1:j])))
            i = j + 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and _MD_TABLE_SEP.match(lines[i + 1]):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            events.append(("table", _table_rows(lines[i:j])))
            i = j
            continue
        if _MD_DIVIDER.match(line):
            events.append(("divider",))
            i += 1
            continue
        img = _MD_IMAGE.match(line)
        if img:
            events.append(("image", img["url"]))
            i += 1
            continue
        m = _MD_BLOCK.match(line)
        attrs: dict = {}
        if m["h"]:
            attrs["header"] = len(m["h"])
        elif m["q"]:
            attrs["blockquote"] = True
        elif m["b"] or m["o"]:
            attrs["list"] = ("ordered" if m["o"] else "bullet" if m["chk"] is None
                             else "checked" if m["chk"].lower() == "x" else "unchecked")
            indent = len(m["ind"].expandtabs(2)) // 2
            if indent:
                attrs["indent"] = indent
        events.append(("line", attrs, m["rest"]))
        i += 1
    return events


def _inline_events(text: str) -> list[tuple]:
    """Inline markdown -> ("text", s, attrs|None) | ("user", id, name) | ("task", task_id, None)."""
    events: list[tuple] = []

    def plain(s: str):
        s = _MD_ESCAPE.sub(r"\1", s)  # ClickUp emits \_ \* … in markdown_description
        if s:
            events.append(("text", s, None))

    pos = 0
    for m in _MD_INLINE.finditer(text):
        plain(text[pos:m.start()])
        if m["mid"]:
            events.append(("user", user_id(m["mid"]), m["mname"]))
        elif m["alias"]:
            events.append(("user", user_id(m["alias"]), USER_NAMES[m["alias"]])) if m["alias"] in USERS else plain(m[0])
        elif m["tshort"]:
            events.append(("task", m["tshort"], None))
        elif m["ltext"]:
            task_id = task_id_from_url(m["lurl"])
            events.append(("task", task_id, None) if task_id
                          else ("text", m["ltext"], {"link": m["lurl"]}))
        elif m["turl"]:
            events.append(("task", task_id_of(m["turl"]), None))
        elif m["bold"]:
            events.append(("text", m["bold"], {"bold": True}))
        elif m["strike"]:
            events.append(("text", m["strike"], {"strike": True}))
        elif m["ital"] or m["ital2"]:
            events.append(("text", m["ital"] or m["ital2"], {"italic": True}))
        else:
            events.append(("text", m["code"], {"code": True}))
        pos = m.end()
    plain(text[pos:])
    return events


def _delta_attrs(attrs: dict) -> dict:
    """Emitter-neutral block attrs -> the nested shapes ClickUp stores for descriptions."""
    out = {}
    for k, v in attrs.items():
        if k == "list":
            out["list"] = {"list": v}
        elif k == "blockquote":
            out["blockquote"] = {}
        else:
            out[k] = v
    return out


def md_to_delta(md: str) -> str:
    """Render markdown as a JSON Quill delta for ClickUp's `content` field."""
    ops: list[dict] = []

    def newline(attrs: dict | None = None):
        ops.append({"insert": "\n", **({"attributes": attrs} if attrs else {})})

    for event in _md_blocks(md.replace("\r\n", "\n").rstrip("\n")):
        kind = event[0]
        if kind == "line":
            _, attrs, text = event
            for ekind, value, extra in _inline_events(text):
                if ekind == "user":
                    ops.append({"insert": {"user_mention": {"id": value, "name": extra}}})
                elif ekind == "task":
                    ops.append({"insert": {"task_mention": {"task_id": value}}})
                else:
                    ops.append({"insert": value, **({"attributes": extra} if extra else {})})
            newline(_delta_attrs(attrs))
        elif kind == "code":
            _, lang, code = event
            for code_line in code.split("\n"):
                if code_line:
                    ops.append({"insert": code_line})
                newline({"code-block": {"code-block": lang}})
        elif kind == "table":
            ops.append({"insert": {"table-embed": _table_embed(event[1])}})
            newline()
        elif kind == "divider":
            ops.append({"insert": {"divider": True}})
            newline()
        elif kind == "image":
            ops.append({"insert": {"image": event[1]}})
            newline()
    return json.dumps({"ops": ops}, ensure_ascii=False)


def get_task(task_id: str, markdown: bool = False) -> dict:
    return api("GET", f"/task/{task_id}",
               params={"include_markdown_description": "true"} if markdown else None)


def set_description(task_id: str, md: str):
    content = md_to_delta(md)
    write_task_content(task_id, content)


def task_id_from_url(value: str) -> str | None:
    m = re.search(r"https://app\.clickup\.com/t/(?:\d+/)?([a-z0-9]+)", value)
    return m.group(1) if m else None


def get_task_content(task_id: str) -> str:
    """Lossless task-description delta. The documented v2 endpoint omits this field."""
    task = api_v1("GET", f"/task/{task_id}", params=[("fields[]", "content")])
    return task.get("content") or ""


def _trailing_newlines(ops: list[dict]) -> int:
    count = 0
    for op in reversed(ops):
        inserted = op.get("insert")
        if not isinstance(inserted, str):
            break
        match = re.search(r"\n+$", inserted)
        if not match:
            break
        count += len(match.group())
        if match.start() > 0 or count >= 2:
            break
    return min(count, 2)


def append_ops_to_content(content: str, added_ops: list[dict]) -> str:
    """Append ops without changing one byte of any existing rich-content op."""
    added_ops = list(added_ops)
    try:
        delta = json.loads(content) if content else {"ops": []}
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"task content is not valid JSON: {exc}") from exc
    if not isinstance(delta, dict) or not isinstance(delta.get("ops"), list):
        raise TypeError("task content is not a Quill {ops:[...]} document")
    existing_ops = delta["ops"]
    if existing_ops:
        missing = 2 - _trailing_newlines(existing_ops)
        if missing:
            added_ops.insert(0, {"insert": "\n" * missing})
    return json.dumps({**delta, "ops": [*existing_ops, *added_ops]}, ensure_ascii=False)


def append_markdown_to_content(content: str, extra: str) -> str:
    return append_ops_to_content(content, json.loads(md_to_delta(extra))["ops"])


def embed_ops(att: dict) -> tuple[str, list[dict]]:
    """Ops that render an uploaded attachment INSIDE the description: video player or file chip.

    Undocumented shapes, copied verbatim from what ClickUp's own UI stores (probed 2026-09-08).
    `block-id` attributes are deliberately omitted — ClickUp assigns them.
    """
    url = att.get("url") or ""
    open_url = att.get("url_w_query") or f"{url}?view=open"
    # The upload response has no mimetype (only the later task read does): decide by name.
    mime = att.get("mimetype") or mimetypes.guess_type(att.get("title") or url)[0] or ""
    if mime.startswith("video/"):
        return "video", [
            {"insert": {"frame": {"id": att["id"], "service": "clickup_video",
                                  "url": open_url, "src": open_url, "source": 1}},
             "attributes": {"width": "420", "data-size": "large", "data-origin": "attachment"}},
            {"insert": "\n"},
        ]
    return "file", [
        {"insert": {"attachment": {
            "name": att.get("title") or "", "source": 1, "date": int(att.get("date") or 0),
            "url": url, "url_w_host": att.get("url_w_host") or url, "url_w_query": open_url,
            "id": att["id"], "type": mime,
            "extension": att.get("extension") or ""}}},
        {"insert": "\n"},
    ]


def verify_embed(task_id: str, embed_op: dict):
    """The preservation check proves nothing was lost; this proves the embed actually landed."""
    key = next(iter(embed_op["insert"]))  # "frame" | "attachment"
    embed_id = embed_op["insert"][key]["id"]
    ops = json.loads(get_task_content(task_id) or '{"ops":[]}')["ops"]
    if not any(isinstance(op.get("insert"), dict) and key in op["insert"]
               and op["insert"][key].get("id") == embed_id for op in ops):
        sys.exit(f"embed {embed_id} is missing from {task_id} content readback")


def content_signature(content: str) -> list[tuple[str, object]]:
    """Preserve ordering while tolerating merged adjacent unformatted strings."""
    delta = json.loads(content)
    signature: list[tuple[str, object]] = []
    plain = ""
    for op in delta["ops"]:
        if isinstance(op.get("insert"), str) and not op.get("attributes"):
            plain += op["insert"]
            continue
        if plain:
            signature.append(("text", plain))
            plain = ""
        signature.append(("op", op))
    if plain:
        signature.append(("text", plain))
    return signature


def verify_task_content(task_id: str, expected: str):
    actual = get_task_content(task_id)
    if content_signature(actual) != content_signature(expected):
        sys.exit(f"task {task_id} content readback differs: text or rich embeds/formatting were lost")


def appended_ops_content(task_id: str, ops: list[dict]) -> str:
    raw = get_task_content(task_id)
    if not raw:
        task = get_task(task_id)
        if (task.get("description") or task.get("text_content") or "").strip():
            sys.exit(f"refusing to append on {task_id}: task has a description but lossless content "
                     "came back empty — appending would wipe rich content")
    try:
        return append_ops_to_content(raw, ops)
    except (TypeError, ValueError) as exc:
        sys.exit(f"refusing to append on {task_id}: {exc}")


def appended_content(task_id: str, extra: str) -> str:
    return appended_ops_content(task_id, json.loads(md_to_delta(extra))["ops"])


def task_mention_part(task_id: str) -> dict:
    task = get_task(task_id)
    if str(task.get("team_id")) != TEAM_ID:
        sys.exit(f"task mention {task_id} is outside workspace {TEAM_ID}")
    return {"type": "task_mention", "text": task["name"],
            "task_mention": {"task_id": task_id, "team_id": TEAM_ID}}


# --- markdown -> structured comment parts -----------------------------------
# Comments take the same Quill-style attributes as descriptions, but as `{"text", "attributes"}`
# parts (docs: developer.clickup.com/docs/comment-formatting) and in the FLAT attribute shape
# (`{"list": "bullet"}`, `{"code-block": "plain"}`) — verified by readback 2026-09-07 together with
# bold · italic · strike · code · link · header · indent · blockquote · checklists.
# Tables use the undocumented `table-embed` part the ClickUp UI writes (plain-text cells).
# Dividers and images have no comment part: they degrade to a rule line / a link.


def _inline_parts(text: str) -> list[dict]:
    parts: list[dict] = []
    for kind, value, extra in _inline_events(text):
        if kind == "user":
            parts.append({"type": "tag", "user": {"id": value}})
        elif kind == "task":
            parts.append(task_mention_part(value))
        else:
            parts.append({"text": value, **({"attributes": extra} if extra else {})})
    return parts


def comment_parts(text: str) -> list[dict]:
    """Same markdown as `md_to_delta`, emitted as ClickUp structured comment parts."""
    parts: list[dict] = []
    events = _md_blocks(text.replace("\r\n", "\n"))
    for i, event in enumerate(events):
        kind, last = event[0], i == len(events) - 1
        if kind == "line":
            _, attrs, line = event
            parts += _inline_parts(line)
            if attrs:
                parts.append({"text": "\n", "attributes": attrs})
            elif not last:
                parts.append({"text": "\n"})
        elif kind == "code":
            parts += [{"text": event[2]}, {"text": "\n", "attributes": {"code-block": event[1]}}]
        elif kind == "table":
            parts.append({"type": "table-embed", "table-embed": _table_embed(event[1])})
        elif kind == "divider":
            parts.append({"text": "─" * 24 + ("" if last else "\n")})
        elif kind == "image":
            parts.append({"text": event[1], "attributes": {"link": event[1]}})
            if not last:
                parts.append({"text": "\n"})
    return parts or [{"text": ""}]


def validate_task_mentions(content: str):
    delta = json.loads(content)
    task_ids = {
        op["insert"]["task_mention"]["task_id"]
        for op in delta["ops"]
        if isinstance(op.get("insert"), dict) and "task_mention" in op["insert"]
    }
    for task_id in task_ids:
        task_mention_part(task_id)  # resolves the task and enforces TEAM_ID


def write_task_content(task_id: str, content: str):
    validate_task_mentions(content)
    api("PUT", f"/task/{task_id}", data=json.dumps({"content": content}))
    verify_task_content(task_id, content)


def render(comment: dict) -> str:
    """Text in real part order. ClickUp's derived `comment_text` always appends tags at the end."""
    def part_text(part: dict) -> str:
        if part.get("type") == "tag":
            return f"@{part.get('user', {}).get('username', part.get('user', {}).get('id', 'user'))}"
        if part.get("type") == "task_mention":
            return part.get("text") or f"[[{part.get('task_mention', {}).get('task_id', 'task')}]]"
        return part.get("text", "")
    return "".join(part_text(p) for p in comment["comment"])


def post_comment(task_id: str, text: str, mention: int | None, as_json: bool, quiet: bool = False,
                 prefix: str | None = None):
    """``prefix`` puts the mention at the TOP: ``<prefix> @mention\n<text>`` (e.g. "# Review")."""
    if mention and prefix is not None:
        parts: list[dict] = ([{"text": prefix + " "}] if prefix else []) + [
            {"type": "tag", "user": {"id": mention}}]
        parts += comment_parts(("\n" if prefix else " ") + text)
    else:
        parts = comment_parts(text.rstrip() + " " if mention else text)
        if mention:
            parts.append({"type": "tag", "user": {"id": mention}})
    created = api("POST", f"/task/{task_id}/comment",
                  data=json.dumps({"comment": parts, "notify_all": False}))
    comments = api("GET", f"/task/{task_id}/comment")["comments"]
    posted = next((c for c in comments if str(c["id"]) == str(created["id"])), None)
    if posted is None:
        sys.exit(f"comment {created['id']} created but not found on readback; do not retry posting")
    expected_users = {p["user"]["id"] for p in parts if p.get("type") == "tag"}
    expected_tasks = {p["task_mention"]["task_id"] for p in parts
                      if p.get("type") == "task_mention"}
    actual_users = {p.get("user", {}).get("id") for p in posted["comment"] if p.get("type") == "tag"}
    actual_tasks = {p.get("task_mention", {}).get("task_id") for p in posted["comment"]
                    if p.get("type") == "task_mention"}
    has_tag = bool(actual_users)
    if expected_users - actual_users:
        sys.exit(f"comment posted WITHOUT a real mention: {render(posted)!r}")
    if expected_tasks - actual_tasks:
        sys.exit(f"comment posted WITHOUT a real task mention: {render(posted)!r}")
    if quiet:
        return
    out(posted if as_json else {"id": posted["id"], "text": render(posted), "mention": has_tag},
        as_json, f"posted{' with mention' if has_tag else ''}: {render(posted)}")


def policy(key, default=None):
    return CONFIG.get("policy", {}).get(key, default)


def counterpart(current, explicit=None):
    if explicit:
        return user_id(explicit)
    me = api("GET", "/user")["user"]["id"]
    if policy("handoff_mode", "counterpart") == "assignee":
        ignored = {me, *policy("ignored_assignees", [])}
        candidates = [u["id"] for u in current.get("assignees", []) if u["id"] not in ignored]
    else:
        pair = policy("handoff_pair", list(USERS))
        ids = {user_id(u) for u in pair}
        candidates = list(ids - {me}) if me in ids else []
    if len(candidates) != 1:
        sys.exit("cannot derive one recipient; pass --mention")
    return candidates[0]


def closed_status(task):
    key = list_key_of(task)
    configured = CONFIG.get("lists", {}).get(key, {}).get("closed_status") or policy("review_closed_status")
    if configured:
        return configured
    statuses = api("GET", f"/list/{task['list']['id']}")["statuses"]
    closed = [s["status"] for s in statuses if s["type"] == "closed"]
    if len(closed) != 1:
        sys.exit("cannot derive one closed status; pass --status")
    return closed[0]


def cmd_whoami(a):
    u = api("GET", "/user")["user"]
    if CONFIG.get("workspace", {}).get("default_list"):
        api("GET", f"/list/{list_id()}")
    out({**u, "known_as": next((k for k, v in USERS.items() if v == u["id"]), "unknown")}, a.json)


def cmd_discovery(a):
    if a.cmd == "workspaces":
        result = api("GET", "/team")
    elif a.cmd == "spaces":
        team = a.workspace or TEAM_ID
        if not team:
            sys.exit("pass --workspace or configure workspace.id")
        result = api("GET", f"/team/{team}/space")
    elif a.cmd == "folders":
        space = a.space or SPACE_ID
        if not space:
            sys.exit("pass --space or configure workspace.space_id")
        result = api("GET", f"/space/{space}/folder")
    elif a.cmd == "lists":
        space = a.space or SPACE_ID
        if a.folder:
            result = api("GET", f"/folder/{a.folder}/list")
        elif space:
            lists = api("GET", f"/space/{space}/list")["lists"]
            for folder in api("GET", f"/space/{space}/folder")["folders"]:
                lists += api("GET", f"/folder/{folder['id']}/list")["lists"]
            result = {"lists": lists}
        else:
            sys.exit("pass --space/--folder or configure workspace.space_id")
    elif a.cmd == "members" and not a.list:
        teams = api("GET", "/team")["teams"]
        result = next((t["members"] for t in teams if str(t["id"]) == TEAM_ID), None)
        if result is None:
            sys.exit("configured workspace not visible; run workspaces")
    else:
        lid = list_id(a.list)
        if a.cmd == "statuses":
            result = api("GET", f"/list/{lid}")["statuses"]
        else:
            result = api("GET", f"/list/{lid}/{'member' if a.cmd == 'members' else 'field'}")
    out(result, a.json)


def cmd_topology(a):
    teams = api("GET", "/team")["teams"]
    team = next((t for t in teams if str(t["id"]) == TEAM_ID), None)
    if team is None:
        sys.exit(f"workspace {TEAM_ID!r} not visible; run workspaces")
    lists = {k: api("GET", f"/list/{lid}") for k, lid in LISTS.items()}
    out({"team": {"id": team["id"], "name": team["name"]}, "members": team["members"],
         "lists": lists, "matches_skill_constants": all(
             not STATUSES[k] or STATUSES[k] == [s["status"] for s in v["statuses"]]
             for k, v in lists.items())}, a.json)


def cmd_tasks(a):
    for status in a.status or []:
        check_status(a.list or CONFIG.get("workspace", {}).get("default_list"), status)
    tasks = fetch_tasks(a.list, a.assignee, a.status or [], a.include_closed or bool(a.status), a.tag or [])
    if a.search:
        needle = a.search.casefold()
        tasks = [t for t in tasks if needle in (t["name"] + "\n" + (t.get("description") or "")).casefold()]
    if a.json:
        return out(tasks, True)
    rows = [task_row(t) for t in tasks]
    key = next((k for k, lid in LISTS.items() if lid == list_id(a.list)), "")
    order = STATUSES.get(key, [])
    active = policy("active_statuses", [])
    for status in order + sorted({r["status"] for r in rows} - set(order)):
        group = [r for r in rows if r["status"] == status]
        if group:
            mark = "*" if status in active else " "
            print(f"{mark} {status} ({len(group)})")
            for r in group:
                print(f"    {r['id']}  {r['name']}  [{r['priority']}]  {'/'.join(r['assignees'])}  {r['url']}")
    print(f"\n{len(rows)} task(s). '*' = active queue.")


def cmd_customers(a):
    target = CONFIG.get("custom_fields", {}).get("customer", {}).get("target_list", "customers")
    tasks = fetch_tasks(target, None, [], True)
    out([task_row(t) for t in tasks if (a.search or "").casefold() in t["name"].casefold()], a.json)


def cmd_task(a):
    t = get_task(a.id, markdown=True)
    t["content"] = get_task_content(a.id)
    comments = fetch_comments(a.id) if a.comments or a.download_looms else []
    result = {"task": t}
    if a.comments:
        result["comments"] = comments
    if a.download_attachments:
        result["downloaded"] = download_attachments(t, a.dir)
    if a.download_looms:
        result["looms"] = download_looms(t, comments, a.dir)
    out(result, a.json)


def fetch_comments(tid):
    comments, params = [], {}
    while True:
        batch = api("GET", f"/task/{tid}/comment", params=params)["comments"]
        comments += batch
        if len(batch) < 25:
            return comments
        cursor = {"start": batch[-1]["date"], "start_id": batch[-1]["id"]}
        if cursor == params:
            sys.exit("comment pagination did not advance")
        params = cursor


def description_of(a, prefix=""):
    filename = getattr(a, prefix + "description_file", None)
    return Path(filename).read_text() if filename else getattr(a, prefix + "description", None)


def customer_allowed(lid):
    cfg = CONFIG.get("custom_fields", {}).get("customer", {})
    if not cfg.get("id") or lid != list_id(cfg.get("list", "onboardings")):
        sys.exit("--customer requires the configured customer relationship source list")


def cmd_create(a):
    lid = list_id(a.list)
    key = next((k for k, v in LISTS.items() if v == lid), lid)
    status = a.status or CONFIG.get("lists", {}).get(key, {}).get("default_status")
    check_status(key, status)
    assignee = a.assignee or policy("default_assignee")
    if policy("require_assignee", False) and not assignee:
        sys.exit("workspace policy requires --assignee")
    if policy("require_priority", False) and not a.priority:
        sys.exit("workspace policy requires --priority")
    if a.customer:
        customer_allowed(lid)
    body = {"name": a.name}
    if assignee:
        body["assignees"] = [user_id(assignee)]
    if status:
        body["status"] = status
    if a.priority:
        body["priority"] = PRIORITY[a.priority]
    if a.tag:
        body["tags"] = a.tag
    if a.parent:
        body["parent"] = task_id_of(a.parent)
    desc = description_of(a)
    if desc is not None:
        body["content"] = md_to_delta(desc)
        validate_task_mentions(body["content"])
    t = api("POST", f"/list/{lid}/task", data=json.dumps(body))
    # Make partial success recoverable even when rich-content readback fails.
    print(f"created task {t['id']} {t.get('url', '')}", file=sys.stderr)
    if "content" in body:
        verify_task_content(t["id"], body["content"])
    if a.customer:
        set_customer(t["id"], task_id_of(a.customer))
    read_back(t["id"], a.json)


def cmd_update(a):
    current = get_task(a.id)
    check_status(list_key_of(current), a.status)
    if a.customer:
        customer_allowed(current["list"]["id"])
    body = {}
    for key in ("name", "status"):
        if getattr(a, key) is not None:
            body[key] = getattr(a, key)
    if a.priority:
        body["priority"] = PRIORITY[a.priority]
    desc, extra = description_of(a), description_of(a, "append_")
    if desc is not None and extra is not None:
        sys.exit("pass either --description* or --append-description*, not both")
    if desc is not None:
        body["content"] = md_to_delta(desc)
    elif extra is not None:
        body["content"] = appended_content(a.id, extra.strip())
    if a.add_assignee or a.rem_assignee:
        body["assignees"] = {"add": [user_id(x) for x in a.add_assignee or []],
                             "rem": [user_id(x) for x in a.rem_assignee or []]}
    if not body and not a.customer:
        sys.exit("nothing to update")
    if body:
        if "content" in body:
            validate_task_mentions(body["content"])
        api("PUT", f"/task/{a.id}", data=json.dumps(body))
        if "content" in body:
            verify_task_content(a.id, body["content"])
    if a.customer:
        set_customer(a.id, task_id_of(a.customer))
    read_back(a.id, a.json)


def cmd_close(a):
    current = get_task(a.id)
    status = a.status or closed_status(current)
    check_status(list_key_of(current), status)
    api("PUT", f"/task/{a.id}", data=json.dumps({"status": status}))
    read_back(a.id, a.json)


def cmd_comment(a):
    post_comment(a.id, a.text, user_id(a.mention) if a.mention else None, a.json, prefix=a.mention_first)


def cmd_comments(a):
    out(fetch_comments(a.id), a.json)


def cmd_handoff(a):
    current = get_task(a.id)
    status = a.status or policy("handoff_status", "to test")
    check_status(list_key_of(current), status)
    mention = counterpart(current, a.mention)
    if current["status"]["status"] != status:
        api("PUT", f"/task/{a.id}", data=json.dumps({"status": status}))
    post_comment(a.id, a.text, mention, False, quiet=a.json)
    read_back(a.id, a.json)


def cmd_review(a):
    current = get_task(a.id)
    status = closed_status(current) if a.verdict == "ok" else policy("handoff_status", "to test")
    check_status(list_key_of(current), status)
    me = api("GET", "/user")["user"]
    text = a.text or (policy("review_ok_text", f"reviewed by {me['username']}'s coding agent, ✅ all fine") if a.verdict == "ok" else None)
    if not text:
        sys.exit("--text required for --verdict to-test")
    recipient = a.mention or policy("review_mention")
    mention = user_id(recipient) if recipient else counterpart(current)
    header = policy("review_header")
    if not header:
        name = next((USER_NAMES[k] for k, uid in USERS.items() if uid == mention), str(mention))
        header = f"# {me['username']} [@{name}](#user_mention#{mention})"
    content = appended_content(a.id, f"{header}\n\n{text.strip()}")
    validate_task_mentions(content)
    api("PUT", f"/task/{a.id}", data=json.dumps({"status": status, "content": content}))
    verify_task_content(a.id, content)
    if a.comment:
        post_comment(a.id, text, mention, False, quiet=a.json, prefix="")
    read_back(a.id, a.json)


def upload_attachment(tid, filename, name=None):
    path = Path(filename)
    with path.open("rb") as stream:
        r = requests.post(f"{API}/task/{tid}/attachment", headers={"Authorization": TOKEN},
                          files={"attachment": (name or path.name, stream,
                                 mimetypes.guess_type(name or path.name)[0] or "application/octet-stream")}, timeout=120)
    if not r.ok:
        sys.exit(f"HTTP {r.status_code} uploading attachment: {r.text}")
    return r.json()


def cmd_attach(a):
    result = upload_attachment(a.id, a.file, a.name)
    if a.embed:
        kind, ops = embed_ops(result)
        write_task_content(a.id, appended_ops_content(a.id, ops))
        verify_embed(a.id, ops[0])
        result["embedded"] = kind
    out(result, a.json, result.get("url") or json.dumps(result))


def resolve_field(field):
    return CONFIG.get("custom_fields", {}).get(field, {"id": field})


def cmd_field(a):
    cfg = resolve_field(a.field)
    if a.remove:
        if a.value is not None:
            sys.exit("--remove and --value are mutually exclusive")
        api("DELETE", f"/task/{a.id}/field/{cfg['id']}")
    else:
        if a.value is None:
            sys.exit("pass --value (JSON or configured enum label), or --remove")
        if a.value in cfg.get("options", {}):
            value = cfg["options"][a.value]
        else:
            try:
                value = json.loads(a.value)
            except ValueError:
                sys.exit("--value must be valid JSON or an exact configured option label")
        api("POST", f"/task/{a.id}/field/{cfg['id']}", data=json.dumps({"value": value}))
    read_back(a.id, a.json)


def cmd_delete(a):
    if not a.yes:
        sys.exit("refusing to delete without --yes")
    api("DELETE", f"/task/{a.id}")
    out({"deleted": a.id}, a.json, f"deleted {a.id}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config")
    config_args, _ = pre.parse_known_args(argv)
    configure(find_config(config_args.config))
    g = argparse.ArgumentParser(add_help=False)
    g.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    g.add_argument("--config", default=argparse.SUPPRESS, help="workspace TOML; otherwise CLICKUP_CONFIG or cwd ancestor discovery")
    p = argparse.ArgumentParser(description=__doc__, parents=[g])
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=lambda **kw: argparse.ArgumentParser(parents=[g], **kw))
    for cmd in ("whoami", "topology", "workspaces", "spaces", "folders", "lists", "statuses", "members", "fields"):
        s = sub.add_parser(cmd)
        s.set_defaults(fn=globals().get("cmd_" + cmd, cmd_discovery))
        if cmd == "spaces": s.add_argument("--workspace")
        if cmd in ("folders", "lists"): s.add_argument("--space")
        if cmd == "lists": s.add_argument("--folder")
        if cmd in ("statuses", "members", "fields"): s.add_argument("--list")
    for cmd in ("tasks", "search"):
        s = sub.add_parser(cmd)
        s.add_argument("--list")
        s.add_argument("--assignee")
        s.add_argument("--status", action="append")
        s.add_argument("--tag", action="append")
        s.add_argument("--include-closed", action="store_true")
        s.add_argument("--search", required=cmd == "search", help="case-insensitive substring in name/description of selected list")
        s.set_defaults(fn=cmd_tasks)
    s = sub.add_parser("customers")
    s.add_argument("--search")
    s.set_defaults(fn=cmd_customers)
    for cmd in ("task", "create", "update", "close", "comment", "comments", "handoff", "review", "attach", "field", "delete"):
        s = sub.add_parser(cmd)
        s.set_defaults(fn=globals()["cmd_" + cmd])
        if cmd != "create": s.add_argument("id")
        if cmd == "task":
            for flag in ("comments", "download-attachments", "download-looms"):
                s.add_argument("--" + flag, action="store_true")
            s.add_argument("--dir")
        if cmd in ("create", "update"):
            s.add_argument("--name", required=cmd == "create")
            s.add_argument("--priority", choices=list(PRIORITY))
            s.add_argument("--description")
            s.add_argument("--description-file")
            s.add_argument("--customer")
        if cmd in ("create", "update", "close", "handoff"): s.add_argument("--status")
        if cmd == "create":
            s.add_argument("--list")
            s.add_argument("--assignee")
            s.add_argument("--tag", action="append")
            s.add_argument("--parent")
        if cmd == "update":
            s.add_argument("--append-description")
            s.add_argument("--append-description-file")
            s.add_argument("--add-assignee", action="append")
            s.add_argument("--rem-assignee", action="append")
        if cmd in ("comment", "handoff", "review"): s.add_argument("--text", required=cmd != "review")
        if cmd in ("comment", "handoff", "review"): s.add_argument("--mention")
        if cmd == "comment": s.add_argument("--mention-first")
        if cmd == "review":
            s.add_argument("--verdict", choices=["ok", "to-test"], required=True)
            s.add_argument("--comment", action="store_true")
        if cmd == "attach":
            s.add_argument("file")
            s.add_argument("--name")
            s.add_argument("--embed", action="store_true")
        if cmd == "field":
            s.add_argument("field", help="configured field alias or UUID")
            s.add_argument("--value")
            s.add_argument("--remove", action="store_true")
        if cmd == "delete": s.add_argument("--yes", action="store_true")
    a = p.parse_args(argv)
    a.json = getattr(a, "json", False)
    if getattr(a, "id", None): a.id = task_id_of(a.id)
    global TOKEN
    TOKEN = token_from_env()
    a.fn(a)


if __name__ == "__main__":
    main()
