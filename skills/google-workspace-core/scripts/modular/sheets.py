"""Google Sheets client for the configured Workspace account — read and write spreadsheets."""

from __future__ import annotations

from base import BaseClient

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsClient(BaseClient):
    """Read and write Google Sheets."""

    def metadata(self, sheet_id: str) -> dict:
        r = self.http.get(f"{SHEETS_API}/{sheet_id}")
        r.raise_for_status()
        data = r.json()
        return {
            "title": data.get("properties", {}).get("title"),
            "tabs": [
                {"name": s["properties"]["title"], "id": s["properties"]["sheetId"]}
                for s in data.get("sheets", [])
            ],
        }

    def add_sheet(self, sheet_id: str, title: str) -> dict:
        """Create a new tab in a spreadsheet via batchUpdate addSheet."""
        r = self.http.post(
            f"{SHEETS_API}/{sheet_id}:batchUpdate",
            json={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        )
        r.raise_for_status()
        return r.json()

    def freeze_rows(
        self, sheet_id: str, tab_sheet_id: int, frozen_row_count: int = 1
    ) -> dict:
        """Freeze the top `frozen_row_count` rows on a tab."""
        r = self.http.post(
            f"{SHEETS_API}/{sheet_id}:batchUpdate",
            json={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": tab_sheet_id,
                                "gridProperties": {"frozenRowCount": frozen_row_count},
                            },
                            "fields": "gridProperties.frozenRowCount",
                        }
                    }
                ]
            },
        )
        r.raise_for_status()
        return r.json()

    def format_default_rows(
        self,
        sheet_id: str,
        tab_sheet_id: int,
        row_count: int,
        col_count: int,
        *,
        pixel_size: int = 21,
    ) -> dict:
        """Clip cell text and reset rows to normal height for dense dumps."""
        r = self.http.post(
            f"{SHEETS_API}/{sheet_id}:batchUpdate",
            json={
                "requests": [
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": tab_sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": row_count,
                                "startColumnIndex": 0,
                                "endColumnIndex": col_count,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "wrapStrategy": "CLIP",
                                }
                            },
                            "fields": "userEnteredFormat.wrapStrategy",
                        }
                    },
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": tab_sheet_id,
                                "dimension": "ROWS",
                                "startIndex": 0,
                                "endIndex": row_count,
                            },
                            "properties": {"pixelSize": pixel_size},
                            "fields": "pixelSize",
                        }
                    },
                ]
            },
        )
        r.raise_for_status()
        return r.json()

    def add_named_range(
        self, sheet_id: str, name: str, tab_sheet_id: int, a1_cell: str
    ) -> dict:
        """Create a single-cell named range. `a1_cell` is plain A1 with no tab prefix (`D4`)."""
        col_letters = "".join(c for c in a1_cell if c.isalpha())
        row_digits = "".join(c for c in a1_cell if c.isdigit())
        if not col_letters or not row_digits:
            raise ValueError(f"a1_cell must look like 'D4', got {a1_cell!r}")
        col_idx = 0
        for c in col_letters.upper():
            col_idx = col_idx * 26 + (ord(c) - ord("A") + 1)
        col_idx -= 1  # 0-based
        row_idx = int(row_digits) - 1  # 0-based
        r = self.http.post(
            f"{SHEETS_API}/{sheet_id}:batchUpdate",
            json={
                "requests": [
                    {
                        "addNamedRange": {
                            "namedRange": {
                                "name": name,
                                "range": {
                                    "sheetId": tab_sheet_id,
                                    "startRowIndex": row_idx,
                                    "endRowIndex": row_idx + 1,
                                    "startColumnIndex": col_idx,
                                    "endColumnIndex": col_idx + 1,
                                },
                            }
                        }
                    }
                ]
            },
        )
        r.raise_for_status()
        return r.json()

    def named_ranges(self, sheet_id: str) -> list[dict]:
        """Return named ranges as `[{name, range}]`, with range as A1 (e.g. `'General'!D6`).

        The name alone is a valid A1 reference for `get`/`update`, so callers usually
        only need `name`. The A1 string is included for humans inspecting the layout.
        """
        r = self.http.get(
            f"{SHEETS_API}/{sheet_id}",
            params={"fields": "namedRanges,sheets.properties(sheetId,title)"},
        )
        r.raise_for_status()
        data = r.json()
        tabs = {
            s["properties"]["sheetId"]: s["properties"]["title"] for s in data.get("sheets", [])
        }
        out = []
        for nr in data.get("namedRanges", []):
            rng = nr.get("range", {})
            tab = tabs.get(rng.get("sheetId", 0), "")
            a1 = f"'{tab}'!{_a1(rng)}" if tab else _a1(rng)
            out.append({"name": nr["name"], "range": a1})
        out.sort(key=lambda x: x["name"])
        return out

    def get(self, sheet_id: str, range_name: str) -> list[list]:
        r = self.http.get(f"{SHEETS_API}/{sheet_id}/values/{range_name}")
        r.raise_for_status()
        return r.json().get("values", [])

    def update(
        self,
        sheet_id: str,
        range_name: str,
        values: list[list],
        *,
        raw: bool = False,
    ) -> dict:
        r = self.http.put(
            f"{SHEETS_API}/{sheet_id}/values/{range_name}",
            params={"valueInputOption": "RAW" if raw else "USER_ENTERED"},
            json={"values": values},
        )
        r.raise_for_status()
        return r.json()

    def append(self, sheet_id: str, range_name: str, values: list[list]) -> dict:
        r = self.http.post(
            f"{SHEETS_API}/{sheet_id}/values/{range_name}:append",
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            json={"values": values},
        )
        r.raise_for_status()
        return r.json()

    def clear(self, sheet_id: str, range_name: str) -> dict:
        r = self.http.post(f"{SHEETS_API}/{sheet_id}/values/{range_name}:clear", json={})
        r.raise_for_status()
        return r.json()

    def batch_clear(self, sheet_id: str, ranges: list[str]) -> dict:
        r = self.http.post(
            f"{SHEETS_API}/{sheet_id}/values:batchClear", json={"ranges": ranges}
        )
        r.raise_for_status()
        return r.json()

    def batch_update(self, sheet_id: str, updates: dict[str, list[list]]) -> dict:
        """One round-trip multi-range write: `{range: [[values]], ...}`."""
        r = self.http.post(
            f"{SHEETS_API}/{sheet_id}/values:batchUpdate",
            json={
                "valueInputOption": "USER_ENTERED",
                "data": [{"range": k, "values": v} for k, v in updates.items()],
            },
        )
        r.raise_for_status()
        return r.json()

    # --- native Google Sheets Tables (the green-chip kind) -------------------

    def tables(self, sheet_id: str) -> list[dict]:
        """List native Tables in the workbook.

        Returns `[{id, name, range, columns}]` — `columns` is column names in order
        (left-to-right). Use `name` or `id` as the lookup key for read/append.
        """
        r = self.http.get(
            f"{SHEETS_API}/{sheet_id}",
            params={"fields": "sheets(properties(sheetId,title),tables)"},
        )
        r.raise_for_status()
        data = r.json()
        tabs = {
            s["properties"]["sheetId"]: s["properties"]["title"] for s in data.get("sheets", [])
        }
        out = []
        for sheet in data.get("sheets", []):
            for t in sheet.get("tables", []):
                rng = t["range"]
                tab = tabs.get(rng.get("sheetId"))
                a1 = f"'{tab}'!{_a1(rng)}" if tab else _a1(rng)
                cols = sorted(
                    t.get("columnProperties", []), key=lambda c: c.get("columnIndex", 0)
                )
                out.append(
                    {
                        "id": t["tableId"],
                        "name": t["name"],
                        "range": a1,
                        "columns": [c.get("columnName", "") for c in cols],
                    }
                )
        return out

    def _find_table(self, sheet_id: str, name_or_id: str) -> dict:
        for t in self.tables(sheet_id):
            if t["name"] == name_or_id or t["id"] == name_or_id:
                return t
        raise ValueError(f"no table named or with id {name_or_id!r}")

    def read_table(self, sheet_id: str, name_or_id: str) -> list[dict]:
        """Read a native Table as `[{col_name: value}]` rows (header row skipped)."""
        t = self._find_table(sheet_id, name_or_id)
        values = self.get(sheet_id, t["range"])
        cols = t["columns"]
        out = []
        for row in values[1:]:  # skip header row
            padded = list(row) + [""] * (len(cols) - len(row))
            out.append(dict(zip(cols, padded)))
        return out

    def delete_rows(self, sheet_id: str, tab_sheet_id: int, start_row: int, end_row: int) -> dict:
        """Delete rows `start_row..end_row` (1-based, inclusive) from a tab.

        Shrinks any native Table on the tab whose range covers the deleted rows
        (unlike `clear`, which only blanks values and leaves the table range intact).
        """
        r = self.http.post(
            f"{SHEETS_API}/{sheet_id}:batchUpdate",
            json={
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": tab_sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start_row - 1,
                                "endIndex": end_row,
                            }
                        }
                    }
                ]
            },
        )
        r.raise_for_status()
        return r.json()

    def rename_table(self, sheet_id: str, name_or_id: str, new_name: str) -> dict:
        """Rename a native Table (via batchUpdate `updateTable`). Columns untouched."""
        t = self._find_table(sheet_id, name_or_id)
        r = self.http.post(
            f"{SHEETS_API}/{sheet_id}:batchUpdate",
            json={
                "requests": [
                    {"updateTable": {"table": {"tableId": t["id"], "name": new_name}, "fields": "name"}}
                ]
            },
        )
        r.raise_for_status()
        return r.json()

    def append_table(self, sheet_id: str, name_or_id: str, rows: list[dict]) -> dict:
        """Append dict rows to a native Table.

        Missing keys → empty cells; unknown keys are dropped. Google Sheets
        auto-extends the table's range to cover the new rows.
        """
        t = self._find_table(sheet_id, name_or_id)
        cols = t["columns"]
        values = [[r.get(c, "") for c in cols] for r in rows]
        return self.append(sheet_id, t["range"], values)


def _a1(rng: dict) -> str:
    """Convert a GridRange (0-based, half-open) to A1 notation."""
    r1 = rng.get("startRowIndex", 0) + 1
    r2 = rng.get("endRowIndex", r1)
    c1 = _col(rng.get("startColumnIndex", 0))
    c2 = _col(rng.get("endColumnIndex", rng.get("startColumnIndex", 0) + 1) - 1)
    return f"{c1}{r1}" if r1 == r2 and c1 == c2 else f"{c1}{r1}:{c2}{r2}"


def _col(idx: int) -> str:
    """0-based column index → A1 letters (0 → A, 26 → AA)."""
    s = ""
    n = idx
    while True:
        s = chr(ord("A") + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            return s

