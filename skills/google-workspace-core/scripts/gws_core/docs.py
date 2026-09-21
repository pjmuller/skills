"""Google Docs: Markdown export, structural outline and text edits."""

from __future__ import annotations

from .errors import WorkspaceError
from .inputs import extract_id
from .session import DOCS, Session


class DocsClient:
    def __init__(self, session: Session) -> None:
        self.session = session

    def outline(self, doc: str) -> dict:
        return self.session.api("GET", f"{DOCS}/{extract_id(doc)}",
                                params={"fields": "title,body.content,revisionId"})

    def replace_text(self, doc: str, find: str, replace: str, *, match_case: bool = False) -> dict:
        request = {"replaceAllText": {
            "containsText": {"text": find, "matchCase": bool(match_case)}, "replaceText": replace}}
        return self.batch(doc, {"requests": [request]})

    def insert_text(self, doc: str, text: str, *, index: int | None = None, end: bool = False) -> dict:
        if end:
            request = {"insertText": {"endOfSegmentLocation": {}, "text": text}}
        elif index is not None:
            request = {"insertText": {"location": {"index": index}, "text": text}}
        else:
            raise WorkspaceError("pass --index N or --end")
        return self.batch(doc, {"requests": [request]})

    def batch(self, doc: str, body: dict) -> dict:
        return self.session.api("POST", f"{DOCS}/{extract_id(doc)}:batchUpdate", json=body)
