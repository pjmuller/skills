"""Google Slides: outline, text, structure edits, images and rendering."""

from __future__ import annotations

import uuid
from typing import Any

from .errors import WorkspaceError
from .inputs import extract_id
from .session import DRIVE, SLIDES, Session

EMU_PER_PT = 12700
TITLE_TYPES = ("TITLE", "CENTERED_TITLE")
BODY_TYPES = ("BODY", "SUBTITLE")
ELEMENT_KINDS = ("shape", "table", "image", "video", "line", "elementGroup", "sheetsChart", "wordArt")
# Compact mask: enough for one line per slide, cheap on a 163-slide deck.
OUTLINE_FIELDS = (
    "presentationId,title,"
    "layouts(objectId,layoutProperties.displayName),"
    "slides(objectId,slideProperties.layoutObjectId,"
    "slideProperties.notesPage(pageElements(shape(text(textElements(textRun(content)))))),"
    "pageElements(objectId,shape(shapeType,placeholder,text(textElements(textRun(content)))),"
    "table(rows,columns),image(contentUrl),elementGroup(children(objectId,"
    "shape(text(textElements(textRun(content))))))))"
)
LAYOUT_FIELDS = (
    "layouts(objectId,layoutProperties.displayName,layoutProperties.name,"
    "pageElements(objectId,shape(placeholder)))"
)


def element_text(element: dict) -> str:
    """All text in a page element, recursing into groups and table cells."""
    parts: list[str] = []

    def text_of(container: dict) -> None:
        for item in (container.get("text") or {}).get("textElements", []):
            run = item.get("textRun") or item.get("autoText")
            if run:
                parts.append(run.get("content", ""))

    def walk(node: dict) -> None:
        if "shape" in node:
            text_of(node["shape"])
        for row in (node.get("table") or {}).get("tableRows", []):
            for cell in row.get("tableCells", []):
                text_of(cell)
                parts.append("\t")
        for child in (node.get("elementGroup") or {}).get("children", []):
            walk(child)

    walk(element)
    return "".join(parts)


def element_paragraphs(element: dict) -> list[tuple[int, str]]:
    """(nesting level, text) per paragraph of a shape or group; tables flatten like element_text."""
    if "shape" not in element and "elementGroup" not in element:
        return [(0, line) for line in element_text(element).replace("\v", "\n").split("\n")]
    paragraphs: list[tuple[int, str]] = []

    def walk(node: dict) -> None:
        for item in ((node.get("shape") or {}).get("text") or {}).get("textElements", []):
            if "paragraphMarker" in item:
                level = ((item["paragraphMarker"].get("bullet") or {}).get("nestingLevel", 0))
                paragraphs.append((level, ""))
            run = item.get("textRun") or item.get("autoText")
            if run:
                if not paragraphs:
                    paragraphs.append((0, ""))
                level, text = paragraphs[-1]
                paragraphs[-1] = (level, text + run.get("content", ""))
        for child in (node.get("elementGroup") or {}).get("children", []):
            walk(child)

    walk(element)
    return [(level, text.replace("\v", "\n").rstrip("\n")) for level, text in paragraphs]


def element_geometry(element: dict) -> str:
    """`WxH pt at (x, y)` from size + transform, the way slides-image takes them."""
    size, transform = element.get("size") or {}, element.get("transform") or {}
    if not size:
        return "no size"
    scale_x, scale_y = transform.get("scaleX", 1), transform.get("scaleY", 1)
    width = size.get("width", {}).get("magnitude", 0) * scale_x / EMU_PER_PT
    height = size.get("height", {}).get("magnitude", 0) * scale_y / EMU_PER_PT
    x, y = transform.get("translateX", 0) / EMU_PER_PT, transform.get("translateY", 0) / EMU_PER_PT
    return f"{width:.0f}x{height:.0f} pt at ({x:.0f}, {y:.0f})"


def element_kind(element: dict) -> str:
    kind = next((key for key in ELEMENT_KINDS if key in element), "unknown")
    if kind == "elementGroup":
        return "group"
    if kind == "shape":
        return f"shape/{element['shape'].get('shapeType', '?')}".lower()
    return kind


def placeholder_type(element: dict) -> str:
    return ((element.get("shape") or {}).get("placeholder") or {}).get("type", "")


def notes_text(page: dict) -> str:
    notes = (page.get("slideProperties") or {}).get("notesPage") or {}
    return "".join(element_text(element) for element in notes.get("pageElements", [])).strip()


def slide_title(slide: dict) -> str:
    """First TITLE/CENTERED_TITLE placeholder, else the first non-empty text."""
    texts = []
    for element in slide.get("pageElements", []):
        text = element_text(element).strip()
        if not text or placeholder_type(element) == "SLIDE_NUMBER":
            continue
        if placeholder_type(element) in TITLE_TYPES:
            return text
        texts.append(text)
    return texts[0] if texts else ""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class SlidesClient:
    def __init__(self, session: Session) -> None:
        self.session = session

    def presentation(self, deck: str, fields: str | None = None) -> dict:
        return self.session.api("GET", f"{SLIDES}/{extract_id(deck)}",
                                params={"fields": fields} if fields else {})

    def page(self, deck: str, page_id: str, fields: str | None = None) -> dict:
        return self.session.api("GET", f"{SLIDES}/{extract_id(deck)}/pages/{page_id}",
                                params={"fields": fields} if fields else {})

    def batch(self, deck: str, body: dict) -> dict:
        return self.session.api("POST", f"{SLIDES}/{extract_id(deck)}:batchUpdate", json=body)

    @staticmethod
    def resolve(deck_data: dict, ref: str) -> tuple[int, dict]:
        """`ref` is a 1-based slide number or a slide objectId."""
        slides = deck_data.get("slides", [])
        if str(ref).isdigit():
            index = int(ref)
            if not 1 <= index <= len(slides):
                raise WorkspaceError(f"slide {index} out of range (deck has {len(slides)})")
            return index, slides[index - 1]
        for index, slide in enumerate(slides, 1):
            if slide["objectId"] == ref:
                return index, slide
        raise WorkspaceError(f"no slide {ref!r} in this presentation")

    def outline(self, deck: str) -> dict:
        return self.presentation(deck, OUTLINE_FIELDS)

    def replace_text(self, deck: str, find: str, replace: str, *, slides: str | None = None,
                     match_case: bool = False) -> dict:
        request: dict[str, Any] = {"replaceAllText": {
            "containsText": {"text": find, "matchCase": bool(match_case)}, "replaceText": replace}}
        if slides:
            request["replaceAllText"]["pageObjectIds"] = [
                item.strip() for item in slides.split(",") if item.strip()]
        return self.batch(deck, {"requests": [request]})

    def set_text(self, deck: str, element_id: str, text: str) -> dict:
        # deleteText(ALL) + insertText: the new run inherits the shape/placeholder defaults, so
        # run-level styling set on the old text is lost (placeholder-level styling survives).
        requests: list[dict] = [{"deleteText": {"objectId": element_id, "textRange": {"type": "ALL"}}}]
        if text:
            requests.append({"insertText": {"objectId": element_id, "insertionIndex": 0, "text": text}})
        return self.batch(deck, {"requests": requests})

    # --- structure ----------------------------------------------------------

    @staticmethod
    def find_layout(deck_data: dict, name: str) -> dict:
        """Match by display name ("Title and body"), API name (TITLE_AND_BODY) or objectId."""
        wanted = str(name).strip().lower()
        for layout in deck_data.get("layouts", []):
            properties = layout.get("layoutProperties", {})
            if wanted in (layout["objectId"].lower(), properties.get("displayName", "").lower(),
                          properties.get("name", "").lower()):
                return layout
        names = ", ".join(layout.get("layoutProperties", {}).get("displayName", "?")
                          for layout in deck_data.get("layouts", []))
        raise WorkspaceError(f"no layout {name!r}; this deck has: {names}")

    @staticmethod
    def layout_placeholder(layout: dict, types: tuple[str, ...]) -> dict | None:
        for element in layout.get("pageElements", []):
            placeholder = ((element.get("shape") or {}).get("placeholder") or {})
            if placeholder.get("type") in types:
                return {"type": placeholder["type"], "index": placeholder.get("index", 0)}
        return None

    def run_colors(self, deck: str, slide_id: str) -> dict[str, dict]:
        """Foreground colour of the first TITLE/BODY run: fresh placeholders do not inherit it."""
        page = self.page(deck, slide_id,
                         "pageElements(shape(placeholder,text(textElements(textRun(style)))))")
        colors: dict[str, dict] = {}
        for element in page.get("pageElements", []):
            kind = placeholder_type(element)
            key = "title" if kind in TITLE_TYPES else "body" if kind in BODY_TYPES else None
            if not key or key in colors:
                continue
            for item in (element["shape"].get("text") or {}).get("textElements", []):
                color = ((item.get("textRun") or {}).get("style") or {}).get("foregroundColor")
                if color:
                    colors[key] = color
                    break
        return colors

    def slide_requests(self, layout: dict, spec: dict, insertion_index: int,
                       colors: dict | None = None) -> tuple[str, list[dict]]:
        """createSlide + fill TITLE/BODY. Body lines become bullets; leading tabs nest them."""
        slide_id = new_id("s")
        mappings: list[dict] = []
        requests: list[dict] = []
        title, body = spec.get("title"), spec.get("body")
        title_placeholder = self.layout_placeholder(layout, TITLE_TYPES) if title else None
        # drop_body: instantiate the layout's body placeholder only to delete it, keeping the
        # layout's title position/logo while leaving a clean canvas for hand-placed shapes.
        drop_body = bool(spec.get("drop_body")) and not body
        body_placeholder = self.layout_placeholder(layout, BODY_TYPES) if (body or drop_body) else None
        display = layout["layoutProperties"].get("displayName")
        if title and not title_placeholder:
            raise WorkspaceError(f"layout {display!r} has no title placeholder")
        if body and not body_placeholder:
            raise WorkspaceError(f"layout {display!r} has no body placeholder")
        title_id = body_id = None
        if title_placeholder:
            title_id = new_id("t")
            mappings.append({"layoutPlaceholder": title_placeholder, "objectId": title_id})
        if body_placeholder:
            body_id = new_id("b")
            mappings.append({"layoutPlaceholder": body_placeholder, "objectId": body_id})
        requests.append({"createSlide": {
            "objectId": slide_id, "insertionIndex": insertion_index,
            "slideLayoutReference": {"layoutId": layout["objectId"]},
            "placeholderIdMappings": mappings}})
        colors = colors or {}
        if title_id:
            requests.append({"insertText": {"objectId": title_id, "insertionIndex": 0, "text": title}})
            if colors.get("title"):
                requests.append({"updateTextStyle": {
                    "objectId": title_id, "textRange": {"type": "ALL"},
                    "style": {"foregroundColor": colors["title"]}, "fields": "foregroundColor"}})
        if body_id and drop_body:
            requests.append({"deleteObject": {"objectId": body_id}})
        elif body_id:
            requests.append({"insertText": {"objectId": body_id, "insertionIndex": 0, "text": body}})
            if colors.get("body"):
                requests.append({"updateTextStyle": {
                    "objectId": body_id, "textRange": {"type": "ALL"},
                    "style": {"foregroundColor": colors["body"]}, "fields": "foregroundColor"}})
            if spec.get("bullets", "\n" in body.strip()):
                requests.append({"createParagraphBullets": {
                    "objectId": body_id, "textRange": {"type": "ALL"},
                    "bulletPreset": spec.get("bullet_preset", "BULLET_DISC_CIRCLE_SQUARE")}})
        return slide_id, requests

    def set_notes(self, deck: str, slide_id: str, text: str) -> None:
        page = self.page(deck, slide_id, "slideProperties.notesPage(notesProperties,pageElements)")
        notes = (page.get("slideProperties") or {}).get("notesPage") or {}
        notes_id = (notes.get("notesProperties") or {}).get("speakerNotesObjectId")
        if not notes_id:
            raise WorkspaceError(f"slide {slide_id} has no speaker-notes shape")
        requests = []
        if notes_text(page):
            requests.append({"deleteText": {"objectId": notes_id, "textRange": {"type": "ALL"}}})
        if text:
            requests.append({"insertText": {"objectId": notes_id, "insertionIndex": 0, "text": text}})
        if requests:
            self.batch(deck, {"requests": requests})

    def add_slides(self, deck: str, specs: list[dict], *, after: str | None, default_layout: str,
                   like: str | None) -> list[dict]:
        deck_id = extract_id(deck)
        data = self.presentation(deck_id, "slides(objectId)," + LAYOUT_FIELDS)
        position = len(data.get("slides", [])) if after in (None, "end") else self.resolve(data, after)[0]
        reference = like or (after if after not in (None, "end") else None)
        colors = ({} if not reference or reference == "none"
                  else self.run_colors(deck_id, self.resolve(data, reference)[1]["objectId"]))
        requests: list[dict] = []
        created: list[tuple[str, dict]] = []
        for offset, spec in enumerate(specs):
            layout = self.find_layout(data, spec.get("layout") or default_layout)
            slide_id, slide_reqs = self.slide_requests(layout, spec, position + offset, colors)
            requests.extend(slide_reqs)
            created.append((slide_id, spec))
        self.batch(deck_id, {"requests": requests})
        for slide_id, spec in created:
            if spec.get("notes"):
                self.set_notes(deck_id, slide_id, spec["notes"])
        return [{"objectId": slide_id, "position": position + offset + 1, "title": spec.get("title")}
                for offset, (slide_id, spec) in enumerate(created)]

    def delete_slides(self, deck: str, refs: list[str]) -> list[str]:
        data = self.presentation(deck, "slides(objectId)")
        targets = [self.resolve(data, ref)[1]["objectId"] for ref in refs]
        self.batch(deck, {"requests": [{"deleteObject": {"objectId": item}} for item in targets]})
        return targets

    def move_slides(self, deck: str, refs: list[str], to: int) -> list[str]:
        data = self.presentation(deck, "slides(objectId)")
        ids = [self.resolve(data, ref)[1]["objectId"] for ref in refs]
        # updateSlidesPosition's insertionIndex counts the deck *before* the move, moved slides
        # included. "Become slide N" = exactly N-1 non-moved slides precede the block.
        moved = set(ids)
        insertion, seen = 0, 0
        for index, slide in enumerate(data["slides"], 1):
            if seen == to - 1:
                break
            if slide["objectId"] not in moved:
                seen += 1
                insertion = index
        self.batch(deck, {"requests": [{"updateSlidesPosition": {
            "slideObjectIds": ids, "insertionIndex": insertion}}]})
        return ids

    # --- images and rendering ------------------------------------------------

    def _create_image(self, deck_id: str, request: dict) -> tuple[bool, Any]:
        """createImage without raising, so the caller can retry after opening up access."""
        response = self.session.send(
            "POST", f"{SLIDES}/{deck_id}:batchUpdate", json={"requests": [request]})
        return (True, response.json()) if response.is_success else (False, response.text)

    def scale_image(self, deck_id: str, page_id: str, image_id: str, width: float | None,
                    height: float | None, x: float, y: float) -> None:
        """Uniformly scale a natural-size image to the one given dimension (ratio kept)."""
        page = self.page(deck_id, page_id, "pageElements(objectId,size)")
        natural = next((element.get("size") for element in page.get("pageElements", [])
                        if element["objectId"] == image_id), None)
        if not natural:
            return
        target = (width or height) * EMU_PER_PT
        scale = target / natural["width" if width else "height"]["magnitude"]
        self.batch(deck_id, {"requests": [{"updatePageElementTransform": {
            "objectId": image_id, "applyMode": "ABSOLUTE",
            "transform": {"scaleX": scale, "scaleY": scale, "unit": "EMU",
                          "translateX": x * EMU_PER_PT, "translateY": y * EMU_PER_PT}}}]})

    def insert_image(self, deck: str, slide_ref: str, *, drive, url: str | None = None,
                     file: str | None = None, x: float = 30, y: float = 110,
                     width: float | None = None, height: float | None = None,
                     name: str | None = None, parent: str | None = None) -> dict:
        deck_id = extract_id(deck)
        index, slide = self.resolve(self.presentation(deck_id, "slides(objectId)"), slide_ref)
        file_id = folder = None
        if file:
            # Default: next to the deck. A deck on a shared drive we cannot list has no readable
            # parent, and Drive then silently files the upload in My Drive root: say so.
            target_parent = parent or drive.parent_of(deck_id)
            file_id = drive.upload(file, name, target_parent)["id"]
            folder = (f"folder {extract_id(target_parent)}" if target_parent
                      else "My Drive root (deck folder not readable; pass --parent)")
            url = f"https://drive.google.com/uc?id={file_id}"
        properties: dict[str, Any] = {
            "pageObjectId": slide["objectId"],
            "transform": {"scaleX": 1, "scaleY": 1, "unit": "EMU",
                          "translateX": x * EMU_PER_PT, "translateY": y * EMU_PER_PT}}
        # `size` needs both dimensions (a half-filled one fails as "Unknown dimension unit
        # UNIT_UNSPECIFIED"). With only one we create at natural size and rescale after.
        if width and height:
            properties["size"] = {"width": {"magnitude": width * EMU_PER_PT, "unit": "EMU"},
                                  "height": {"magnitude": height * EMU_PER_PT, "unit": "EMU"}}
        image_id = new_id("img")
        request = {"createImage": {"objectId": image_id, "url": url, "elementProperties": properties}}
        ok, result = self._create_image(deck_id, request)
        if not ok and file_id:
            # Slides fetches the URL itself, without our credentials, so a freshly uploaded
            # private Drive file is invisible to it. Open it for the duration of the call only.
            permission = drive.share_anyone_reader(file_id)
            try:
                ok, result = self._create_image(deck_id, request)
            finally:
                drive.unshare(file_id, permission["id"])
        if not ok:
            raise WorkspaceError(f"Google API error on createImage: {result}")
        if not (width and height):
            self.scale_image(deck_id, slide["objectId"], image_id,
                             width or (None if height else 660), height, x, y)
        return {"objectId": image_id, "slide": index, "driveFileId": file_id, "driveFolder": folder}

    def thumbnail(self, deck: str, slide_ref: str) -> tuple[int, str, bytes]:
        import httpx

        deck_id = extract_id(deck)
        index, slide = self.resolve(self.presentation(deck_id, "slides(objectId)"), slide_ref)
        meta = self.session.api(
            "GET", f"{SLIDES}/{deck_id}/pages/{slide['objectId']}/thumbnail",
            params={"thumbnailProperties.thumbnailSize": "LARGE",
                    "thumbnailProperties.mimeType": "PNG"})
        url = meta.get("contentUrl")
        if not url:
            raise WorkspaceError(f"Slides returned no thumbnail contentUrl for slide {index}")
        response = httpx.get(url, timeout=120)  # pre-signed, no Authorization header
        if not response.is_success:
            raise WorkspaceError(f"thumbnail download failed ({response.status_code})")
        return index, slide["objectId"], response.content

    def export_pdf(self, deck: str) -> bytes:
        return self.session.request("GET", f"{DRIVE}/files/{extract_id(deck)}/export",
                                    params={"mimeType": "application/pdf"}).content
