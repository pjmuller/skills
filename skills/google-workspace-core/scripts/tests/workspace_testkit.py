"""Shared stubs and constants for the Workspace core tests."""

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

ACCOUNT = "team@example.com"
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email",
          "https://www.googleapis.com/auth/drive"]


class Recorded:
    """A response stub plus the call that produced it."""

    def __init__(self, payload=None, *, status=200, content=None, headers=None):
        self._payload = {} if payload is None else payload
        self.status_code = status
        self.headers = headers or {}
        self.content = content if content is not None else json.dumps(self._payload).encode()

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    @property
    def text(self):
        return self.content.decode(errors="replace")

    def json(self):
        return self._payload


class FakeSession:
    """Session stand-in: records every call and replays queued responses."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def _next(self):
        return self.responses.pop(0) if self.responses else Recorded({})

    def send(self, method, url, **kw):
        self.calls.append((method.upper(), url, kw))
        return self._next()

    def request(self, method, url, **kw):
        response = self.send(method, url, **kw)
        if not response.is_success:
            from gws_core.errors import ApiError

            raise ApiError(response.status_code, method.upper(), url, response.text)
        return response

    def api(self, method, url, **kw):
        response = self.request(method, url, **kw)
        return response.json() if response.content else {}

    def close(self):
        pass


class RoutedSession(FakeSession):
    """Route by URL instead of a queue: concurrent fetches arrive in any order."""

    def __init__(self, routes):
        super().__init__()
        self.routes = dict(routes)

    def api(self, method, url, **kw):
        self.calls.append((method.upper(), url, kw))
        for fragment, payload in self.routes.items():
            if fragment in url:
                return payload
        raise AssertionError(f"no route for {url}")
