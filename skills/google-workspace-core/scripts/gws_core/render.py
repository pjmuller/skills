"""Compact human output. Every command also emits raw API JSON with --json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def out(data: Any, as_json: bool, human: str | None = None) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False) if as_json or human is None else human)


def trunc(text: str, limit: int) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def table(rows: list[list[Any]]) -> str:
    widths = [
        max((len(str(row[i])) for row in rows if i < len(row)), default=0)
        for i in range(max((len(row) for row in rows), default=0))
    ]
    return "\n".join(
        "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in rows
    )


def write_out(path: str | Path, content: bytes | str) -> str:
    target = Path(path).expanduser()
    if isinstance(content, str):
        target.write_text(content, encoding="utf-8")
    else:
        target.write_bytes(content)
    unit = "chars" if isinstance(content, str) else "bytes"
    return f"{target.resolve()} ({len(content)} {unit})"
