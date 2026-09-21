"""Google Sheets: values, tabs, named ranges and native Tables."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .errors import WorkspaceError
from .inputs import extract_id
from .session import SHEETS, Session


def a1_column(index: int) -> str:
    """0-based column index → A1 letters (0 → A, 26 → AA)."""
    letters = ""
    value = index
    while True:
        letters = chr(ord("A") + value % 26) + letters
        value = value // 26 - 1
        if value < 0:
            return letters


def a1_range(grid: dict) -> str:
    """GridRange (0-based, half-open) → A1 without the tab prefix."""
    first_row = grid.get("startRowIndex", 0) + 1
    last_row = grid.get("endRowIndex", first_row)
    first_col = a1_column(grid.get("startColumnIndex", 0))
    last_col = a1_column(grid.get("endColumnIndex", grid.get("startColumnIndex", 0) + 1) - 1)
    if first_row == last_row and first_col == last_col:
        return f"{first_col}{first_row}"
    return f"{first_col}{first_row}:{last_col}{last_row}"


class SheetsClient:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- values -------------------------------------------------------------

    def meta(self, sheet: str) -> dict:
        return self.session.api(
            "GET", f"{SHEETS}/{extract_id(sheet)}",
            params={"fields": "spreadsheetId,properties.title,sheets.properties"},
        )

    def read(self, sheet: str, cell_range: str) -> dict:
        return self.session.api(
            "GET", f"{SHEETS}/{extract_id(sheet)}/values/{quote(cell_range, safe='')}",
            params={"majorDimension": "ROWS", "valueRenderOption": "FORMATTED_VALUE",
                    "dateTimeRenderOption": "FORMATTED_STRING"},
        )

    def values(self, sheet: str, cell_range: str) -> list[list]:
        return self.read(sheet, cell_range).get("values", [])

    def write(self, sheet: str, cell_range: str, values: list[list], *, raw: bool = False) -> dict:
        return self.session.api(
            "PUT", f"{SHEETS}/{extract_id(sheet)}/values/{quote(cell_range, safe='')}",
            params={"valueInputOption": "RAW" if raw else "USER_ENTERED"}, json={"values": values},
        )

    def append(self, sheet: str, cell_range: str, values: list[list]) -> dict:
        return self.session.api(
            "POST", f"{SHEETS}/{extract_id(sheet)}/values/{quote(cell_range, safe='')}:append",
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            json={"values": values},
        )

    def clear(self, sheet: str, cell_range: str) -> dict:
        return self.session.api(
            "POST", f"{SHEETS}/{extract_id(sheet)}/values/{quote(cell_range, safe='')}:clear", json={})

    def batch_clear(self, sheet: str, ranges: list[str]) -> dict:
        return self.session.api("POST", f"{SHEETS}/{extract_id(sheet)}/values:batchClear",
                                json={"ranges": ranges})

    def batch_write(self, sheet: str, updates: dict[str, list[list]]) -> dict:
        """One round-trip multi-range write: `{range: [[values]], …}`."""
        return self.session.api(
            "POST", f"{SHEETS}/{extract_id(sheet)}/values:batchUpdate",
            json={"valueInputOption": "USER_ENTERED",
                  "data": [{"range": key, "values": value} for key, value in updates.items()]},
        )

    def batch(self, sheet: str, body: dict) -> dict:
        """Raw spreadsheets.batchUpdate for everything with no dedicated command."""
        return self.session.api("POST", f"{SHEETS}/{extract_id(sheet)}:batchUpdate", json=body)

    # --- structure ----------------------------------------------------------

    def add_tab(self, sheet: str, title: str) -> dict:
        return self.batch(sheet, {"requests": [{"addSheet": {"properties": {"title": title}}}]})

    def delete_rows(self, sheet: str, tab_sheet_id: int, start_row: int, end_row: int) -> dict:
        """Delete rows start..end (1-based, inclusive); shrinks a native Table covering them."""
        return self.batch(sheet, {"requests": [{"deleteDimension": {"range": {
            "sheetId": tab_sheet_id, "dimension": "ROWS",
            "startIndex": start_row - 1, "endIndex": end_row}}}]})

    def freeze_rows(self, sheet: str, tab_sheet_id: int, rows: int = 1) -> dict:
        return self.batch(sheet, {"requests": [{"updateSheetProperties": {
            "properties": {"sheetId": tab_sheet_id, "gridProperties": {"frozenRowCount": rows}},
            "fields": "gridProperties.frozenRowCount"}}]})

    def format_rows(self, sheet: str, tab_sheet_id: int, row_count: int, col_count: int,
                    *, pixel_size: int = 21) -> dict:
        """Clip cell text and reset row heights, for dense machine-written dumps."""
        return self.batch(sheet, {"requests": [
            {"repeatCell": {
                "range": {"sheetId": tab_sheet_id, "startRowIndex": 0, "endRowIndex": row_count,
                          "startColumnIndex": 0, "endColumnIndex": col_count},
                "cell": {"userEnteredFormat": {"wrapStrategy": "CLIP"}},
                "fields": "userEnteredFormat.wrapStrategy"}},
            {"updateDimensionProperties": {
                "range": {"sheetId": tab_sheet_id, "dimension": "ROWS",
                          "startIndex": 0, "endIndex": row_count},
                "properties": {"pixelSize": pixel_size}, "fields": "pixelSize"}},
        ]})

    def named_ranges(self, sheet: str) -> list[dict]:
        """`[{name, range}]`; the name alone is a valid A1 reference for read/write."""
        data = self.session.api(
            "GET", f"{SHEETS}/{extract_id(sheet)}",
            params={"fields": "namedRanges,sheets.properties(sheetId,title)"})
        tabs = {tab["properties"]["sheetId"]: tab["properties"]["title"]
                for tab in data.get("sheets", [])}
        found = []
        for entry in data.get("namedRanges", []):
            grid = entry.get("range", {})
            tab = tabs.get(grid.get("sheetId", 0), "")
            reference = a1_range(grid)
            found.append({"name": entry["name"], "range": f"'{tab}'!{reference}" if tab else reference})
        return sorted(found, key=lambda item: item["name"])

    def add_named_range(self, sheet: str, name: str, tab_sheet_id: int, a1_cell: str) -> dict:
        """Single-cell named range; `a1_cell` is plain A1 with no tab prefix (`D4`)."""
        letters = "".join(char for char in a1_cell if char.isalpha())
        digits = "".join(char for char in a1_cell if char.isdigit())
        if not letters or not digits:
            raise WorkspaceError(f"a1_cell must look like 'D4', got {a1_cell!r}")
        column = 0
        for char in letters.upper():
            column = column * 26 + (ord(char) - ord("A") + 1)
        column -= 1
        row = int(digits) - 1
        return self.batch(sheet, {"requests": [{"addNamedRange": {"namedRange": {
            "name": name,
            "range": {"sheetId": tab_sheet_id, "startRowIndex": row, "endRowIndex": row + 1,
                      "startColumnIndex": column, "endColumnIndex": column + 1}}}}]})

    # --- native Tables (the green-chip kind) --------------------------------

    def tables(self, sheet: str) -> list[dict]:
        """`[{id, name, range, columns}]`; `columns` in left-to-right order."""
        data = self.session.api("GET", f"{SHEETS}/{extract_id(sheet)}",
                                params={"fields": "sheets(properties(sheetId,title),tables)"})
        tabs = {tab["properties"]["sheetId"]: tab["properties"]["title"]
                for tab in data.get("sheets", [])}
        found = []
        for tab in data.get("sheets", []):
            for table in tab.get("tables", []):
                grid = table["range"]
                name = tabs.get(grid.get("sheetId"))
                reference = a1_range(grid)
                columns = sorted(table.get("columnProperties", []),
                                 key=lambda column: column.get("columnIndex", 0))
                found.append({
                    "id": table["tableId"], "name": table["name"],
                    "range": f"'{name}'!{reference}" if name else reference,
                    "columns": [column.get("columnName", "") for column in columns],
                })
        return found

    def _table(self, sheet: str, name_or_id: str) -> dict:
        for table in self.tables(sheet):
            if name_or_id in (table["name"], table["id"]):
                return table
        raise WorkspaceError(f"no table named or with id {name_or_id!r}")

    def read_table(self, sheet: str, name_or_id: str) -> list[dict]:
        """Rows as `[{column: value}]`, header row skipped."""
        table = self._table(sheet, name_or_id)
        columns = table["columns"]
        rows = self.values(sheet, table["range"])
        return [dict(zip(columns, list(row) + [""] * (len(columns) - len(row)))) for row in rows[1:]]

    def append_table(self, sheet: str, name_or_id: str, rows: list[dict[str, Any]]) -> dict:
        """Append dict rows; missing keys become empty cells, unknown keys are dropped."""
        table = self._table(sheet, name_or_id)
        columns = table["columns"]
        values = [[row.get(column, "") for column in columns] for row in rows]
        return self.append(sheet, table["range"], values)

    def rename_table(self, sheet: str, name_or_id: str, new_name: str) -> dict:
        table = self._table(sheet, name_or_id)
        return self.batch(sheet, {"requests": [{"updateTable": {
            "table": {"tableId": table["id"], "name": new_name}, "fields": "name"}}]})
