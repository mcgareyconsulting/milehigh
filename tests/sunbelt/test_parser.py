"""Unit tests for the Sunbelt CSV parser (no DB/Flask needed)."""
from datetime import date
from decimal import Decimal

import pytest

from app.brain.sunbelt.parser import parse_sunbelt_csv, SunbeltCsvError
from tests.sunbelt.conftest import CSV_PATH


def test_parses_sample_csv_row_count():
    with open(CSV_PATH, "rb") as f:
        rows = parse_sunbelt_csv(f)
    assert len(rows) == 21  # 22 data lines minus the trailing blank line


def test_money_and_date_and_quantity_parsing():
    with open(CSV_PATH, "rb") as f:
        rows = parse_sunbelt_csv(f)
    # Row 3 (Alta Flatirons scissor): Week Rate $415.00, rented 6/2/2026.
    scissor = next(r for r in rows if r["contract_number"] == "184625948")
    assert scissor["week_rate"] == Decimal("415.00")
    assert scissor["date_rented"] == date(2026, 6, 2)
    assert scissor["quantity"] == 1
    assert scissor["po_number"] == "480"


def test_blank_billed_through_is_none():
    with open(CSV_PATH, "rb") as f:
        rows = parse_sunbelt_csv(f)
    # Capital Hill screed blade has an empty Billed Through column.
    cap = next(r for r in rows if r["po_number"] == "490" and r["billed_through"] is None)
    assert cap["billed_through"] is None


def test_zero_dollar_accessory_parses_to_zero():
    with open(CSV_PATH, "rb") as f:
        rows = parse_sunbelt_csv(f)
    forks = next(r for r in rows if r["equipment_number"] == "FORKSLTELH")
    assert forks["day_rate"] == Decimal("0.00")


def test_bad_header_raises():
    with pytest.raises(SunbeltCsvError):
        parse_sunbelt_csv("Foo,Bar,Baz\n1,2,3\n")


def test_accepts_string_and_bytes():
    csv = (
        '"Contract #","Job #","Job_Location","Ordered By","PO_Number",'
        '"Equipment Type","Equipment #","Make","Model","Quantity",'
        '"Est Return Date","Day Rate","Week Rate","4 Week Rate","Billed Through","Date Rented"\n'
        '"1","X","ADDR","FERRIN","480","FORK","E1","JCB","50","1",'
        '"6/30/2026","$10.00","$50.00","$100.00","","6/1/2026"\n'
    )
    rows_str = parse_sunbelt_csv(csv)
    rows_bytes = parse_sunbelt_csv(csv.encode("utf-8"))
    assert len(rows_str) == len(rows_bytes) == 1
    assert rows_str[0]["week_rate"] == Decimal("50.00")
