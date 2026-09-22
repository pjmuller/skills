"""Authenticated transport and the Workspace facade importers use."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx

from .auth import USERINFO, credentials, granted_scopes
from .config import WorkspaceConfig
from .errors import ApiError

DRIVE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
DOCS = "https://docs.googleapis.com/v1/documents"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
SLIDES = "https://slides.googleapis.com/v1/presentations"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"


class Session:
    """One bearer-token httpx client. No module-level state, so two accounts can coexist."""

    def __init__(self, token: str, *, timeout: float = 120) -> None:
        self.token = token
        self.timeout = timeout
        self._http: httpx.Client | None = None

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                headers={"Authorization": f"Bearer {self.token}"}, timeout=self.timeout
            )
        return self._http

    def send(self, method: str, url: str, **kw) -> httpx.Response:
        """Raw call: the caller inspects the response instead of getting an ApiError."""
        if "?" in url:  # httpx `params` replaces the URL's query, so fold it in first
            parts = urlsplit(url)
            kw["params"] = {**dict(parse_qsl(parts.query)), **(kw.get("params") or {})}
            url = urlunsplit(parts._replace(query=""))
        if url.startswith((f"{DRIVE}/", DRIVE_UPLOAD)):  # shared drives are opt-in per call
            kw["params"] = {"supportsAllDrives": "true", **(kw.get("params") or {})}
        return self.http.request(method.upper(), url, **kw)

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        response = self.send(method, url, **kw)
        if not response.is_success:
            detail = response.text
            try:  # Google wraps the useful line in {"error":{"message":…}}
                detail = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            raise ApiError(response.status_code, method.upper(), url, detail)
        return response

    def api(self, method: str, url: str, **kw) -> Any:
        response = self.request(method, url, **kw)
        return response.json() if response.content else {}

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class Workspace:
    """Account-bound entry point: `with Workspace(load_config(path)) as ws: ws.gmail…`."""

    def __init__(self, config: WorkspaceConfig) -> None:
        self.config = config
        self._credentials = None
        self._session: Session | None = None
        self._services: dict[str, Any] = {}

    @property
    def credentials(self):
        if self._credentials is None:
            self._credentials = credentials(self.config)
        return self._credentials

    @property
    def token(self) -> str:
        return self.credentials.token

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Session(self.token)
        return self._session

    def api(self, method: str, url: str, **kw) -> Any:
        return self.session.api(method, url, **kw)

    def whoami(self) -> dict:
        creds = self.credentials
        identity = self.api("GET", USERINFO) if self.config.wants_openid else {}
        email = str(identity.get("email") or self.config.account).lower()
        # Env-var credentials carry no scope list; ask Google what the token actually grants.
        scopes = sorted(scope.rstrip("/").rsplit("/", 1)[-1] for scope in granted_scopes(creds.token))
        return {"email": email, "token_expiry": str(creds.expiry), "scopes": scopes}

    def _service(self, name: str):
        if name not in self._services:
            from . import docs, drive, gmail, sheets, slides

            if name == "gmail":
                self._services[name] = gmail.GmailClient(self.session, sender=self.config.account)
            else:
                factory = {"drive": drive.DriveClient, "docs": docs.DocsClient,
                           "sheets": sheets.SheetsClient, "slides": slides.SlidesClient}[name]
                self._services[name] = factory(self.session)
        return self._services[name]

    @property
    def drive(self):
        return self._service("drive")

    @property
    def docs(self):
        return self._service("docs")

    @property
    def sheets(self):
        return self._service("sheets")

    @property
    def slides(self):
        return self._service("slides")

    @property
    def gmail(self):
        return self._service("gmail")

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self) -> "Workspace":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
