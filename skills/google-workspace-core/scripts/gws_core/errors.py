"""Errors the CLI turns into `error: …` exits and importers can catch."""

from __future__ import annotations


class WorkspaceError(Exception):
    """Any expected failure: bad config, missing credentials, refused write."""


class ConfigError(WorkspaceError):
    """The wrapper's workspace.json is missing, unreadable or invalid."""


class AuthError(WorkspaceError):
    """No usable offline credentials, wrong account, or refused consent."""


class ApiError(WorkspaceError):
    """Google answered with a non-2xx status."""

    def __init__(self, status: int, method: str, url: str, detail: str) -> None:
        super().__init__(f"Google API {status} on {method} {url}: {detail}")
        self.status = status
        self.method = method
        self.url = url
        self.detail = detail
