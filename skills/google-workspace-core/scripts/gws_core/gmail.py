"""Gmail: search, read, drafts, send, labels, attachments and one-time codes."""

from __future__ import annotations

import base64
import html as html_module
import mimetypes
import re
import time
import unicodedata
from collections.abc import Iterator
from email.message import EmailMessage
from email.policy import SMTP
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .errors import WorkspaceError
from .session import GMAIL, Session

HEADER_ORDER = ("Date", "From", "To", "Cc", "Reply-To", "Subject", "Message-ID", "References")
# A 4-10 character run of letters+digits containing at least one digit: 123456, A1B2C3, 9F4K2.
CODE_RE = re.compile(r"\b(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{4,10}\b")
QUOTE_MARKERS = (
    r"^On .{1,400}? wrote:\s*$",
    r"^Op .{1,400}? schreef.{0,200}?:\s*$",
    r"^Le .{1,400}? a écrit\s*:\s*$",
    r"^Am .{1,400}? schrieb.{0,200}?:\s*$",
    r"^-{2,}\s*(?:Original Message|Forwarded message)\s*-{2,}\s*$",
    r"^_{5,}\s*$",
    r"^\*?(?:From|Van|Sent|Verzonden):\*?\s",
)


class _HtmlText(HTMLParser):
    """HTML mail body → readable text, keeping link targets, without summarizing."""

    BLOCKS = frozenset({"address", "blockquote", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                        "hr", "li", "ol", "p", "pre", "table", "tr", "ul"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._ignored = 0
        self._links: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored += 1
            return
        if self._ignored:
            return
        if tag in self.BLOCKS:
            self._newline()
        if tag == "li":
            self._chunks.append("- ")
        if tag == "a":
            self._links.append((dict(attrs).get("href") or "", len("".join(self._chunks))))

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored = max(0, self._ignored - 1)
            return
        if self._ignored:
            return
        if tag == "a" and self._links:
            href, start = self._links.pop()
            visible = "".join(self._chunks)[start:].strip()
            if href and href not in visible:
                self._chunks.append(f" <{href}>")
        if tag in self.BLOCKS:
            self._newline()

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self._chunks.append(data)

    def _newline(self) -> None:
        if self._chunks and not self._chunks[-1].endswith("\n"):
            self._chunks.append("\n")

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self._chunks).splitlines())
        return "\n".join(line for line in lines if line).strip()


def html_to_text(source: str) -> str:
    parser = _HtmlText()
    parser.feed(source)
    parser.close()
    return parser.text()


def decode_websafe(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def trim_quotes(source: str) -> str:
    """Drop quoted reply chains and signatures: compact input for an agent."""
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    cut = len(text)
    for marker in QUOTE_MARKERS:
        match = re.search(marker, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            cut = min(cut, match.start())
    text = text[:cut]
    text = "".join(line for line in text.splitlines(keepends=True) if not line.lstrip().startswith(">"))
    signature = re.search(r"^--\s*$", text, flags=re.MULTILINE)
    if signature:
        text = text[: signature.start()]
    return re.sub(r"[ \t]+$", "", re.sub(r"\n{3,}", "\n\n", text), flags=re.MULTILINE).strip()


def extract_codes(text: str) -> list[str]:
    return sorted({match.group(0) for match in CODE_RE.finditer(text or "")}, key=lambda c: (len(c), c))


def normalized_subject(subject: str) -> str:
    """Gmail threads common reply/forward prefixes but not a changed topic."""
    return re.sub(r"^(?:(?:re|fw|fwd|aw|sv):\s*)+", "", subject.strip(), flags=re.IGNORECASE).casefold()


def _headers(part: dict) -> dict[str, str]:
    return {header.get("name", "").lower(): header.get("value") or ""
            for header in part.get("headers", []) if header.get("name")}


def _is_file_part(part: dict) -> bool:
    """Tell real attachments/inline files from large text body parts."""
    headers = _headers(part)
    disposition = headers.get("content-disposition", "").lower()
    mime = part.get("mimeType", "").lower().split(";", 1)[0]
    body = part.get("body", {})
    if part.get("filename") or disposition.startswith("attachment"):
        return True
    if mime.startswith("multipart/") or mime in {"text/plain", "text/html"}:
        return False
    if disposition.startswith("inline"):
        return True
    return bool(body.get("data") or body.get("attachmentId"))


def _decode_text(raw: bytes, content_type: str) -> str:
    match = re.search(r"charset\s*=\s*[\"']?([^;\"'\s]+)", content_type, re.I)
    for charset in dict.fromkeys([*( [match.group(1)] if match else [] ), "utf-8", "windows-1252"]):
        try:
            return raw.decode(charset)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


class GmailClient:
    def __init__(self, session: Session, *, sender: str) -> None:
        self.session = session
        self.sender = sender

    # --- reading ------------------------------------------------------------

    def profile(self) -> dict:
        return self.session.api("GET", f"{GMAIL}/profile")

    def message_ids(self, query: str, limit: int = 25) -> list[dict]:
        return self.session.api(
            "GET", f"{GMAIL}/messages", params={"q": query, "maxResults": limit}
        ).get("messages", [])

    def search(self, query: str, limit: int = 25) -> list[dict]:
        """One compact record per hit (date/from/subject), without fetching bodies."""
        found = []
        for stub in self.message_ids(query, limit):
            message = self.session.api(
                "GET", f"{GMAIL}/messages/{stub['id']}",
                params={"format": "metadata", "metadataHeaders": ["Date", "From", "Subject"]})
            headers = _headers(message.get("payload") or {})
            found.append({"id": message.get("id"), "threadId": message.get("threadId"),
                          "date": headers.get("date", ""), "from": headers.get("from", ""),
                          "subject": headers.get("subject", "")})
        return found

    def get(self, message_id: str) -> dict:
        return self.session.api("GET", f"{GMAIL}/messages/{message_id}", params={"format": "full"})

    def thread(self, thread_id: str) -> dict:
        return self.session.api("GET", f"{GMAIL}/threads/{thread_id}", params={"format": "full"})

    def recent(self, word: str, *, minutes: int = 5, limit: int = 5, codes: bool = True) -> list[dict]:
        """Gmail's newer_than: is day-granular; after:<epoch> isolates mail that just arrived."""
        query = f"{word} after:{int(time.time()) - minutes * 60}"
        views = [self.view(self.get(stub["id"]), trim=False) for stub in self.message_ids(query, limit)]
        if codes:
            for view in views:
                subject = view["headers"].get("Subject", "")
                view["codes"] = extract_codes(f"{subject} {view['body']}")
        return views

    def view(self, message: dict, *, trim: bool = True) -> dict:
        """Flatten a raw message into headers, readable body text and attachment facts."""
        payload = message.get("payload") or {}
        headers = _headers(payload)
        body = self._body_text(message.get("id", ""), payload)
        return {
            "id": message.get("id"),
            "threadId": message.get("threadId"),
            "labelIds": message.get("labelIds", []),
            "headers": {name: headers[name.lower()] for name in HEADER_ORDER if headers.get(name.lower())},
            "snippet": message.get("snippet", ""),
            "body": trim_quotes(body) if trim else body,
            "attachments": self.attachment_index(payload),
        }

    def _body_text(self, message_id: str, part: dict) -> str:
        if _is_file_part(part):
            return ""
        mime = part.get("mimeType", "").lower().split(";", 1)[0]
        children = part.get("parts", [])
        if mime == "multipart/alternative":
            candidates = [(child.get("mimeType", "").lower(), self._body_text(message_id, child))
                          for child in children]
            for preferred in ("text/plain", "text/html"):
                for child_mime, text in candidates:
                    if child_mime.startswith(preferred) and text.strip():
                        return text
            return next((text for _, text in candidates if text.strip()), "")
        if children:
            return "\n\n".join(
                text for child in children if (text := self._body_text(message_id, child)).strip())
        if mime not in {"text/plain", "text/html"}:
            return ""
        raw = self._part_bytes(message_id, part)
        if raw is None:
            return ""
        text = _decode_text(raw, _headers(part).get("content-type", ""))
        return html_to_text(text) if mime == "text/html" else text

    def _part_bytes(self, message_id: str, part: dict) -> bytes | None:
        body = part.get("body", {})
        data = body.get("data")
        if not data and body.get("attachmentId"):
            data = self.session.api(
                "GET", f"{GMAIL}/messages/{message_id}/attachments/{body['attachmentId']}"
            ).get("data")
        return decode_websafe(data) if data else None

    @staticmethod
    def attachment_index(payload: dict) -> list[dict]:
        found: list[dict] = []

        def walk(part: dict) -> None:
            body = part.get("body") or {}
            if _is_file_part(part) and (body.get("data") or body.get("attachmentId")):
                found.append({"filename": part.get("filename") or "(unnamed)",
                              "mimeType": part.get("mimeType", "application/octet-stream"),
                              "size": body.get("size", 0), "attachmentId": body.get("attachmentId")})
            for child in part.get("parts", []):
                walk(child)

        walk(payload)
        return found

    # --- files --------------------------------------------------------------

    def download_files(self, message_id: str, output_dir: str | Path) -> list[dict]:
        """Save attachment and inline file parts byte-for-byte under safe local names."""
        message = self.get(message_id)
        target = Path(output_dir).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        used = {_filename_key(path.name) for path in target.iterdir()}
        saved = []
        for index, part in enumerate(_downloadable_parts(message.get("payload", {})), start=1):
            data = self._part_bytes(message_id, part)
            if not data:
                raise WorkspaceError(
                    f"message {message_id} has an empty or unreadable file part at position {index}")
            expected = part.get("body", {}).get("size")
            if isinstance(expected, int) and expected != len(data):
                raise WorkspaceError(
                    f"message {message_id} file part {index} has size {len(data)}, expected {expected}")
            original = part.get("filename") or f"attachment-{index}"
            name = _safe_filename(original, f"attachment-{index}")
            if not Path(name).suffix:
                extension = mimetypes.guess_extension(
                    part.get("mimeType", "").split(";", 1)[0].lower(), strict=False)
                if extension:
                    name += extension
            name = _unique_name(name, used)
            used.add(_filename_key(name))
            path = target / name
            path.write_bytes(data)
            saved.append({"path": str(path), "filename": name, "original_filename": original,
                          "mime_type": part.get("mimeType", ""), "size": path.stat().st_size})
        return saved

    def save_text(self, message_id: str, output_path: str | Path) -> dict:
        """Save source headers plus the complete readable body, without summarizing it."""
        view = self.view(self.get(message_id), trim=False)
        if not view["body"].strip():
            raise WorkspaceError(f"message {message_id} has no readable text body")
        target = Path(output_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{name}: {value}" for name, value in view["headers"].items()]
        target.write_text("\n".join([*lines, "", view["body"]]), encoding="utf-8")
        return {"path": str(target), "mime_type": "text/plain", "size": target.stat().st_size}

    # --- composing ----------------------------------------------------------

    def build(self, to: str, subject: str, body: str, *, cc: str | None = None,
              html: bool = False, html_body: str | None = None,
              reply_to_message: str | None = None) -> tuple[str, str | None]:
        """Build the base64url MIME payload; replies thread, quote and keep the subject.

        `html=True` means `body` is HTML and the plain-text alternative is derived from it;
        `html_body` instead keeps `body` as the authored plain text and adds that HTML
        alternative beside it.
        """
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        if cc:
            message["Cc"] = cc
        message["Subject"] = subject
        thread_id = None
        quote_plain = quote_html = ""
        if reply_to_message:
            original = self.view(self.get(reply_to_message), trim=True)
            reference = original["headers"].get("Message-ID")
            if not reference:
                raise WorkspaceError(
                    f"message {reply_to_message} has no Message-ID header; cannot thread a reply")
            if normalized_subject(subject) != normalized_subject(original["headers"].get("Subject", "")):
                raise WorkspaceError(
                    "reply subject must match the original (an added Re: prefix is allowed) to "
                    f"preserve Gmail threading; original: {original['headers'].get('Subject', '(none)')!r}")
            thread_id = original["threadId"]
            message["In-Reply-To"] = reference
            message["References"] = " ".join(
                filter(None, [original["headers"].get("References"), reference]))
            lead = f"On {original['headers'].get('Date', '?')}, {original['headers'].get('From', '?')} wrote:"
            quoted = "\n".join(f"> {line}" if line else ">" for line in original["body"].splitlines())
            quote_plain = f"\n\n{lead}\n{quoted}"
            quote_html = (
                f'<br><br><div class="gmail_quote">{html_module.escape(lead)}'
                '<blockquote style="margin:0 0 0 .8ex;border-left:1px #ccc solid;padding-left:1ex">'
                f'{html_module.escape(original["body"]).replace(chr(10), "<br>")}</blockquote></div>')
        if html and html_body:
            raise WorkspaceError("pass either --html (the body is HTML) or --html-file, not both")
        if html:
            message.set_content(html_to_text(body) + quote_plain)
            message.add_alternative(body + quote_html, subtype="html")
        elif html_body:
            message.set_content(body + quote_plain)
            message.add_alternative(html_body + quote_html, subtype="html")
        else:
            message.set_content(body + quote_plain)
        raw = base64.urlsafe_b64encode(message.as_bytes(policy=SMTP)).decode("ascii")
        return raw, thread_id

    def _payload(self, raw: str, thread_id: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id
        return payload

    def create_draft(self, to: str, subject: str, body: str, **kw) -> dict:
        """Create a draft. Nothing is sent."""
        raw, thread_id = self.build(to, subject, body, **kw)
        return self.session.api("POST", f"{GMAIL}/drafts", json={"message": self._payload(raw, thread_id)})

    def send(self, to: str, subject: str, body: str, **kw) -> dict:
        """Send immediately. No idempotency guard: one call is one mail."""
        raw, thread_id = self.build(to, subject, body, **kw)
        return self.session.api("POST", f"{GMAIL}/messages/send", json=self._payload(raw, thread_id))

    def drafts(self, limit: int = 20) -> list[dict]:
        return self.session.api("GET", f"{GMAIL}/drafts", params={"maxResults": limit}).get("drafts", [])

    def get_draft(self, draft_id: str) -> dict:
        data = self.session.api("GET", f"{GMAIL}/drafts/{draft_id}", params={"format": "full"})
        return {"id": data.get("id"), "message": self.view(data.get("message", {}), trim=False)}

    def send_draft(self, draft_id: str) -> dict:
        return self.session.api("POST", f"{GMAIL}/drafts/send", json={"id": draft_id})

    def delete_draft(self, draft_id: str) -> dict:
        self.session.request("DELETE", f"{GMAIL}/drafts/{draft_id}")
        return {"deleted": draft_id}

    # --- labels -------------------------------------------------------------

    def labels(self) -> list[dict]:
        return self.session.api("GET", f"{GMAIL}/labels").get("labels", [])

    def resolve_labels(self, values: list[str] | None, known: list[dict]) -> list[str]:
        """Accept ids or names, repeatable or comma-separated."""
        if not values:
            return []
        by_id = {item["id"]: item["id"] for item in known}
        by_name = {item.get("name", "").casefold(): item["id"] for item in known}
        resolved: list[str] = []
        for value in values:
            for label in (part.strip() for part in value.split(",")):
                if not label:
                    continue
                label_id = by_id.get(label) or by_name.get(label.casefold())
                if not label_id:
                    raise WorkspaceError(f"unknown Gmail label {label!r}; run gmail-labels")
                if label_id not in resolved:
                    resolved.append(label_id)
        return resolved

    def modify_labels(self, message_id: str, add: list[str] | None = None,
                      remove: list[str] | None = None) -> dict:
        known = self.labels()
        add_ids = self.resolve_labels(add, known)
        remove_ids = self.resolve_labels(remove, known)
        if not add_ids and not remove_ids:
            raise WorkspaceError("pass --add LABEL or --remove LABEL")
        return self.session.api("POST", f"{GMAIL}/messages/{message_id}/modify",
                                json={"addLabelIds": add_ids, "removeLabelIds": remove_ids})


def _downloadable_parts(part: dict) -> Iterator[dict]:
    body = part.get("body", {})
    if _is_file_part(part) and (body.get("data") or body.get("attachmentId")):
        yield part
        return
    for child in part.get("parts", []):
        yield from _downloadable_parts(child)


def _filename_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _truncate_utf8(value: str, max_bytes: int) -> str:
    while len(value.encode("utf-8")) > max_bytes:
        value = value[:-1]
    return value


def _safe_filename(original: str, fallback: str) -> str:
    """Make an untrusted MIME filename safe and portable without touching the bytes."""
    name = original.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(
        "_" if char in '<>:"/\\|?*' or unicodedata.category(char) in {"Cc", "Cf"} else char
        for char in name
    ).strip(" .")
    if not name or name in {".", ".."}:
        name = fallback
    stem, suffix = Path(name).stem, Path(name).suffix
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    if stem.upper() in reserved:
        stem = f"_{stem}"
    suffix = _truncate_utf8(suffix, 40)
    stem = _truncate_utf8(stem, 240 - len(suffix.encode("utf-8")))
    return f"{stem}{suffix}" or fallback


def _unique_name(name: str, used: set[str]) -> str:
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 2
    while _filename_key(name) in used:
        marker = f"-{counter}"
        budget = 240 - len(suffix.encode("utf-8")) - len(marker.encode("utf-8"))
        name = f"{_truncate_utf8(stem, budget)}{marker}{suffix}"
        counter += 1
    return name
