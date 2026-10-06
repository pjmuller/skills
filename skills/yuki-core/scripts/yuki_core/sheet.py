"""Append-only push of quarter rows into a `<YYYY>-Q<n>` tab through the google-workspace-core CLI.

Colleagues own the manual columns and every existing row: a re-run appends only unseen
`item_id`s and never rewrites a cell. A row vanishing from Yuki never means Done in the sheet.
"""

from __future__ import annotations

import json
import re
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from .outstanding import COLUMNS, NUMERIC

Gws = Callable[..., dict]
TAB = re.compile(r"^(\d{4})\s*-\s*Q([1-4])$")  # also matches legacy names like "2026 - Q1"


def gws_runner(script: Path, config: Path) -> Gws:
    def run(*args: str) -> dict:
        cmd = ["uv", "run", "--quiet", "--script", str(script), "--config", str(config), *args, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"gws {args[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
        return json.loads(result.stdout)
    return run


def push(gws: Gws, spreadsheet_id: str, manual: list[str], quarter: str, rows: list[dict],
         dry_run: bool = False) -> dict:
    header = manual + COLUMNS
    tabs = {t["properties"]["title"]: t["properties"]["sheetId"]
            for t in gws("sheet-meta", spreadsheet_id).get("sheets", [])}
    existing = _values(gws, spreadsheet_id, quarter) if quarter in tabs else []
    if existing and existing[0] != header:
        raise ValueError(f"tab {quarter} header differs from the expected one; fix the sheet or the "
                         f"wrapper's manual_columns.\n  sheet:    {existing[0]}\n  expected: {header}")
    seen = {r[header.index("item_id")] for r in existing[1:] if len(r) > header.index("item_id")}
    new = [r for r in rows if r["item_id"] not in seen]
    seeds = _prior_manual_cells(gws, spreadsheet_id, quarter, tabs, manual, new) if new else {}
    summary = {"tab": quarter, "existing": len(seen), "appended": len(new), "seeded": len(seeds),
               "carryover": sum(1 for r in new if r["carryover"]), "created": quarter not in tabs}
    if dry_run or not new:
        summary["rows"] = [[r["date"], str(r["amount"]), r["description_clean"],
                            "seeded" if r["item_id"] in seeds else ""] for r in new]
        return summary

    if quarter not in tabs:
        reply = gws("sheet-add-tab", spreadsheet_id, quarter)
        tabs[quarter] = reply["replies"][0]["addSheet"]["properties"]["sheetId"]
    body = [_cells(seeds.get(r["item_id"], [""] * len(manual))) + _cells([r[c] for c in COLUMNS], COLUMNS)
            for r in new]
    if not existing:
        body.insert(0, header)
    start = len(existing) + 1 if existing else 1
    gws("sheet-write", spreadsheet_id, f"'{quarter}'!A{start}", "--raw", "--values", json.dumps(body))
    if summary["created"]:
        gws("sheet-freeze-rows", spreadsheet_id, str(tabs[quarter]), "--rows", "1")

    after = _values(gws, spreadsheet_id, quarter)
    ids = [r[header.index("item_id")] for r in after[1:] if len(r) > header.index("item_id")]
    missing = [r["item_id"] for r in new if ids.count(r["item_id"]) != 1]
    if after[0] != header or len(ids) != len(seen) + len(new) or missing:
        raise RuntimeError(f"read-back mismatch in tab {quarter}: {len(ids)} ids, missing/duplicate {missing}")
    return summary


def _values(gws: Gws, spreadsheet_id: str, tab: str) -> list[list[str]]:
    return gws("sheet-read", spreadsheet_id, f"'{tab}'").get("values", [])


def _cells(values: list, columns: list[str] | None = None) -> list:
    """RAW write: numbers as numbers, TRUE/FALSE as checkboxes' booleans, everything else text."""
    out = []
    for i, v in enumerate(values):
        if columns and columns[i] in NUMERIC and v != "":
            out.append(float(v))
        elif not columns and v in ("TRUE", "FALSE"):
            out.append(v == "TRUE")
        else:
            out.append("" if v is None else str(v))
    return out


def _prior_manual_cells(gws: Gws, spreadsheet_id: str, quarter: str, tabs: dict, manual: list[str],
                        rows: list[dict]) -> dict[str, list[str]]:
    """Copy manual cells from the newest earlier quarter tab for rows found there uniquely:
    by item_id when that tab has one, else by (date, original_amount, description_raw).
    Ambiguous or missing matches stay blank."""
    current = TAB.match(quarter)
    earlier = sorted((m[1], m[2], t) for t in tabs if (m := TAB.match(t)) and (m[1], m[2]) < (current[1], current[2]))
    if not earlier:
        return {}
    values = _values(gws, spreadsheet_id, earlier[-1][2])
    if not values:
        return {}
    head = values[0]
    col = {name: i for i, name in enumerate(head)}
    shared = [name for name in manual if name in col]
    if not shared:
        return {}

    def cell(row: list[str], name: str) -> str:
        i = col.get(name)
        return row[i].strip() if i is not None and i < len(row) else ""

    by_id = "item_id" in col

    def sheet_key(row: list[str]) -> tuple:
        if by_id:
            return (cell(row, "item_id"),)
        return (cell(row, "date"), _number(cell(row, "original_amount")), cell(row, "description_raw"))

    def yuki_key(r: dict) -> tuple:
        return (r["item_id"],) if by_id else (r["date"], r["original_amount"], r["description_raw"])

    index: dict[tuple, list[list[str]]] = {}
    for row in values[1:]:
        index.setdefault(sheet_key(row), []).append(row)
    seeds = {}
    for r in rows:
        matches = index.get(yuki_key(r), [])
        if len(matches) == 1:
            cells = [cell(matches[0], name) if name in shared else "" for name in manual]
            if any(cells):
                seeds[r["item_id"]] = cells
    return seeds


def _number(text: str) -> Decimal | str:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return text
