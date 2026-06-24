"""Parser unit tests — no Flask/DB, just the .eml fixture through parse_order_email."""
import datetime
import os

from app.brain.material_orders.eml_adapter import eml_to_payload
from app.brain.material_orders.parser import _parse_email_date, parse_order_email

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


def test_orderer_is_innermost_sender_not_forwarder():
    # The .eml is a forward chain: Bill O'Neill forwarded Rourke Alvarado's order.
    # The orderer is the innermost (original) sender, never the forwarder.
    p = _parsed()
    assert p["ordered_by"] == "Rourke Alvarado"
    assert p["ordered_by_email"] == "ralvarado@mhmw.com"


def test_ordered_date_is_inner_placement_date():
    # Parsed from the inner "Sent: Monday, 15 June 2026 07:41:28", not the forward time.
    assert _parsed()["ordered_at"] == datetime.date(2026, 6, 15)


def test_orderer_falls_back_to_envelope_without_forwarded_block():
    # A direct (non-forwarded) order email has no inner "From:" block, so the orderer
    # is left null and ordered_at falls back to the message envelope's sent time.
    payload = {
        "subject": "580-659 Decking Order",
        "from": {"name": "Rourke Alvarado", "address": "ralvarado@mhmw.com"},
        "sent_at": "2026-06-15T07:41:28+00:00",
        "body": "Please use PO# 580-659\nQty (45) 1.5C 18Ga. Galvanized Decking @ 48\"",
        "body_content_type": "text",
    }
    p = parse_order_email(payload)
    assert p is not None
    assert p["ordered_by"] is None
    assert p["ordered_by_email"] is None
    assert p["ordered_at"] == datetime.date(2026, 6, 15)


def test_parse_email_date_handles_outlook_and_gmail_formats():
    assert _parse_email_date("Monday, 15 June 2026 07:41:28").date() == datetime.date(2026, 6, 15)
    assert _parse_email_date("Mon, Jun 15, 2026 at 8:31 AM").date() == datetime.date(2026, 6, 15)
    assert _parse_email_date("nonsense") is None


def test_non_order_email_returns_none():
    payload = {
        "subject": "Lunch tomorrow?",
        "body": "Hey, are we still on for lunch? No PO, no quantities here.",
        "body_content_type": "text",
    }
    assert parse_order_email(payload) is None
