"""Append-only push of quarter rows into a `<YYYY>-Q<n>` tab through the google-workspace-core CLI.

Colleagues own the manual columns and every existing row: a re-run appends only unseen
`item_id`s and never rewrites a cell. A row vanishing from Yuki never means Done in the sheet.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from decimal import Decimal, InvalidOperation
from collections import Counter
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from .outstanding import COLUMNS, NUMERIC

Gws = Callable[..., dict]
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
TAB = re.compile(r"^(\d{4})\s*-\s*Q([1-4])$")  # also matches legacy names like "2026 - Q1"


def gws_runner(script: Path, config: Path) -> Gws:
    def run(*args: str) -> dict:
        cmd = ["uv", "run", "--quiet", "--script", str(script), "--config", str(config), *args, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"gws {args[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
        return json.loads(result.stdout)
    return run


WIDTHS = {"Resp": 188, "contact": 145, "description_clean": 485}  # px; other columns keep the default
LOOKUP_WIDTH = 250
DOT_DECIMAL = {"en", "ja", "zh", "ko", "th", "he"}  # locales whose formulas separate arguments with ","
SORT = [("description_clean", "ASCENDING"), ("date", "DESCENDING")]


def columns(formulas: list[dict], manual: list[str], lookups: list[dict]) -> tuple[list[str], list[str]]:
    """(header, data columns): formula columns, manual columns, then data with lookups after description_clean."""
    cut = COLUMNS.index("description_clean") + 1
    data = COLUMNS[:cut] + [lk["name"] for lk in lookups] + COLUMNS[cut:]
    return [f["name"] for f in formulas] + manual + data, data


def push(gws: Gws, spreadsheet_id: str, manual: list[str], quarter: str, rows: list[dict],
         dry_run: bool = False, formulas: list[dict] | None = None, tab: str | None = None,
         lookups: list[dict] | None = None) -> dict:
    """`formulas` = wrapper `formula_columns` ([{name, rules: [{label, pattern}]}]), placed first;
    `lookups` = wrapper `lookup_columns` ([{name, tab}]): the note of the first row in a human-kept tab
    (columns match, name, Owner; created if missing) whose `match` regex hits contact + description_clean; `tab` overrides the target tab name (test pushes);
    seeding still follows `quarter`."""
    formulas, lookups, tab = formulas or [], lookups or [], tab or quarter
    header, data = columns(formulas, manual, lookups)
    meta = gws("api", "GET", f"{SHEETS}/{spreadsheet_id}",
                 "--param", "fields=properties.locale,sheets(properties(title,sheetId),basicFilter)")
    sheets, locale = meta.get("sheets", []), meta.get("properties", {}).get("locale", "en_US")
    tabs = {t["properties"]["title"]: t["properties"]["sheetId"] for t in sheets}
    existing = _values(gws, spreadsheet_id, tab) if tab in tabs else []
    if existing and existing[0] != header:
        raise ValueError(f"tab {tab} header differs from the expected one; fix the sheet or the wrapper's "
                         f"formula_columns/manual_columns/lookup_columns.\n  sheet:    {existing[0]}\n  expected: {header}")
    id_col = header.index("item_id")
    seen = {r[id_col] for r in existing[1:] if len(r) > id_col}
    new = [r for r in rows if r["item_id"] not in seen]
    seeds = _prior_manual_cells(gws, spreadsheet_id, quarter, tabs, manual, rows, new) if new else {}
    summary = {"tab": tab, "existing": len(seen), "appended": len(new), "seeded": len(seeds),
               "created": tab not in tabs}
    if dry_run or not new:
        summary["rows"] = [[r["date"], str(r["amount"]), r["description_clean"],
                            "seeded" if r["item_id"] in seeds else ""] for r in new]
        return summary

    batch = []
    for lk in lookups:  # the notes tab people maintain, once per vendor
        if lk["tab"] not in tabs:
            reply = gws("sheet-add-tab", spreadsheet_id, lk["tab"])
            tabs[lk["tab"]] = reply["replies"][0]["addSheet"]["properties"]["sheetId"]
            gws("sheet-write", spreadsheet_id, f"{_quoted(lk['tab'])}!A1", "--raw",
                "--values", json.dumps([["match", lk["name"], "Owner"]]))
            batch.append(_freeze(tabs[lk["tab"]]))
    if summary["created"]:
        reply = gws("sheet-add-tab", spreadsheet_id, tab)
        tabs[tab] = reply["replies"][0]["addSheet"]["properties"]["sheetId"]
    first = len(existing) + 1 if existing else 2  # first new data row (1-based)
    body = [[""] * len(formulas) + _cells(seeds.get(r["item_id"], [""] * len(manual)))
            + _cells([r.get(c, "") for c in data], data) for r in new]
    if not existing:
        body.insert(0, header)
    gws("sheet-write", spreadsheet_id, f"{_quoted(tab)}!A{first - (not existing)}", "--raw", "--values", json.dumps(body))
    # Formula/lookup cells USER_ENTERED, in the sheet locale's argument separator; data stays RAW/typed.
    sep = "," if locale.split("_")[0] in DOT_DECIMAL else ";"
    blocks = [(0, lambda n: [_formula(f, header, n, sep) for f in formulas]) if formulas else None,
              (header.index(lookups[0]["name"]), lambda n: [_lookup(lk, header, n, sep) for lk in lookups]) if lookups else None]
    for start, make in filter(None, blocks):
        gws("sheet-write", spreadsheet_id, f"{_quoted(tab)}!{_letter(start)}{first}",
            "--values", json.dumps([make(n) for n in range(first, first + len(new))]))
    last = first + len(new) - 1
    if summary["created"]:
        requests = batch + _layout(tabs[tab], header, last, [lk["name"] for lk in lookups])
    else:  # grow an existing basic filter over the appended rows, keeping its sort/filter specs
        old = next((t.get("basicFilter") for t in sheets if t["properties"]["title"] == tab), None)
        requests = [{"setBasicFilter": {"filter": {**{k: v for k, v in old.items() if k != "criteria"},
                                                   "range": {**old["range"], "endRowIndex": max(last, old["range"]["endRowIndex"])}}}}] \
            if old and "endRowIndex" in old["range"] else []
        requests = batch + requests
    if requests:
        with tempfile.NamedTemporaryFile("w", suffix=".json") as body_file:
            json.dump({"requests": requests}, body_file)
            body_file.flush()
            gws("sheet-batch", spreadsheet_id, "--body", body_file.name)

    after = _values(gws, spreadsheet_id, tab)
    ids = [r[id_col] for r in after[1:] if len(r) > id_col]
    missing = [r["item_id"] for r in new if ids.count(r["item_id"]) != 1]
    if after[0] != header or len(ids) != len(seen) + len(new) or missing:
        raise RuntimeError(f"read-back mismatch in tab {tab}: {len(ids)} ids, missing/duplicate {missing}")
    added = {r["item_id"] for r in new}
    broken = [r[id_col] for r in after[1:] if len(r) > id_col and r[id_col] in added
              and any(str(r[header.index(name)]).startswith("#") for name in
                      [f["name"] for f in formulas] + [lk["name"] for lk in lookups] if header.index(name) < len(r))]
    if broken:
        raise RuntimeError(f"formula errors in tab {tab} (locale {locale}?) for item ids {broken}")
    return summary


def _formula(column: dict, header: list[str], row: int, sep: str = ",") -> str:
    """=IFS(REGEXMATCH(contact&" "&description_clean, pattern), label, ..., TRUE, ""); `sep` is the
    locale's argument separator (";" where the decimal mark is a comma, e.g. nl_NL)."""
    text = f'{_letter(header.index("contact"))}{row}&" "&{_letter(header.index("description_clean"))}{row}'
    quote_ = lambda s: '"' + s.replace('"', '""') + '"'
    parts = [f"REGEXMATCH({text}{sep}{quote_(r['pattern'])}){sep}{quote_(r['label'])}" for r in column["rules"]]
    return f'=IFS({sep.join(parts)}{sep}TRUE{sep}"")'


def _lookup(column: dict, header: list[str], row: int, sep: str = ",") -> str:
    """Note of the first notes-tab row whose `match` (case-insensitive regex) hits contact + description_clean.
    Not a contact VLOOKUP: Yuki books e.g. Google Ads under the "Linkedin Ireland" contact."""
    notes = _quoted(column["tab"])
    text = f'{_letter(header.index("contact"))}{row}&" "&{_letter(header.index("description_clean"))}{row}'
    hits = f'ARRAYFORMULA(({notes}!A2:A<>"")*REGEXMATCH({text}{sep}"(?i)"&{notes}!A2:A))'
    return f'=IFERROR(INDEX({notes}!B2:B{sep}MATCH(1{sep}{hits}{sep}0)){sep}"")'


def _freeze(sheet_id: int) -> dict:
    return {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                                      "fields": "gridProperties.frozenRowCount"}}


def _letter(index: int) -> str:
    out, index = "", index + 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _layout(sheet_id: int, header: list[str], last_row: int, lookups: list[str] = ()) -> list[dict]:
    """New tab: frozen header, EUR amounts as 0.00, fixed widths, basic filter sorted for triage."""
    requests = [_freeze(sheet_id)]
    for name in ("amount", "original_amount"):
        i = header.index(name)
        requests.append({"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": i, "endColumnIndex": i + 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}}},
            "fields": "userEnteredFormat.numberFormat"}})
    for name, px in [*WIDTHS.items(), *((n, LOOKUP_WIDTH) for n in lookups)]:
        if name in header:
            i = header.index(name)
            requests.append({"updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    requests.append({"setBasicFilter": {"filter": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": last_row,
                  "startColumnIndex": 0, "endColumnIndex": len(header)},
        "sortSpecs": [{"dimensionIndex": header.index(n), "sortOrder": o} for n, o in SORT]}}})
    return requests


def _values(gws: Gws, spreadsheet_id: str, tab: str) -> list[list[str]]:
    return gws("sheet-read", spreadsheet_id, _quoted(tab)).get("values", [])


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
                        rows: list[dict], new: list[dict]) -> dict[str, list[str]]:
    """Copy manual cells from the newest earlier quarter tab when exactly one row there matches
    exactly one of this quarter's Yuki rows: by item_id when that tab has one, else by
    (date, original_amount, description_raw). Ambiguous or missing matches stay blank."""
    current = TAB.match(quarter)
    earlier = sorted((m[1], m[2], t) for t in tabs if (m := TAB.match(t)) and (m[1], m[2]) < (current[1], current[2]))
    if not earlier:
        return {}
    tab = earlier[-1][2]
    shown = _values(gws, spreadsheet_id, tab)  # manual cells as people see them
    # Keys from unformatted values: displayed amounts follow the sheet locale ("-10,00" in nl_BE).
    raw = gws("api", "GET", f"{SHEETS}/{spreadsheet_id}/values/"
              f"{quote(_quoted(tab), safe='')}", "--param", "valueRenderOption=UNFORMATTED_VALUE",
              "--param", "dateTimeRenderOption=FORMATTED_STRING").get("values", [])
    if not shown:
        return {}
    if len(raw) != len(shown) or raw[0] != shown[0]:
        raise RuntimeError(f"tab {tab} changed between reads; rerun")
    col = {name: i for i, name in enumerate(shown[0])}
    shared = [name for name in manual if name in col]
    if not shared:
        return {}

    def cell(row: list, name: str):
        i = col.get(name)
        return row[i] if i is not None and i < len(row) else ""

    by_id = "item_id" in col

    def sheet_key(row: list) -> tuple:
        if by_id:
            return (str(cell(row, "item_id")).strip(),)
        return (str(cell(row, "date")).strip(), _number(cell(row, "original_amount")),
                str(cell(row, "description_raw")).strip())

    def yuki_key(r: dict) -> tuple:
        return (r["item_id"],) if by_id else (r["date"], r["original_amount"], r["description_raw"])

    index: dict[tuple, list[int]] = {}
    for n, row in enumerate(raw[1:], start=1):
        index.setdefault(sheet_key(row), []).append(n)
    current_count = Counter(yuki_key(r) for r in rows)  # all of this quarter's rows, not only new ones
    seeds = {}
    for r in new:
        matches = index.get(yuki_key(r), [])
        if len(matches) == 1 and current_count[yuki_key(r)] == 1:
            cells = [str(cell(shown[matches[0]], name)).strip() if name in shared else "" for name in manual]
            if any(cells):
                seeds[r["item_id"]] = cells
    return seeds


def _quoted(tab: str) -> str:
    return "'" + tab.replace("'", "''") + "'"


def _number(value) -> Decimal | str:
    """Unformatted cell -> Decimal; text that is not a plain number never matches (no separator guessing)."""
    if isinstance(value, bool):
        return str(value)
    try:
        return Decimal(str(value).strip()) if isinstance(value, (int, float, str)) else str(value)
    except InvalidOperation:
        return str(value)
