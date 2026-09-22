"""Slide references: a pasted Slides URL, a 1-based slide number or a raw objectId."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from .errors import WorkspaceError
from .inputs import extract_id


def _slide_from(source: str) -> str | None:
    """`slide=id.gX` / `slide=p3` out of a query string or fragment; a bare `id.gX` too."""
    if not source:
        return None
    value = parse_qs(source).get("slide", [None])[0]
    if value is None and "=" not in source:
        value = source  # `#id.p3`, seen on some copied links
    if not value:
        return None
    return value[3:] if value.startswith("id.") else value


def parse_slides_url(value: str) -> tuple[str | None, str | None]:
    """(presentationId, slideRef) from a Google URL; (None, None) for a bare id or number."""
    candidate = str(value).strip()
    if "/" not in candidate:
        return None, None
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    try:
        presentation = extract_id(candidate)
    except WorkspaceError:
        presentation = None
    return presentation, _slide_from(parsed.query) or _slide_from(parsed.fragment)


def resolve_slide(presentation: dict, ref: str) -> tuple[int, str]:
    """(1-based index, objectId). An all-digit ref is a slide number, anything else an objectId."""
    slides = presentation.get("slides", [])
    token = (parse_slides_url(ref)[1] or str(ref)).strip()
    if not token:
        raise WorkspaceError("empty slide reference; pass a slide number, an objectId or a Slides URL")
    if token.isdigit():
        index = int(token)
        if not 1 <= index <= len(slides):
            raise WorkspaceError(f"slide {index} out of range: this deck has {len(slides)} slides")
        return index, slides[index - 1]["objectId"]
    for index, slide in enumerate(slides, 1):
        if slide["objectId"] == token:
            return index, token
    raise WorkspaceError(f"no slide {token!r} in this deck ({len(slides)} slides); "
                         f"run slides-outline to list the objectIds")


def slide_url(presentation_id: str, object_id: str) -> str:
    return (f"https://docs.google.com/presentation/d/{presentation_id}"
            f"/edit#slide=id.{object_id}")
