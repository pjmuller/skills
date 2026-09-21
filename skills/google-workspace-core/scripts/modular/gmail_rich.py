"""Gmail client for the configured Workspace account — read, search, send, label."""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.parser import HTMLParser
import mimetypes
from pathlib import Path
import re
from typing import Any
import unicodedata

from auth import EXPECTED_EMAIL
from base import BaseClient

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


class _ReadableHTMLParser(HTMLParser):
    """Turn an HTML-only mail body into readable text without summarizing it."""

    _BLOCK_TAGS = {
        "address",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "pre",
        "table",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._ignored_depth = 0
        self._links: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in self._BLOCK_TAGS:
            self._newline()
        if tag == "a":
            href = dict(attrs).get("href") or ""
            self._links.append((href, len("".join(self._chunks))))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag == "a" and self._links:
            href, start = self._links.pop()
            visible = "".join(self._chunks)[start:].strip()
            if href and href not in visible:
                self._chunks.append(f" <{href}>")
        if tag in self._BLOCK_TAGS:
            self._newline()

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._chunks.append(data)

    def _newline(self) -> None:
        if self._chunks and not self._chunks[-1].endswith("\n"):
            self._chunks.append("\n")

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self._chunks).splitlines())
        return "\n".join(line for line in lines if line).strip()


class GmailClient(BaseClient):
    """Read, search, send, and label emails for the configured Workspace account."""

    def me(self) -> dict:
        r = self.http.get(f"{GMAIL_API}/users/me/profile")
        r.raise_for_status()
        return r.json()

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        r = self.http.get(
            f"{GMAIL_API}/users/me/messages",
            params={"q": query, "maxResults": max_results},
        )
        r.raise_for_status()
        return r.json().get("messages", [])

    def get_message(self, message_id: str) -> dict:
        r = self.http.get(
            f"{GMAIL_API}/users/me/messages/{message_id}", params={"format": "full"}
        )
        r.raise_for_status()
        return r.json()

    def get_thread(self, thread_id: str) -> dict:
        r = self.http.get(
            f"{GMAIL_API}/users/me/threads/{thread_id}", params={"format": "full"}
        )
        r.raise_for_status()
        return r.json()

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_message_id: str | None = None,
        *,
        html: str | None = None,
    ) -> dict:
        if html is None:
            msg = MIMEText(body)
        else:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))
        msg["to"] = to
        msg["from"] = EXPECTED_EMAIL
        msg["subject"] = subject
        payload: dict[str, Any] = {}
        if reply_to_message_id:
            orig = self.http.get(
                f"{GMAIL_API}/users/me/messages/{reply_to_message_id}",
                params={"format": "metadata", "metadataHeaders": "Message-ID"},
            )
            orig.raise_for_status()
            orig_json = orig.json()
            headers = {
                h["name"].lower(): h["value"]
                for h in orig_json.get("payload", {}).get("headers", [])
            }
            mid = headers.get("message-id", "")
            msg["In-Reply-To"] = mid
            msg["References"] = mid
            payload["threadId"] = orig_json.get("threadId")
        payload["raw"] = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = self.http.post(f"{GMAIL_API}/users/me/messages/send", json=payload)
        r.raise_for_status()
        return r.json()

    def create_draft(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict:
        msg = MIMEText(body)
        msg["to"] = to
        msg["from"] = EXPECTED_EMAIL
        if cc:
            msg["cc"] = cc
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = self.http.post(
            f"{GMAIL_API}/users/me/drafts", json={"message": {"raw": raw}}
        )
        r.raise_for_status()
        return r.json()

    def list_labels(self) -> list[dict]:
        r = self.http.get(f"{GMAIL_API}/users/me/labels")
        r.raise_for_status()
        return r.json().get("labels", [])

    def modify_labels(
        self, message_id: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> dict:
        r = self.http.post(
            f"{GMAIL_API}/users/me/messages/{message_id}/modify",
            json={"addLabelIds": add or [], "removeLabelIds": remove or []},
        )
        r.raise_for_status()
        return r.json()

    def download_files(self, message_id: str, output_dir: str | Path) -> list[dict]:
        """Download attachment and inline file parts without changing their bytes."""
        message = self.get_message(message_id)
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        downloaded = []
        used_names = {self._filename_key(path.name) for path in target.iterdir()}

        for index, part in enumerate(
            self._walk_downloadable_parts(message.get("payload", {})), start=1
        ):
            mime_type = part.get("mimeType", "")
            body = part.get("body", {})
            original_name = part.get("filename") or ""
            data = self._load_part_bytes(message_id, part)
            if not data:
                raise ValueError(
                    f"Message {message_id} contains an empty or unreadable file part "
                    f"at position {index}"
                )
            expected_size = body.get("size")
            if isinstance(expected_size, int) and expected_size != len(data):
                raise ValueError(
                    f"Message {message_id} file part {index} has size {len(data)}, "
                    f"expected {expected_size}"
                )

            original_name = original_name or f"attachment-{index}"
            name = self._safe_filename(original_name, fallback=f"attachment-{index}")
            if not Path(name).suffix:
                extension = mimetypes.guess_extension(
                    mime_type.split(";", 1)[0].lower(), strict=False
                )
                if extension:
                    name += extension
            stem, suffix = Path(name).stem, Path(name).suffix
            counter = 2
            while self._filename_key(name) in used_names:
                collision_marker = f"-{counter}"
                max_stem_bytes = 240 - len(suffix.encode("utf-8")) - len(
                    collision_marker.encode("utf-8")
                )
                name = (
                    f"{self._truncate_utf8(stem, max_stem_bytes)}"
                    f"{collision_marker}{suffix}"
                )
                counter += 1
            used_names.add(self._filename_key(name))
            path = target / name
            path.write_bytes(data)
            downloaded.append(
                {
                    "path": str(path),
                    "filename": name,
                    "original_filename": original_name,
                    "mime_type": mime_type,
                    "size": path.stat().st_size,
                }
            )
        return downloaded

    def save_text(self, message_id: str, output_path: str | Path) -> dict:
        """Save source headers and readable body text without summarizing it."""
        parsed = self.parse_message(self.get_message(message_id))
        if not parsed["body"].strip():
            raise ValueError(f"Message {message_id} has no readable text body")

        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        headers = (
            ("From", "from"),
            ("To", "to"),
            ("Cc", "cc"),
            ("Reply-To", "reply_to"),
            ("Date", "date"),
            ("Subject", "subject"),
            ("Message-ID", "message_id"),
        )
        content = "\n".join(
            [*(f"{label}: {parsed[key]}" for label, key in headers if parsed[key]), "", parsed["body"]]
        )
        target.write_text(content, encoding="utf-8")
        return {"path": str(target), "mime_type": "text/plain", "size": target.stat().st_size}

    @staticmethod
    def _decode_base64url(data: str) -> bytes:
        """Decode Gmail base64url data, which may omit trailing padding."""
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

    @staticmethod
    def _walk_parts(part: dict) -> Iterator[dict]:
        yield part
        for child in part.get("parts", []):
            yield from GmailClient._walk_parts(child)

    @classmethod
    def _walk_downloadable_parts(cls, part: dict) -> Iterator[dict]:
        body = part.get("body", {})
        if cls._is_file_part(part) and (body.get("data") or body.get("attachmentId")):
            yield part
            return
        for child in part.get("parts", []):
            yield from cls._walk_downloadable_parts(child)

    @staticmethod
    def _part_headers(part: dict) -> dict[str, str]:
        return {
            header.get("name", "").lower(): header.get("value") or ""
            for header in part.get("headers", [])
            if header.get("name")
        }

    @classmethod
    def _is_file_part(cls, part: dict) -> bool:
        """Distinguish real attachments/inline files from large text body parts."""
        headers = cls._part_headers(part)
        disposition = headers.get("content-disposition", "").lower()
        mime_type = part.get("mimeType", "").lower().split(";", 1)[0]
        body = part.get("body", {})
        if part.get("filename") or disposition.startswith("attachment"):
            return True
        if mime_type.startswith("multipart/"):
            return False
        if mime_type in {"text/plain", "text/html"}:
            return False
        if disposition.startswith("inline"):
            return True
        return bool(body.get("data") or body.get("attachmentId"))

    def _load_part_bytes(self, message_id: str, part: dict) -> bytes | None:
        body = part.get("body", {})
        data = body.get("data")
        if not data and body.get("attachmentId"):
            r = self.http.get(
                f"{GMAIL_API}/users/me/messages/{message_id}/attachments/"
                f"{body['attachmentId']}"
            )
            r.raise_for_status()
            data = r.json().get("data")
        return self._decode_base64url(data) if data else None

    @staticmethod
    def _filename_key(name: str) -> str:
        return unicodedata.normalize("NFC", name).casefold()

    @classmethod
    def _safe_filename(cls, original_name: str, fallback: str) -> str:
        """Make an untrusted MIME filename safe and portable without changing file bytes."""
        name = original_name.replace("\\", "/").rsplit("/", 1)[-1]
        name = "".join(
            "_"
            if char in '<>:"/\\|?*' or unicodedata.category(char) in {"Cc", "Cf"}
            else char
            for char in name
        ).strip(" .")
        if not name or name in {".", ".."}:
            name = fallback

        stem, suffix = Path(name).stem, Path(name).suffix
        if stem.upper() in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            stem = f"_{stem}"
        suffix = cls._truncate_utf8(suffix, 40)
        stem = cls._truncate_utf8(stem, 240 - len(suffix.encode("utf-8")))
        return f"{stem}{suffix}" or fallback

    @staticmethod
    def _truncate_utf8(value: str, max_bytes: int) -> str:
        while len(value.encode("utf-8")) > max_bytes:
            value = value[:-1]
        return value

    def parse_message(self, message: dict) -> dict:
        message_id = message.get("id", "")
        return self.parse(
            message,
            attachment_loader=lambda part: self._load_part_bytes(message_id, part),
        )

    @staticmethod
    def parse(
        message: dict,
        attachment_loader: Callable[[dict], bytes | None] | None = None,
    ) -> dict:
        """Flatten a raw Gmail message into headers plus readable complete body text."""
        payload = message.get("payload", {})
        headers = GmailClient._part_headers(payload)
        loader = attachment_loader or (
            lambda part: GmailClient._decode_base64url(part.get("body", {}).get("data", ""))
            if part.get("body", {}).get("data")
            else None
        )
        body = GmailClient._extract_body(payload, loader)
        return {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "label_ids": message.get("labelIds", []),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "cc": headers.get("cc", ""),
            "reply_to": headers.get("reply-to", ""),
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
            "message_id": headers.get("message-id", ""),
            "snippet": message.get("snippet", ""),
            "body": body,
        }

    @classmethod
    def _extract_body(
        cls, part: dict, loader: Callable[[dict], bytes | None]
    ) -> str:
        if cls._is_file_part(part):
            return ""
        mime_type = part.get("mimeType", "").lower().split(";", 1)[0]
        children = part.get("parts", [])
        if mime_type == "multipart/alternative":
            candidates = [
                (
                    child.get("mimeType", "").lower(),
                    cls._extract_body(child, loader),
                )
                for child in children
            ]
            for preferred in ("text/plain", "text/html"):
                for child_type, text in candidates:
                    if child_type.startswith(preferred) and text.strip():
                        return text
            return next((text for _, text in candidates if text.strip()), "")
        if children:
            return "\n\n".join(
                text for child in children if (text := cls._extract_body(child, loader)).strip()
            )
        if mime_type not in {"text/plain", "text/html"}:
            return ""

        raw = loader(part)
        if raw is None:
            return ""
        text = cls._decode_text(raw, cls._part_headers(part).get("content-type", ""))
        if mime_type == "text/html":
            parser = _ReadableHTMLParser()
            parser.feed(text)
            parser.close()
            return parser.text()
        return text

    @staticmethod
    def _decode_text(raw: bytes, content_type: str) -> str:
        charset_match = re.search(r"charset\s*=\s*[\"']?([^;\"'\s]+)", content_type, re.I)
        candidates = [charset_match.group(1)] if charset_match else []
        candidates.extend(["utf-8", "windows-1252"])
        for charset in dict.fromkeys(candidates):
            try:
                return raw.decode(charset)
            except (LookupError, UnicodeDecodeError):
                continue
        return raw.decode("utf-8", errors="replace")
