"""Google Drive client for the configured Workspace account — list, search, read, create."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from uuid import uuid4

from base import BaseClient

DRIVE_API = "https://www.googleapis.com/drive/v3"
_FILE_FIELDS = (
    "files(id, name, mimeType, size, md5Checksum, parents, webViewLink, "
    "createdTime, modifiedTime)"
)
_UPLOAD_FIELDS = "id,name,mimeType,size,md5Checksum,parents,webViewLink"
_MULTIPART_LIMIT = 5 * 1024 * 1024


class DriveClient(BaseClient):
    """List, search, read, and create Drive files (full drive scope)."""

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
                              "modifiedTime, size, md5Checksum, parents, owners"},
        )
        r.raise_for_status()
        return r.json()

    def download(self, file_id: str) -> bytes:
        r = self.http.get(f"{DRIVE_API}/files/{file_id}", params={"alt": "media"})
        r.raise_for_status()
        return r.content

    def export_markdown(self, file_id: str) -> tuple[dict, str]:
        """Export a Google Doc as Markdown. Returns (metadata, markdown)."""
        meta = self.http.get(
            f"{DRIVE_API}/files/{file_id}",
            params={"fields": "id, name, mimeType", "supportsAllDrives": "true"},
        )
        meta.raise_for_status()
        metadata = meta.json()
        if metadata.get("mimeType") != "application/vnd.google-apps.document":
            raise ValueError(f"{file_id} is {metadata.get('mimeType')}, not a Google Doc")
        r = self.http.get(
            f"{DRIVE_API}/files/{file_id}/export", params={"mimeType": "text/markdown"}
        )
        r.raise_for_status()
        return metadata, r.content.decode("utf-8-sig")

    def create(self, name: str, mime_type: str, folder_id: str | None = None) -> dict:
        body: dict[str, Any] = {"name": name, "mimeType": mime_type}
        if folder_id:
            body["parents"] = [folder_id]
        r = self.http.post(
            f"{DRIVE_API}/files", params={"fields": "id, name, webViewLink"}, json=body
        )
        r.raise_for_status()
        return r.json()

    def upload(
        self, path: str | Path, name: str | None = None, folder_id: str | None = None
    ) -> dict:
        """Upload a local file, using resumable upload when it exceeds 5 MiB."""
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"Upload source is not a file: {source}")

        mime_type = (
            mimetypes.guess_type(source.name, strict=False)[0] or "application/octet-stream"
        )
        metadata: dict[str, Any] = {"name": name or source.name}
        if folder_id:
            metadata["parents"] = [folder_id]

        size = source.stat().st_size
        if size > _MULTIPART_LIMIT:
            init = self.http.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                params={"uploadType": "resumable", "fields": _UPLOAD_FIELDS},
                headers={
                    "X-Upload-Content-Type": mime_type,
                    "X-Upload-Content-Length": str(size),
                },
                json=metadata,
            )
            init.raise_for_status()
            upload_url = init.headers.get("Location")
            if not upload_url:
                raise RuntimeError("Drive resumable upload did not return a Location header")
            with source.open("rb") as content:
                response = self.http.put(
                    upload_url,
                    headers={"Content-Type": mime_type, "Content-Length": str(size)},
                    content=content,
                )
            response.raise_for_status()
            return response.json()

        boundary = f"workspace-upload-{uuid4().hex}"
        content = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n"
        ).encode() + source.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        r = self.http.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            params={"uploadType": "multipart", "fields": _UPLOAD_FIELDS},
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            content=content,
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
