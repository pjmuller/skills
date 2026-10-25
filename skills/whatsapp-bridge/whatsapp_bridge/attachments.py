"""Local attachment validation; never fetch URLs or log file contents."""
from io import BytesIO
import mimetypes
import os
from pathlib import Path
import re
import stat

# Conservative bridge limits, not claims about WhatsApp's maximums.
DOCUMENT_LIMIT = 100 * 1024 * 1024
IMAGE_LIMIT = 16 * 1024 * 1024


def attachment(path, kind, caption="", filename=None, mimetype=None, *, read=False):
    if kind not in {"document", "image"}:
        raise ValueError("unsupported attachment kind")
    if not isinstance(caption, str) or len(caption) > 1024:
        raise ValueError("caption must be text, at most 1024 characters")
    if not isinstance(path, (str, Path)) or not str(path) or "://" in str(path):
        raise ValueError("attachment must be a local file")
    path = Path(path).expanduser().absolute()
    name = path.name if filename is None else filename
    if (not isinstance(name, str) or not name.strip() or name in {".", ".."}
            or len(name.encode()) > 255 or any(c in name for c in '/\\')
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError("filename must be a plain basename without control characters")
    if mimetype is not None and (not isinstance(mimetype, str) or not re.fullmatch(
            r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", mimetype)):
        raise ValueError("mimetype must be a MIME type without parameters")
    limit = IMAGE_LIMIT if kind == "image" else DOCUMENT_LIMIT
    try:
        # Nonblocking open avoids hanging on FIFOs; fstat validates the opened file.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                raise ValueError(f"attachment must be a nonempty regular file, at most {limit // (1024 * 1024)} MiB")
            data = stream.read(limit + 1) if read else None
    except OSError:
        raise ValueError("attachment is missing or unreadable") from None
    if read and (not data or len(data) > limit):
        raise ValueError("attachment changed size or exceeds the size limit")
    mime = mimetype or {".md": "text/markdown", ".txt": "text/plain"}.get(Path(name).suffix.lower())
    mime = mime or mimetypes.guess_type(name)[0] or "application/octet-stream"
    if read and kind == "image":
        from PIL import Image
        try:
            with Image.open(BytesIO(data)) as img:
                if img.format not in {"JPEG", "MPO", "PNG"}:
                    raise ValueError("unsupported image format")
                mime = "image/jpeg" if img.format == "MPO" else Image.MIME[img.format]
                img.verify()
        except Exception:
            raise ValueError("image must be a valid JPEG or PNG; send other formats as documents") from None
    return {"path": str(path), "filename": name, "mimetype": mime, "caption": caption}, data
