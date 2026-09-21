"""Google Drive client for the configured Workspace account — list, search, read, write (full scope)."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from base import BaseClient

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
_FILE_FIELDS = "files(id, name, mimeType, webViewLink, createdTime, modifiedTime)"


class DriveClient(BaseClient):
    """List, search, read, create, and write Drive files (full drive scope)."""

    def list_files(self, folder_id: str | None = None, max_results: int = 100) -> list[dict]:
        q = ["trashed=false"]
        if folder_id:
            q.append(f"'{folder_id}' in parents")
        r = self.http.get(
            f"{DRIVE_API}/files",
            params={"q": " and ".join(q), "spaces": "drive", "pageSize": max_results,
                    "fields": _FILE_FIELDS},
        )
        r.raise_for_status()
        return r.json().get("files", [])

    def search(self, query: str, max_results: int = 50) -> list[dict]:
        r = self.http.get(
            f"{DRIVE_API}/files",
            params={"q": query, "spaces": "drive", "pageSize": max_results,
                    "fields": _FILE_FIELDS},
        )
        r.raise_for_status()
        return r.json().get("files", [])

    def metadata(self, file_id: str) -> dict:
        r = self.http.get(
            f"{DRIVE_API}/files/{file_id}",
            params={"fields": "id, name, mimeType, webViewLink, createdTime, "
                              "modifiedTime, size, owners"},
        )
        r.raise_for_status()
        return r.json()

    def download(self, file_id: str) -> bytes:
        r = self.http.get(f"{DRIVE_API}/files/{file_id}", params={"alt": "media"})
        r.raise_for_status()
        return r.content

    def create(self, name: str, mime_type: str, folder_id: str | None = None) -> dict:
        """Create an empty file/folder (metadata only — no content)."""
        body: dict[str, Any] = {"name": name, "mimeType": mime_type}
        if folder_id:
            body["parents"] = [folder_id]
        r = self.http.post(
            f"{DRIVE_API}/files", params={"fields": "id, name, webViewLink"}, json=body
        )
        r.raise_for_status()
        return r.json()

    def upload(
        self,
        name: str,
        local_path: str,
        folder_id: str | None = None,
        mime_type: str | None = None,
    ) -> dict:
        """Create a new file from local bytes (multipart: metadata + media)."""
        data = Path(local_path).read_bytes()
        mime = mime_type or mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        meta: dict[str, Any] = {"name": name}
        if folder_id:
            meta["parents"] = [folder_id]
        files = {
            "metadata": (None, json.dumps(meta), "application/json; charset=UTF-8"),
            "file": (name, data, mime),
        }
        r = self.http.post(
            f"{DRIVE_UPLOAD_API}/files",
            params={"uploadType": "multipart", "fields": "id, name, mimeType, webViewLink"},
            files=files,
        )
        r.raise_for_status()
        return r.json()

    def update_content(self, file_id: str, local_path: str, mime_type: str | None = None) -> dict:
        """Overwrite an existing file's bytes (media upload)."""
        data = Path(local_path).read_bytes()
        mime = mime_type or mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        r = self.http.patch(
            f"{DRIVE_UPLOAD_API}/files/{file_id}",
            params={"uploadType": "media", "fields": "id, name, mimeType, webViewLink, modifiedTime"},
            headers={"Content-Type": mime},
            content=data,
        )
        r.raise_for_status()
        return r.json()

    def copy(self, file_id: str, name: str, folder_id: str | None = None) -> dict:
        """Copy a file. Keeps the same mimeType; new file lands in `folder_id` (or root)."""
        body: dict[str, Any] = {"name": name}
        if folder_id:
            body["parents"] = [folder_id]
        r = self.http.post(
            f"{DRIVE_API}/files/{file_id}/copy",
            params={"fields": "id, name, webViewLink"},
            json=body,
        )
        r.raise_for_status()
        return r.json()

    def trash(self, file_id: str) -> dict:
        """Move a file to the trash (reversible — not a permanent delete)."""
        r = self.http.patch(
            f"{DRIVE_API}/files/{file_id}",
            params={"fields": "id, name, trashed"},
            json={"trashed": True},
        )
        r.raise_for_status()
        return r.json()
