"""Service tests — ingest a RawSourceRecord into MaterialOrders (in-memory DB)."""
import os

from app.models import MaterialOrder, RawSourceRecord, db
from app.brain.material_orders.eml_adapter import eml_to_payload
from app.brain.material_orders import service

FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "drexel_580-659_decking_order.eml"
)
DENCOL_CONFIRM = os.path.join(
    os.path.dirname(__file__), "fixtures", "dencol_390-351_confirm.eml"
)
AZZ_GALV = os.path.join(
    os.path.dirname(__file__), "fixtures", "azz_480-913_ready_to_ship.eml"
)
DENCOL_STOCK = os.path.join(
    os.path.dirname(__file__), "fixtures", "dencol_stock_pickup.eml"
)


def _land_record(eml_path=FIXTURE, external_id=None, content_hash="hash-fixture"):
    """Insert a fixture email as a RawSourceRecord and return it."""
    payload = eml_to_payload(eml_path)
    rec = RawSourceRecord(
        source="m365_mail",
        record_type="email",
        source_account="bb@mhmw.com",
        external_id=external_id or payload["external_id"],
        content_hash=content_hash,
        payload=payload,
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def test_ingest_creates_order(app):
    with app.app_context():
        rec = _land_record()
        orders = service.ingest_record(rec)
        assert len(orders) == 1
        o = orders[0]
        assert o.job == 580 and o.release == "659"
        assert o.supplier == "Drexel Supply"
        assert o.po_number == "580-659"
        assert o.quantity == 45.0
        assert o.status == "ordered"
        assert o.source_record_id == rec.id


def test_ingest_persists_orderer(app):
    with app.app_context():
        rec = _land_record()
        o = service.ingest_record(rec)[0]
        assert o.ordered_by == "Rourke Alvarado"
        assert o.ordered_by_email == "ralvarado@mhmw.com"
        assert str(o.ordered_at) == "2026-06-15"


def test_ingest_logs_when_orderer_unparsed(app, monkeypatch):
    """An order with no parseable orderer still ingests but logs a warning."""
    warnings = []
    monkeypatch.setattr(
        service.logger, "warning",
        lambda event, **kw: warnings.append((event, kw)),
    )
    with app.app_context():
        payload = {
            "subject": "580-661 Decking Order",
            "from": {"name": "Someone", "address": "someone@example.com"},
            "sent_at": "2026-06-16T07:41:28+00:00",
            "body": "Please use PO# 580-661\nQty (10) 1.5C 18Ga. Galvanized Decking @ 48\"",
            "body_content_type": "text",
        }
        rec = RawSourceRecord(
            source="m365_mail", record_type="email", source_account="bb@mhmw.com",
            external_id="no-forward", content_hash="hash-noforward", payload=payload,
        )
        db.session.add(rec)
        db.session.commit()

        orders = service.ingest_record(rec)
        assert len(orders) == 1
        assert orders[0].ordered_by is None
        assert any(e == "material_order_orderer_unparsed" for e, _ in warnings)


def test_ingest_is_idempotent(app):
    with app.app_context():
        rec = _land_record()
        service.ingest_record(rec)
        service.ingest_record(rec)  # second pass must not duplicate
        assert MaterialOrder.query.count() == 1


def test_list_for_release(app):
    with app.app_context():
        rec = _land_record()
        service.ingest_record(rec)
        rows = service.list_for_release(580, "659")
        assert len(rows) == 1
        assert rows[0]["description"].startswith("1.5C")
        # Wrong release returns nothing.
        assert service.list_for_release(580, "999") == []


def test_mark_received(app):
    with app.app_context():
        rec = _land_record()
        order = service.ingest_record(rec)[0]
        result = service.mark_received(order.id)
        assert result["status"] == "received"
        assert result["received_at"] is not None
        # Un-receive.
        result = service.mark_received(order.id, received=False)
        assert result["status"] == "ordered"
        assert result["received_at"] is None


def test_ingest_dencol_confirm_from_pdf(app):
    """The Dencol ORDER CONFIRM PDF ingests its 4 priced lines, tagged confirmed."""
    with app.app_context():
        rec = _land_record(DENCOL_CONFIRM, external_id="dencol-390-351", content_hash="h1")
        orders = service.ingest_record(rec)
        assert len(orders) == 4
        o = orders[0]
        assert o.job == 390 and o.release == "351"
        assert o.supplier == "Dencol"
        assert o.event_type == "confirmed"
        assert o.supplier_order_no == "2296464"
        assert o.ordered_by == "David Servold"  # not the supplier (John Rendon)
        assert o.unit_price == 30.50 and o.extended_price == 61.00
        # Idempotent re-ingest.
        service.ingest_record(rec)
        assert MaterialOrder.query.filter_by(source_record_id=rec.id).count() == 4


def test_ingest_galv_status_notification(app):
    """An AZZ galv notification lands one status row keyed to the linked release."""
    with app.app_context():
        rec = _land_record(AZZ_GALV, external_id="azz-1", content_hash="hg1")
        orders = service.ingest_record(rec)
        assert len(orders) == 1
        o = orders[0]
        assert o.order_kind == "galvanizing"
        assert o.supplier == "AZZ Galvanizing"
        assert o.supplier_order_no == "26070025"
        assert o.job == 480 and o.release == "913"
        assert o.shipping_status == "planning"
        assert o.quantity is None


def test_galv_upserts_single_row_across_notifications(app):
    """A second notification for the same AZZ Job # advances the same row."""
    with app.app_context():
        rec1 = _land_record(AZZ_GALV, external_id="azz-1", content_hash="hg1")
        first = service.ingest_record(rec1)[0]
        assert first.shipping_status == "planning"

        # A later "Shipped" notification — different email, same AZZ Job #.
        shipped = eml_to_payload(AZZ_GALV)
        shipped["subject"] = "AZZDEN: MILE HIGH METAL WORK, 26070025, Shipped"
        shipped["body"] = shipped["body"].replace("Ready to Ship", "Shipped")
        rec2 = RawSourceRecord(
            source="m365_mail", record_type="email", source_account="bb@mhmw.com",
            external_id="azz-2", content_hash="hg2", payload=shipped,
        )
        db.session.add(rec2)
        db.session.commit()

        second = service.ingest_record(rec2)[0]
        # Same row, advanced to complete, re-pointed at the latest record.
        assert MaterialOrder.query.filter_by(order_kind="galvanizing").count() == 1
        assert second.id == first.id
        assert second.shipping_status == "complete"
        assert second.source_record_id == rec2.id


def test_ingest_stock_order_has_no_release(app):
    """A DenCol stock restock lands one release-less status row for shipping planning."""
    with app.app_context():
        rec = _land_record(DENCOL_STOCK, external_id="stock-1", content_hash="hs1")
        orders = service.ingest_record(rec)
        assert len(orders) == 1
        o = orders[0]
        assert o.order_kind == "stock"
        assert o.supplier == "Dencol"
        assert o.job is None and o.release is None
        assert o.po_number == "Stock 7/7/26"
        assert o.shipping_status == "planning"
        assert o.ordered_by == "Luis Solano"
        # ordered_at = Luis's order (7/7); ready_at = DenCol's ready-for-pickup reply (7/9).
        assert str(o.ordered_at) == "2026-07-07"
        assert str(o.ready_at) == "2026-07-09"


def test_ingest_unprocessed_picks_up_new_records(app):
    with app.app_context():
        _land_record()
        created = service.ingest_unprocessed()
        assert created == 1
        # Running again finds nothing new.
        assert service.ingest_unprocessed() == 0
