"""Yuki "Aan te leveren aankoopfacturen" (OutstandingCreditorItems) as clean rows for one quarter.

Yuki returns the items open *today*, not a quarter-end snapshot. A quarter selects rows dated up
to its end; rows dated before its start are kept with `carryover=yes` so stragglers stay visible.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from html import unescape

COLUMNS = [
    "date", "carryover", "contact", "amount", "original_amount", "type",
    "foreign_currency", "foreign_amount", "exchange_rate", "description_clean",
    "vat_number", "coc_number", "country", "city", "address", "due_date", "reference",
    "description_raw", "item_id", "document_id", "contact_id",
]
NUMERIC = {"amount", "original_amount", "foreign_amount", "exchange_rate"}

# Booked purchase invoices only appear as the counter-leg of an open payable; Yuki's UI screen
# does not list them (reconciled against a UI export, Pro Backup 2026-07: 0 of 88 shown).
INVOICE_TYPE = "Aankoopfactuur"
SHORT_TYPES = {"Banktransactie": "Bank", "Creditcardbetaling": "Card", "TRMReversal": "Reversal"}
GENERIC_DESCRIPTIONS = {"Kaartbetaling", "Domiciliering"}
QUARTER = re.compile(r"^(\d{4})-Q([1-4])$")


class YukiDataError(ValueError):
    """The Yuki response does not have the shape we rely on; never guess around it."""


def quarter_bounds(quarter: str) -> tuple[date, date]:
    match = QUARTER.match(quarter)
    if not match:
        raise ValueError(f"quarter must look like 2026-Q3, got {quarter!r}")
    year, q = int(match[1]), int(match[2])
    start = date(year, 3 * q - 2, 1)
    end = date(year + 1, 1, 1) if q == 4 else date(year, 3 * q + 1, 1)
    return start, date.fromordinal(end.toordinal() - 1)


def last_closed_quarter(today: date) -> str:
    q = (today.month - 1) // 3  # 0 means Q4 of last year
    return f"{today.year - 1}-Q4" if q == 0 else f"{today.year}-Q{q}"


def select(items: list[dict], quarter: str) -> list[dict]:
    """Payments without an invoice, dated up to the quarter end; both signs are kept
    (incoming refunds/settlements legitimately show up positive)."""
    start, end = quarter_bounds(quarter)
    rows = []
    for item in items:
        if item["type"] == INVOICE_TYPE or item["date"] > end.isoformat():
            continue
        rows.append({**item, "type": SHORT_TYPES.get(item["type"], item["type"]),
                     "carryover": "yes" if item["date"] < start.isoformat() else ""})
    ids = [row["item_id"] for row in rows]
    if not all(ids):
        raise YukiDataError("an outstanding item has no Item/@ID; refusing to dedupe without it")
    if len(set(ids)) != len(ids):
        raise YukiDataError("duplicate Item/@ID values in the Yuki response")
    return rows


def parse_items(raw) -> list[dict]:
    if raw is None or not hasattr(raw, "findall") or not str(raw.tag).endswith("OutstandingCreditorItems"):
        raise YukiDataError(f"unexpected OutstandingCreditorItems response: {type(raw).__name__}")
    return [_parse_item(el) for el in raw.findall(".//Item")]


def _parse_item(el) -> dict:
    raw_desc = _text(el, "Description")
    item_date = _text(el, "Date")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item_date):
        raise YukiDataError(f"item {el.get('ID')} has no ISO date: {item_date!r}")
    if el.find("Type") is None:
        raise YukiDataError(f"item {el.get('ID')} has no Type")
    fx = re.search(r"Vreemde valuta:\s*([A-Z]{3})\s*(-?[\d.]*\d(?:,\d+)?)\s*Wisselkoers:\s*([\d.]*\d(?:,\d+)?)", raw_desc)
    contact = _text(el, "Contact")
    clean = clean_description(raw_desc)
    if clean in GENERIC_DESCRIPTIONS and contact:
        clean = contact  # cleaning stripped all vendor info; the contact name still has it
    return {
        "date": item_date,
        "contact": contact,
        "amount": _amount(el, "OpenAmount"),
        "original_amount": _amount(el, "OriginalAmount"),
        "type": _text(el, "Type"),
        "foreign_currency": fx[1] if fx else "",
        "foreign_amount": _belgian_number(fx[2]) if fx else "",
        "exchange_rate": _belgian_number(fx[3]) if fx else "",
        "description_clean": clean,
        "vat_number": _text(el, "VATNumber"),
        "coc_number": _text(el, "CoCNumber"),
        "country": _text(el, "Country"),
        "city": _text(el, "City"),
        "address": ", ".join(v for v in (_text(el, t) for t in
                             ("AddressLine_1", "AddressLine_2", "Postcode", "City", "Country")) if v),
        "due_date": _text(el, "DueDate"),
        "reference": _text(el, "Reference"),
        "description_raw": raw_desc,
        "item_id": el.get("ID") or "",
        "document_id": _text(el, "DocumentID"),
        "contact_id": _text(el, "ContactID"),
    }


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return unescape(child.text.strip()) if child is not None and child.text else ""


def _amount(el, tag: str) -> Decimal:
    value = _text(el, tag)
    try:
        return Decimal(value)
    except InvalidOperation:
        raise YukiDataError(f"item {el.get('ID')} has a malformed {tag}: {value!r}") from None


def _belgian_number(value: str) -> Decimal:
    """'-1.090,21' -> Decimal('-1090.21') (dot = thousands, comma = decimals)."""
    return Decimal(value.replace(".", "").replace(",", "."))


def clean_description(desc: str) -> str:
    """Strip SEPA/card/domiciliëring boilerplate; description_raw keeps the original."""
    desc = unescape(desc or "").strip()

    mc = re.match(r"MASTERCARD - Kaartverrichtingen - (.+?)(?:\s*-\s*Vreemde valuta:.*)?$", desc)
    if mc:
        return "Mastercard: " + re.sub(r"\s{2,}", " ", mc[1].strip())
    if desc.startswith("PAYPAL"):
        return desc
    if desc.startswith("Factuur van "):
        return desc[len("Factuur van "):]
    if "Overschrijving te uwen gunste" in desc:
        desc = re.sub(r"^Binnenlandse overschrijvingen - SEPA credit transfers : "
                      r"Overschrijving te uwen gunste\s*", "SEPA inkomend: ", desc)
        desc = re.sub(r"\|\s*(Netto bedrag|Klantreferentie):.*", "", desc)
        return desc.strip().rstrip(":").strip()
    sepa = re.search(r"SEPA credit transfers?\s*:\s*(?:Enkelvoudige overschrijving|Betaling lonen.*?)"
                     r"\s*\|.*?:\s*(.*)", desc)
    if sepa:
        rest = re.sub(r"^[\d.,]+\s*:\s*", "", sepa[1].strip())  # "399,730 : " amount leak
        rest = re.sub(r"^Overschrijving of storting met een gestructureerde mededeling: \d+\s*\|\s*", "", rest)
        return rest or "SEPA overschrijving"
    if "Domicili" in desc:
        creditor = re.search(r"Identificatiecode van de schuldeiser:\s*(\S+)", desc)
        return f"Domiciliering (schuldeiser: {creditor[1]})" if creditor else "Domiciliering"
    if "Afrekening kredietkaarten" in desc or "debetkaart" in desc:
        s = re.sub(r"^Kaarten\s*:.*?Netto bedrag:\s*[\d.,]+\s*:?\s*\|?\s*", "", desc)
        s = re.sub(r"^(?:\|?\s*)?Debet ATM/POS.*?(?:Bancontact/Mister Cash|Mastercard)\s*[-–]?\s*", "", s)
        s = re.sub(r"^(?:\|?\s*)?Nummer kredietkaart.*?\|\s*", "", s)
        s = re.sub(r"Terminalnummer:\s*\d+\s*-\s*Volgnummer verrichting:\s*\d+\s*-\s*Datum verricht.*", "", s)
        return s.strip().lstrip("| ").strip() or "Kaartbetaling"
    desc = re.sub(r"\| (Klantreferentie|Netto bedrag): .*", "", desc)
    return desc.strip().lstrip("| ").strip()


def to_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: (f"{row[k]:.2f}" if k in ("amount", "original_amount") else row[k]) for k in COLUMNS})
    return out.getvalue()
