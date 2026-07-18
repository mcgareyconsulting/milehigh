"""Extractor/classifier tests — route each .eml fixture to the right shape.

No Flask/DB and no API key: the deterministic extractors (inline / Dencol confirm
PDF / Dencol drawing PDF) run keyless, and the LLM fallback degrades to None
without a key. The .eml fixtures carry their PDFs inline, so eml_to_payload yields
the same attachment shape the live Graph poll lands.
"""
import os
from types import SimpleNamespace

from app.brain.material_orders import parser
from app.brain.material_orders.eml_adapter import eml_to_payload
from app.brain.material_orders.extractors import (
    azz_galvanizing, classify, dencol_confirm, dencol_stock, drexel_inline, llm,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
DENCOL_CONFIRM = os.path.join(FIXTURES, "dencol_390-351_confirm.eml")
FALCON_DRAWING = os.path.join(FIXTURES, "falcon_575-402_drawing.eml")
DREXEL_INLINE = os.path.join(FIXTURES, "drexel_580-659_decking_order.eml")
AZZ_GALV = os.path.join(FIXTURES, "azz_480-913_ready_to_ship.eml")
DENCOL_STOCK = os.path.join(FIXTURES, "dencol_stock_pickup.eml")


def _record(eml_path, rid=1):
    return SimpleNamespace(id=rid, source="m365_mail", payload=eml_to_payload(eml_path))


# --- Dencol confirm (priced PDF table, supplier acknowledging the order) ---

def test_dencol_confirm_routes_to_confirm_extractor():
    assert dencol_confirm.matches(_record(DENCOL_CONFIRM))


def test_dencol_confirm_header_and_event():
    r = classify.extract_order(_record(DENCOL_CONFIRM))
    assert r is not None
    assert r["supplier"] == "Dencol"
    assert r["po_number"] == "390-351"
    assert r["job"] == 390 and r["release"] == "351"
    assert r["event_type"] == "confirmed"
    assert r["supplier_order_no"] == "2296464"


def test_dencol_confirm_orderer_is_mhmw_not_supplier():
    # The thread's innermost message is John Rendon's (Dencol) reply; the orderer
    # is the MHMW person who placed it, parsed from the quoted "Original Message".
    r = classify.extract_order(_record(DENCOL_CONFIRM))
    assert r["ordered_by"] == "David Servold"
    assert r["ordered_by_email"] == "dservold@mhmw.com"


def test_dencol_confirm_priced_lines():
    r = classify.extract_order(_record(DENCOL_CONFIRM))
    assert len(r["lines"]) == 4
    first = r["lines"][0]
    assert first["quantity"] == 2.0
    assert "PER DRAWING 351-b1014" in first["description"]
    assert first["unit_price"] == 30.50
    assert first["extended_price"] == 61.00
    # Drawing ids are recoverable across the table.
    assert {ln["description"].split("PER DRAWING ")[-1] for ln in r["lines"]} == {
        "351-b1014", "351-p1000", "351-p1001", "351-p1002",
    }


# --- Falcon outbound (CAD drawing PDF, we placed the order) ---

def test_falcon_drawing_extracts_plate_marks():
    r = classify.extract_order(_record(FALCON_DRAWING))
    assert r is not None
    assert r["supplier"] == "Dencol"
    assert r["po_number"] == "575-402"
    assert r["event_type"] == "placed"
    assert r["ordered_by"] == "David Servold"  # one-way forward, orderer recovered
    marks = {ln["profile"] for ln in r["lines"]}
    assert {"bp1000", "p1000", "p1001", "p1005", "bp1001"} <= marks
    assert len(r["lines"]) == 9
    p1000 = next(ln for ln in r["lines"] if ln["profile"] == "p1000")
    assert p1000["quantity"] == 10.0
    assert p1000["dimension"] == '1/2"'


# --- Drexel inline (unchanged through the registry) ---

def test_drexel_still_routes_to_inline():
    rec = _record(DREXEL_INLINE)
    assert drexel_inline.matches(rec)
    r = classify.extract_order(rec)
    assert r["supplier"] == "Drexel Supply"
    assert r["event_type"] == "placed"
    assert len(r["lines"]) == 1
    assert r["lines"][0]["quantity"] == 45.0


# --- LLM fallback degrades gracefully without a key ---

def test_llm_extractor_returns_none_without_key(monkeypatch):
    monkeypatch.setattr(llm.cfg, "ANTHROPIC_API_KEY", None)
    assert llm.extract(_record(FALCON_DRAWING)) is None


def test_classify_returns_none_when_nothing_recovers(monkeypatch):
    # An "order" with a PO but no inline lines and an attachment that matches no
    # deterministic shape: deterministic extractors yield nothing and, without a
    # key, the LLM fallback returns None — classify returns None, never raises.
    monkeypatch.setattr(llm.cfg, "ANTHROPIC_API_KEY", None)
    payload = {
        "subject": "PO# 999-111 misc",
        "body": "Please see attached.",
        "body_content_type": "text",
        "attachments": [
            {"filename": "note.pdf", "content_type": "application/pdf", "size": 10,
             "text": "Some unrelated text with no order table or callouts.",
             "storage_key": None},
        ],
    }
    rec = SimpleNamespace(id=2, source="m365_mail", payload=payload)
    assert classify.extract_order(rec) is None


# --- AZZ galvanizing status notification (no parts, one status row) ---

def test_azz_galv_routes_to_galv_extractor():
    rec = _record(AZZ_GALV)
    assert azz_galvanizing.matches(rec)
    # It must NOT be swallowed by the DenCol stock gate.
    assert not dencol_stock.matches(rec)


def test_azz_galv_header_status_and_job():
    r = classify.extract_order(_record(AZZ_GALV))
    assert r is not None
    assert r["supplier"] == "AZZ Galvanizing"
    assert r["order_kind"] == "galvanizing"
    assert r["event_type"] == "status"
    # Customer PO maps to our job-release; AZZ Job # is the supplier's own number.
    assert r["job"] == 480 and r["release"] == "913"
    assert r["supplier_order_no"] == "26070025"
    # "Ready to Ship" is still out at the galvanizer -> planning.
    assert r["shipping_status"] == "planning"


def test_azz_galv_single_line_no_quantity():
    r = classify.extract_order(_record(AZZ_GALV))
    assert len(r["lines"]) == 1
    line = r["lines"][0]
    assert line["quantity"] is None
    assert "ANGLE" in line["description"]
    assert line["finish"] == "Galvanized"


def test_azz_galv_anchors_on_customer_po_not_stray_token():
    # A decoy PO-like token must not hijack the link — only "Customer PO xxx-yyy" counts.
    payload = {
        "subject": "AZZDEN: MILE HIGH METAL WORK, 26070025, Ready to Ship",
        "body": ("order status has changed: Ready to Ship.\n"
                 "Reference 999-111 (do not use)\n"
                 "AZZ Job\n26070025\nCustomer PO\n480-913\nDescription\nANGLE\n"
                 "AZZGalvDEN@azz.com"),
        "body_content_type": "text",
    }
    rec = SimpleNamespace(id=10, source="m365_mail", payload=payload)
    r = classify.extract_order(rec)
    assert r["job"] == 480 and r["release"] == "913"
    assert r["po_number"] == "480-913"


def test_azz_galv_shipped_marks_complete():
    # A later "Shipped" notification (steel left the galvanizer) closes the item.
    payload = {
        "subject": "AZZDEN: MILE HIGH METAL WORK, 26070025, Shipped",
        "body": ("This is a notification that your order status has changed: Shipped.\n"
                 "AZZ Job\n26070025\nCustomer PO\n480-913\nDescription\nANGLE\n"
                 "AZZGalvDEN@azz.com"),
        "body_content_type": "text",
    }
    rec = SimpleNamespace(id=9, source="m365_mail", payload=payload)
    r = classify.extract_order(rec)
    assert r["order_kind"] == "galvanizing"
    assert r["shipping_status"] == "complete"


# --- DenCol stock restock (no release, no parts, ready for pickup) ---

def test_dencol_stock_routes_to_stock_extractor():
    rec = _record(DENCOL_STOCK)
    assert dencol_stock.matches(rec)


def test_dencol_stock_has_no_release_and_stock_po():
    r = classify.extract_order(_record(DENCOL_STOCK))
    assert r is not None
    assert r["supplier"] == "Dencol"
    assert r["order_kind"] == "stock"
    assert r["event_type"] == "status"
    assert r["job"] is None and r["release"] is None
    assert r["po_number"] == "Stock 7/7/26"
    # "ready for pick up" -> still to bring in -> planning.
    assert r["shipping_status"] == "planning"
    # Orderer is the internal shop foreman who placed it, not DenCol.
    assert r["ordered_by"] == "Luis Solano"
    assert len(r["lines"]) == 1 and r["lines"][0]["quantity"] is None


def test_extract_header_skips_supplier_as_orderer():
    # Guard: a supplier-domain sender is never returned as the orderer.
    payload = {
        "subject": "Re: order",
        "body": 'From: John Rendon <jrendon@dencol.com>\nSent: Mon, Jun 1, 2026\nThanks.',
        "body_content_type": "text",
    }
    header = parser.extract_header(payload)
    assert header["ordered_by"] is None
    assert header["ordered_by_email"] is None
