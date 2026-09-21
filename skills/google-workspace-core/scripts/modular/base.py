"""Shared authenticated httpx client for the Workspace clients."""

from __future__ import annotations

import httpx

from auth import get_credentials


class BaseClient:
    """Holds a bearer-token httpx client; used as a context manager."""

    def __init__(self) -> None:
        self._token = get_credentials().token
        self._http: httpx.Client | None = None

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                timeout=30.0, headers={"Authorization": f"Bearer {self._token}"}
            )
        return self._http

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self._http:
            self._http.close()
