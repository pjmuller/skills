import json
from decimal import Decimal
from urllib.parse import unquote

import pytest

from yuki_core.outstanding import COLUMNS
from yuki_core.sheet import push

MANUAL = ["Resp", "Done"]
HEADER = MANUAL + COLUMNS
LEGACY = ["Resp", "Done", "date", "original_amount", "description_raw"]


def row(item_id, day="2026-08-01", amount="-10.00", desc="raw"):
    r = {c: "" for c in COLUMNS}
    r.update(item_id=item_id, date=day, amount=Decimal(amount), original_amount=Decimal(amount),
             description_raw=desc, description_clean=desc, type="Card")
    return r


def sheet_row(r, width=len(MANUAL)):
    return [""] * width + [str(r[c]) for c in COLUMNS]


class FakeGws:
    """In-memory spreadsheet speaking the gws CLI subset sheet.push uses."""

    def __init__(self, tabs, unformatted=None, filters=None):
        self.tabs = tabs
        self.unformatted = unformatted or {}  # tab -> values as UNFORMATTED_VALUE returns them
        self.filters = filters or {}
        self.calls, self.batches, self.user_entered = [], [], []

    def __call__(self, cmd, *args):
        self.calls.append(cmd)
        if cmd == "api":
            url = args[1]
            if "/values/" in url:
                tab = unquote(url.rsplit("/", 1)[1]).strip("'")
                return {"values": self.unformatted.get(tab, self.tabs[tab])}
            return {"sheets": [{"properties": {"title": t, "sheetId": i}, **({"basicFilter": self.filters[t]} if t in self.filters else {})}
                               for i, t in enumerate(self.tabs)]}
        if cmd == "sheet-read":
            return {"values": self.tabs[args[1].strip("'")]}
        if cmd == "sheet-add-tab":
            self.tabs[args[1]] = []
            return {"replies": [{"addSheet": {"properties": {"sheetId": 99}}}]}
        if cmd == "sheet-write":
            tab, start = args[1].split("!A")
            values, start = self.tabs[tab.strip("'")], int(start)
            if "--raw" in args:
                assert len(values) == start - 1
                values.extend([["" if c is None else str(c) for c in r] for r in json.loads(args[-1])])
            else:
                self.user_entered.append(json.loads(args[-1]))
                for n, cells in enumerate(json.loads(args[-1])):
                    values[start - 1 + n][:len(cells)] = cells
            return {}
        if cmd == "sheet-batch":
            self.batches.append(json.load(open(args[-1]))["requests"])
            return {}
        raise AssertionError(cmd)


def test_creates_tab_seeds_from_legacy_tab_and_reruns_idempotently():
    gws = FakeGws({"2026 - Q2": [LEGACY, ["Will", "TRUE", "2026-07-02", "-10.00", "old"],
                                 ["A", "", "2026-07-03", "-5.00", "dup"], ["B", "", "2026-07-03", "-5.00", "dup"]]})
    rows = [row("x", "2026-07-02", desc="old"), row("y", "2026-07-03", "-5.00", "dup"), row("z")]
    summary = push(gws, "sid", MANUAL, "2026-Q3", rows)
    tab = gws.tabs["2026-Q3"]
    assert summary["created"] and summary["appended"] == 3 and summary["seeded"] == 1
    assert tab[0] == HEADER
    assert tab[1][:2] == ["Will", "True"] and tab[2][:2] == ["", ""]  # unique match seeded, ambiguous blank
    assert tab[1][HEADER.index("amount")] == "-10.0"  # written as a number
    layout = gws.batches[0]
    assert layout[0]["updateSheetProperties"]["properties"]["gridProperties"] == {"frozenRowCount": 1}
    sort = next(r["setBasicFilter"]["filter"] for r in layout if "setBasicFilter" in r)
    assert sort["range"]["endRowIndex"] == 4 and [s["dimensionIndex"] for s in sort["sortSpecs"]] == \
        [HEADER.index("description_clean"), HEADER.index("date")]

    tab[1][1] = "manual edit"
    again = push(gws, "sid", MANUAL, "2026-Q3", rows + [row("w")])
    assert again["appended"] == 1 and len(tab) == 5 and tab[1][1] == "manual edit"
    assert push(gws, "sid", MANUAL, "2026-Q3", rows)["appended"] == 0


def test_formula_column_and_existing_filter_grows():
    rules = [{"name": "Likely resp", "rules": [{"label": "PJ", "pattern": '(?i)kbc|"q"'}, {"label": "Will", "pattern": "(?i)figma"}]}]
    header = ["Likely resp"] + HEADER
    old = {"range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": len(header)},
           "sortSpecs": [{"dimensionIndex": 12, "sortOrder": "ASCENDING"}], "criteria": {"0": {}}, "filterSpecs": [{"columnIndex": 0}]}
    gws = FakeGws({"2026-Q3 test": [header, sheet_row(row("x"), 3)]}, filters={"2026-Q3 test": old})
    summary = push(gws, "sid", MANUAL, "2026-Q3", [row("x"), row("y")], formulas=rules, tab="2026-Q3 test")
    assert summary["appended"] == 1
    # contact is column E, description_clean column L once the formula column leads (as in PJ's PB tab)
    assert gws.user_entered == [[['=IFS(REGEXMATCH(E3&" "&L3,"(?i)kbc|""q"""),"PJ",REGEXMATCH(E3&" "&L3,"(?i)figma"),"Will",TRUE,"")']]]
    grown = gws.batches[0][0]["setBasicFilter"]["filter"]
    assert grown["range"]["endRowIndex"] == 3 and grown["sortSpecs"] == old["sortSpecs"] and "criteria" not in grown


def test_header_mismatch_and_dry_run_write_nothing():
    gws = FakeGws({"2026-Q3": [["Resp"] + COLUMNS]})
    with pytest.raises(ValueError, match="header differs"):
        push(gws, "sid", MANUAL, "2026-Q3", [row("x")])
    gws = FakeGws({"2026-Q3": [HEADER, sheet_row(row("x"))]})
    summary = push(gws, "sid", MANUAL, "2026-Q3", [row("x"), row("y")], dry_run=True)
    assert summary["appended"] == 1 and "sheet-write" not in gws.calls


def test_legacy_key_must_be_unique_on_both_sides():
    """One annotated legacy row, two current Yuki rows with the same tuple: seed neither,
    also when one of the two was imported by an earlier push."""
    gws = FakeGws({"2026-Q2": [LEGACY, ["Will", "TRUE", "2026-07-02", "-10.00", "same"]]})
    twins = [row("a", "2026-07-02", desc="same"), row("b", "2026-07-02", desc="same")]
    assert push(gws, "sid", MANUAL, "2026-Q3", twins)["seeded"] == 0
    gws = FakeGws({"2026-Q2": gws.tabs["2026-Q2"], "2026-Q3": [HEADER, sheet_row(twins[0])]})
    assert push(gws, "sid", MANUAL, "2026-Q3", twins)["seeded"] == 0


def test_legacy_amount_matches_on_unformatted_value():
    """nl_BE sheets display "-10,00"; the unformatted -10 must match -10.00, never -1000."""
    shown = [LEGACY, ["Will", "TRUE", "2026-07-02", "-10,00", "fee"]]
    gws = FakeGws({"2026-Q2": shown}, {"2026-Q2": [LEGACY, ["Will", True, "2026-07-02", -10, "fee"]]})
    rows = [row("ten", "2026-07-02", "-10.00", "fee"), row("thousand", "2026-07-02", "-1000.00", "fee")]
    summary = push(gws, "sid", MANUAL, "2026-Q3", rows)
    tab = gws.tabs["2026-Q3"]
    assert summary["seeded"] == 1
    assert tab[1][:2] == ["Will", "True"] and tab[2][:2] == ["", ""]
