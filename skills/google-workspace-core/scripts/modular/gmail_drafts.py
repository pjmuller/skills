"""Gmail client for the configured Workspace account — read, search, draft, send, label."""

from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

from base import BaseClient

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
from auth import EXPECTED_EMAIL

FROM_ADDRESS = EXPECTED_EMAIL


class GmailClient(BaseClient):
    """Read, search, draft, send, and label emails for the configured Workspace account."""

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

    def _build_raw(
        self, to: str, subject: str, body: str, reply_to_message_id: str | None
    ) -> dict:
        """Build the {raw, threadId?} payload, threading the reply if given."""
        msg = MIMEText(body)
        msg["to"] = to
        msg["from"] = FROM_ADDRESS
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
        return payload

    def send(
        self, to: str, subject: str, body: str, reply_to_message_id: str | None = None
    ) -> dict:
        """Send (or reply to) an email immediately. No idempotency guard — see SKILL.md."""
        payload = self._build_raw(to, subject, body, reply_to_message_id)
        r = self.http.post(f"{GMAIL_API}/users/me/messages/send", json=payload)
        r.raise_for_status()
        return r.json()

    def create_draft(
        self, to: str, subject: str, body: str, reply_to_message_id: str | None = None
    ) -> dict:
        """Create a draft (nothing is sent). Returns {id, message:{id, threadId}}."""
        payload = self._build_raw(to, subject, body, reply_to_message_id)
        r = self.http.post(
            f"{GMAIL_API}/users/me/drafts", json={"message": payload}
        )
        r.raise_for_status()
        return r.json()

    def list_drafts(self, max_results: int = 20) -> list[dict]:
        r = self.http.get(
            f"{GMAIL_API}/users/me/drafts", params={"maxResults": max_results}
        )
        r.raise_for_status()
        return r.json().get("drafts", [])

    def get_draft(self, draft_id: str) -> dict:
        r = self.http.get(
            f"{GMAIL_API}/users/me/drafts/{draft_id}", params={"format": "full"}
        )
        r.raise_for_status()
        data = r.json()
        return {"id": data.get("id"), "message": self.parse(data.get("message", {}))}

    def send_draft(self, draft_id: str) -> dict:
        """Send an existing draft by id. No idempotency guard — see SKILL.md."""
        r = self.http.post(
            f"{GMAIL_API}/users/me/drafts/send", json={"id": draft_id}
        )
        r.raise_for_status()
        return r.json()

    def delete_draft(self, draft_id: str) -> dict:
        r = self.http.delete(f"{GMAIL_API}/users/me/drafts/{draft_id}")
        r.raise_for_status()
        return {"deleted": draft_id}

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

    @staticmethod
    def parse(message: dict) -> dict:
        """Flatten a raw Gmail message into headers + decoded plain-text body."""
        payload = message.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                        "utf-8", errors="ignore"
                    )
                    break
        elif payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                "utf-8", errors="ignore"
            )
        return {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
            "snippet": message.get("snippet", ""),
            "body": body,
        }
