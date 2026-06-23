"""Service tests — ingest a RawSourceRecord into MaterialOrders (in-memory DB)."""
import os

from app.models import MaterialOrder, RawSourceRecord, db
from app.brain.material_orders.eml_adapter import eml_to_payload
from app.brain.material_orders import service

FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "drexel_580-659_decking_order.eml"
)


def _land_record():
    """Insert the fixture email as a RawSourceRecord and return it."""
    payload = eml_to_payload(FIXTURE)
    rec = RawSourceRecord(
        source="m365_mail",
        record_type="email",
        source_account="bb@mhmw.com",
        external_id=payload["external_id"],
        content_hash="hash-fixture",
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


def test_ingest_unprocessed_picks_up_new_records(app):
    with app.app_context():
        _land_record()
        created = service.ingest_unprocessed()
        assert created == 1
        # Running again finds nothing new.
        assert service.ingest_unprocessed() == 0
