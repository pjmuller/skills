import json
from decimal import Decimal

import pytest

from yuki_core.outstanding import COLUMNS
from yuki_core.sheet import push

MANUAL = ["Resp", "Done"]
HEADER = MANUAL + COLUMNS


def row(item_id, day="2026-08-01", amount="-10.00", desc="raw", carryover=""):
    r = {c: "" for c in COLUMNS}
    r.update(item_id=item_id, date=day, amount=Decimal(amount), original_amount=Decimal(amount),
             description_raw=desc, description_clean=desc, carryover=carryover, type="Card")
    return r


def sheet_row(r):
    return [""] * len(MANUAL) + [str(r[c]) for c in COLUMNS]


class FakeGws:
    """In-memory spreadsheet speaking the gws CLI subset sheet.push uses."""

    def __init__(self, tabs):
        self.tabs = tabs
        self.calls = []

    def __call__(self, cmd, sid, *args):
        self.calls.append(cmd)
        if cmd == "sheet-meta":
            return {"sheets": [{"properties": {"title": t, "sheetId": i}} for i, t in enumerate(self.tabs)]}
        if cmd == "sheet-read":
            return {"values": self.tabs[args[0].strip("'")]}
        if cmd == "sheet-add-tab":
            self.tabs[args[0]] = []
            return {"replies": [{"addSheet": {"properties": {"sheetId": 99}}}]}
        if cmd == "sheet-write":
            tab, start = args[0].split("!A")
            values = self.tabs[tab.strip("'")]
            assert len(values) == int(start) - 1 and "--raw" in args
            values.extend([["" if c is None else str(c) for c in r] for r in json.loads(args[-1])])
            return {}
        if cmd == "sheet-batch":
            self.batch = json.load(open(args[-1]))
            return {}
        raise AssertionError(cmd)


def test_creates_tab_seeds_from_legacy_tab_and_reruns_idempotently():
    legacy = ["Resp", "Done", "date", "original_amount", "description_raw"]
    gws = FakeGws({"2026 - Q2": [legacy, ["Will", "TRUE", "2026-05-02", "-10.00", "old"],
                                 ["A", "", "2026-05-03", "-5.00", "dup"], ["B", "", "2026-05-03", "-5.00", "dup"]]})
    rows = [row("x", "2026-05-02", desc="old", carryover="yes"), row("y", "2026-05-03", "-5.00", "dup", "yes"), row("z")]
    summary = push(gws, "sid", MANUAL, "2026-Q3", rows)
    tab = gws.tabs["2026-Q3"]
    assert summary["created"] and summary["appended"] == 3 and summary["seeded"] == 1
    assert tab[0] == HEADER
    assert tab[1][:2] == ["Will", "True"] and tab[2][:2] == ["", ""]  # unique match seeded, ambiguous blank
    assert tab[1][HEADER.index("amount")] == "-10.0"  # written as a number
    assert gws.batch["requests"][0]["updateSheetProperties"]["properties"]["gridProperties"] == {"frozenRowCount": 1}

    tab[1][1] = "manual edit"
    again = push(gws, "sid", MANUAL, "2026-Q3", rows + [row("w")])
    assert again["appended"] == 1 and len(tab) == 5 and tab[1][1] == "manual edit"
    assert push(gws, "sid", MANUAL, "2026-Q3", rows)["appended"] == 0


def test_header_mismatch_and_dry_run_write_nothing():
    gws = FakeGws({"2026-Q3": [["Resp"] + COLUMNS]})
    with pytest.raises(ValueError, match="header differs"):
        push(gws, "sid", MANUAL, "2026-Q3", [row("x")])
    gws = FakeGws({"2026-Q3": [HEADER, sheet_row(row("x"))]})
    summary = push(gws, "sid", MANUAL, "2026-Q3", [row("x"), row("y")], dry_run=True)
    assert summary["appended"] == 1 and "sheet-write" not in gws.calls
