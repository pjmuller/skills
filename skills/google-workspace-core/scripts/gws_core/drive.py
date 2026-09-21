"""Drive: list, search, read, copy, upload, replace content, export, trash."""

from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from .errors import WorkspaceError
from .inputs import extract_id
from .session import DRIVE, DRIVE_UPLOAD, Session

FILE_FIELDS = "id,name,mimeType,size,parents,webViewLink,modifiedTime,driveId,trashed"
DOC_MIME = "application/vnd.google-apps.document"
EXPORT_MIME = {
    "pdf": "application/pdf",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "html": "text/html",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "epub": "application/epub+zip",
    "odt": "application/vnd.oasis.opendocument.text",
}
RESUMABLE_LIMIT = 5 * 1024 * 1024


class DriveClient:
    def __init__(self, session: Session) -> None:
        self.session = session

    def files(self, query: str, limit: int) -> list[dict]:
        found: list[dict] = []
        page: str | None = None
        while len(found) < limit:
            params = {
                "q": query,
                "pageSize": min(1000, limit - len(found)),
                "fields": f"nextPageToken,files({FILE_FIELDS})",
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
                "corpora": "allDrives",
                "orderBy": "folder,name_natural",
            }
            if page:
                params["pageToken"] = page
            data = self.session.api("GET", f"{DRIVE}/files", params=params)
            found += data.get("files", [])
            page = data.get("nextPageToken")
            if not page:
                break
        return found[:limit]

    def list_folder(self, folder: str, limit: int = 100) -> list[dict]:
        return self.files(f"'{extract_id(folder)}' in parents and trashed=false", limit)

    def search(self, query: str, limit: int = 50) -> list[dict]:
        return self.files(f"({query}) and trashed=false", limit)

    def get(self, file: str) -> dict:
        fields = f"{FILE_FIELDS},owners(displayName,emailAddress),createdTime,md5Checksum"
        return self.session.api("GET", f"{DRIVE}/files/{extract_id(file)}", params={"fields": fields})

    def parent_of(self, file: str) -> str | None:
        parents = self.get_fields(file, "parents").get("parents") or []
        return next(iter(parents), None)

    def get_fields(self, file: str, fields: str) -> dict:
        return self.session.api("GET", f"{DRIVE}/files/{extract_id(file)}", params={"fields": fields})

    def create(self, name: str, mime: str, parent: str | None = None) -> dict:
        body: dict[str, Any] = {"name": name, "mimeType": mime}
        if parent:
            body["parents"] = [extract_id(parent)]
        return self.session.api("POST", f"{DRIVE}/files", params={"fields": FILE_FIELDS}, json=body)

    def copy(self, file: str, name: str, parent: str | None = None) -> dict:
        body: dict[str, Any] = {"name": name}
        if parent:
            body["parents"] = [extract_id(parent)]
        return self.session.api("POST", f"{DRIVE}/files/{extract_id(file)}/copy",
                                params={"fields": FILE_FIELDS}, json=body)

    def trash(self, file: str) -> dict:
        return self.session.api("PATCH", f"{DRIVE}/files/{extract_id(file)}",
                                params={"fields": "id,name,trashed"}, json={"trashed": True})

    def upload(self, path: str | Path, name: str | None = None, parent: str | None = None,
               mime: str | None = None) -> dict:
        """Upload a local file; resumable above 5 MiB, multipart below. Shared-drive safe."""
        source = Path(path).expanduser()
        if not source.is_file():
            raise WorkspaceError(f"no such file: {source}")
        metadata: dict[str, Any] = {"name": name or source.name}
        if parent:
            metadata["parents"] = [extract_id(parent)]
        mime = mime or mimetypes.guess_type(source.name, strict=False)[0] or "application/octet-stream"
        if source.stat().st_size > RESUMABLE_LIMIT:
            return self._resumable(source, metadata, mime)
        boundary = uuid.uuid4().hex
        body = b"".join([
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
            json.dumps(metadata).encode(),
            f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode(),
            source.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        return self.session.api(
            "POST", DRIVE_UPLOAD,
            params={"uploadType": "multipart", "fields": FILE_FIELDS},
            content=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        )

    def _resumable(self, source: Path, metadata: dict, mime: str) -> dict:
        size = source.stat().st_size
        init = self.session.request(
            "POST", DRIVE_UPLOAD,
            params={"uploadType": "resumable", "fields": FILE_FIELDS},
            headers={"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(size)},
            json=metadata,
        )
        location = init.headers.get("Location")
        if not location:
            raise WorkspaceError("Drive resumable upload did not return a Location header")
        with source.open("rb") as content:
            response = self.session.request(
                "PUT", location,
                headers={"Content-Type": mime, "Content-Length": str(size)}, content=content,
            )
        return response.json()

    def replace_content(self, file: str, path: str | Path, mime: str | None = None) -> dict:
        """Overwrite an existing file's bytes, keeping its id, name and sharing."""
        source = Path(path).expanduser()
        if not source.is_file():
            raise WorkspaceError(f"no such file: {source}")
        mime = mime or mimetypes.guess_type(source.name, strict=False)[0] or "application/octet-stream"
        return self.session.api(
            "PATCH", f"{DRIVE_UPLOAD}/{extract_id(file)}",
            params={"uploadType": "media", "fields": f"{FILE_FIELDS},md5Checksum"},
            headers={"Content-Type": mime}, content=source.read_bytes(),
        )

    def download(self, file: str) -> bytes:
        return self.session.request("GET", f"{DRIVE}/files/{extract_id(file)}",
                                    params={"alt": "media"}).content

    def export(self, file: str, fmt: str) -> bytes:
        mime = EXPORT_MIME.get(fmt.lower())
        if not mime:
            raise WorkspaceError(f"unknown format {fmt!r}; use {'/'.join(sorted(EXPORT_MIME))}")
        return self.session.request("GET", f"{DRIVE}/files/{extract_id(file)}/export",
                                    params={"mimeType": mime}).content

    def export_markdown(self, file: str) -> tuple[dict, str]:
        """Google's own Markdown export of a Doc, with the file metadata that produced it."""
        metadata = self.get_fields(file, "id,name,mimeType")
        if metadata.get("mimeType") != DOC_MIME:
            raise WorkspaceError(f"{metadata.get('id')} is {metadata.get('mimeType')}, not a Google Doc")
        raw = self.session.request("GET", f"{DRIVE}/files/{extract_id(file)}/export",
                                   params={"mimeType": "text/markdown"}).content
        return metadata, raw.decode("utf-8-sig")

    def share_anyone_reader(self, file: str) -> dict:
        return self.session.api("POST", f"{DRIVE}/files/{extract_id(file)}/permissions",
                                json={"role": "reader", "type": "anyone"})

    def unshare(self, file: str, permission_id: str) -> None:
        self.session.request("DELETE", f"{DRIVE}/files/{extract_id(file)}/permissions/{permission_id}")
