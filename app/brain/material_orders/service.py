"""Persist parsed supplier orders and serve them to the release detail view.

ingest_record/ingest_unprocessed turn lake RawSourceRecords into MaterialOrder
rows (idempotent via the (source_record_id, line_index) unique key); the bb mail
poll calls ingest_unprocessed() after landing new mail, and the fixture loader
calls it directly. list_for_release / mark_received back the modal.
"""
from datetime import date

from app.logging_config import get_logger
from app.models import MaterialOrder, RawSourceRecord, db
from app.brain.material_orders.parser import parse_order_email

logger = get_logger(__name__)

EMAIL_RECORD_TYPE = "email"


def ingest_record(record):
    """Parse one RawSourceRecord into MaterialOrder rows. Idempotent.

    Returns the list of MaterialOrder rows for this record (created or existing).
    Skips silently (returns []) when the email isn't a recognizable order.
    """
    parsed = parse_order_email(record.payload or {})
    if not parsed or not parsed.get("lines"):
        return []

    orders = []
    for line in parsed["lines"]:
        existing = MaterialOrder.query.filter_by(
            source_record_id=record.id, line_index=line["line_index"]
        ).first()
        if existing:
            orders.append(existing)
            continue
        order = MaterialOrder(
            job=parsed.get("job"),
            release=parsed.get("release"),
            supplier=parsed.get("supplier"),
            supplier_contact=parsed.get("supplier_contact"),
            po_number=parsed.get("po_number"),
            description=line.get("description"),
            quantity=line.get("quantity"),
            profile=line.get("profile"),
            gauge=line.get("gauge"),
            finish=line.get("finish"),
            dimension=line.get("dimension"),
            status="ordered",
            ordered_at=parsed.get("ordered_at"),
            source=record.source,
            source_record_id=record.id,
            line_index=line["line_index"],
            raw_line=line.get("raw_line"),
        )
        db.session.add(order)
        orders.append(order)

    db.session.commit()
    logger.info(
        "material_order_ingested",
        source_record_id=record.id,
        job=parsed.get("job"),
        release=parsed.get("release"),
        supplier=parsed.get("supplier"),
        lines=len(parsed["lines"]),
    )
    return orders


def ingest_unprocessed(limit=200):
    """Scan recent email RawSourceRecords with no MaterialOrder yet; ingest them.

    Returns the count of orders created. Idempotent — records already turned into
    orders are skipped via a NOT-EXISTS check on source_record_id.
    """
    already = {
        rid for (rid,) in db.session.query(MaterialOrder.source_record_id)
        .filter(MaterialOrder.source_record_id.isnot(None)).distinct()
    }
    q = (
        RawSourceRecord.query
        .filter_by(record_type=EMAIL_RECORD_TYPE)
        .order_by(RawSourceRecord.id.desc())
        .limit(limit)
    )
    created = 0
    for record in q:
        if record.id in already:
            continue
        created += len(ingest_record(record))
    if created:
        logger.info("material_orders_backfill", created=created)
    return created


def list_for_release(job, release=None):
    """Material orders for a job (optionally narrowed to a release), newest first."""
    q = MaterialOrder.query
    if job is not None:
        q = q.filter(MaterialOrder.job == int(job))
    if release:
        q = q.filter(MaterialOrder.release == str(release))
    return [o.to_dict() for o in q.order_by(MaterialOrder.id.desc()).all()]


def mark_received(order_id, received=True):
    """Flip an order between ordered/received. Returns the dict or None if missing."""
    order = MaterialOrder.query.get(order_id)
    if order is None:
        return None
    if received:
        order.status = "received"
        order.received_at = date.today()
    else:
        order.status = "ordered"
        order.received_at = None
    db.session.commit()
    return order.to_dict()
