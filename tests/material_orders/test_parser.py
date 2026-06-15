"""Parser unit tests — no Flask/DB, just the .eml fixture through parse_order_email."""
import os

from app.brain.material_orders.eml_adapter import eml_to_payload
from app.brain.material_orders.parser import parse_order_email

FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "drexel_580-659_decking_order.eml"
)


def _parsed():
    return parse_order_email(eml_to_payload(FIXTURE))


def test_parses_supplier_and_contact():
    p = _parsed()
    assert p is not None
    assert p["supplier"] == "Drexel Supply"
    assert "nick@drexelsupply.com" in (p["supplier_contact"] or "")


def test_parses_po_and_job_release():
    p = _parsed()
    assert p["po_number"] == "580-659"
    assert p["job"] == 580
    assert p["release"] == "659"


def test_parses_single_order_line():
    p = _parsed()
    assert len(p["lines"]) == 1
    line = p["lines"][0]
    assert line["quantity"] == 45.0
    assert "1.5C" in line["description"]
    assert "Decking" in line["description"]


def test_parses_part_subfields():
    line = _parsed()["lines"][0]
    assert line["profile"] == "1.5C"
    assert line["gauge"] == "18Ga"
    assert line["finish"] == "Galvanized"
    assert line["dimension"] == '48"'


def test_ordered_date_present():
    assert _parsed()["ordered_at"] is not None


def test_non_order_email_returns_none():
    payload = {
        "subject": "Lunch tomorrow?",
        "body": "Hey, are we still on for lunch? No PO, no quantities here.",
        "body_content_type": "text",
    }
    assert parse_order_email(payload) is None
