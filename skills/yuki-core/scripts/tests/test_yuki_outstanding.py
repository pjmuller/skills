from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from yuki_core.outstanding import (YukiDataError, clean_description, last_closed_quarter, parse_items,
                                   quarter_bounds, select, to_csv)
from datetime import date


def item(id="a1", day="2026-08-01", amount="-29.00", type_="Creditcardbetaling", desc="Factuur van Acme", contact="Acme"):
    id_attr = f' ID="{id}"' if id else ""
    return (f"<Item{id_attr}><Date>{day}</Date><Description>{desc}</Description><Contact>{contact}</Contact>"
            f"<OpenAmount>{amount}</OpenAmount><OriginalAmount>{amount}</OriginalAmount>"
            f'<Type ID="">{type_}</Type><DocumentID>d-{id}</DocumentID></Item>')


def response(*items):
    return ET.fromstring(f"<OutstandingCreditorItems>{''.join(items)}</OutstandingCreditorItems>")


def test_quarter_selection_and_invoice_drop():
    raw = response(item("old", "2026-05-02"), item("in", "2026-09-30"), item("late", "2026-10-01"),
                   item("inv", "2026-08-01", "120.00", "Aankoopfactuur"), item("refund", "2026-07-01", "15.00"))
    rows = select(parse_items(raw), "2026-Q3")
    assert [r["item_id"] for r in rows] == ["refund", "in"]  # older open items belong to their own quarter
    assert rows[0]["type"] == "Card" and rows[0]["amount"] == Decimal("15.00")


def test_fx_uses_belgian_number_format():
    desc = "MASTERCARD - Kaartverrichtingen - AWS EMEA   LUX - Vreemde valuta: USD -1.090,21 Wisselkoers: 1,14 - AWS"
    row = parse_items(response(item(desc=desc)))[0]
    assert (row["foreign_currency"], row["foreign_amount"], row["exchange_rate"]) == ("USD", Decimal("-1090.21"), Decimal("1.14"))
    assert row["description_clean"] == "Mastercard: AWS EMEA LUX"


@pytest.mark.parametrize("raw", [
    response(item(amount="12,5")),        # malformed amount: never a silent 0.0
    response(item(day="")),               # undated
    ET.fromstring("<Fault/>"),            # wrong response shape
    None,
])
def test_malformed_responses_raise(raw):
    with pytest.raises(YukiDataError):
        parse_items(raw)


@pytest.mark.parametrize("items", [(item(id=""),), (item("x"), item("x"))])
def test_missing_or_colliding_ids_refuse(items):
    with pytest.raises(YukiDataError):
        select(parse_items(response(*items)), "2026-Q3")


def test_generic_description_falls_back_to_contact():
    desc = "Kaarten : Afrekening kredietkaarten | Betaling met debetkaart binnen eurozone | Netto bedrag: 29,00"
    assert parse_items(response(item(desc=desc, contact="Versio")))[0]["description_clean"] == "Versio"


@pytest.mark.parametrize("raw, clean", [
    ("Binnenlandse overschrijvingen - SEPA credit transfers : Overschrijving te uwen gunste | Netto bedrag: 1.234,56", "SEPA inkomend"),
    ("SEPA credit transfers : Enkelvoudige overschrijving | Netto bedrag: 500,00 : Payment to supplier", "Payment to supplier"),
    ("Domiciliëring | Identificatiecode van de schuldeiser: BE123", "Domiciliering (schuldeiser: BE123)"),
])
def test_clean_description(raw, clean):
    assert clean_description(raw) == clean


def test_quarters_and_csv():
    assert quarter_bounds("2026-Q4") == (date(2026, 10, 1), date(2026, 12, 31))
    assert last_closed_quarter(date(2026, 10, 6)) == "2026-Q3"
    assert last_closed_quarter(date(2027, 2, 1)) == "2026-Q4"
    csv = to_csv(select(parse_items(response(item())), "2026-Q3"))
    assert csv.splitlines()[1].startswith("2026-08-01,Acme,-29.00,-29.00,Card,")
