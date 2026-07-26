"""Persist parsed supplier orders and serve them to the release detail view.

ingest_record/ingest_unprocessed turn lake RawSourceRecords into MaterialOrder
rows (idempotent via the (source_record_id, line_index) unique key); the bb mail
poll calls ingest_unprocessed() after landing new mail, and the fixture loader
calls it directly. list_for_release / mark_received back the modal.
"""
from datetime import date, datetime

from app.logging_config import get_logger
from app.models import MaterialOrder, RawSourceRecord, Releases, db
from app.brain.material_orders.extractors.classify import extract_order

logger = get_logger(__name__)

EMAIL_RECORD_TYPE = "email"


def ingest_record(record):
    """Parse one RawSourceRecord into MaterialOrder rows. Idempotent.

    Routes the record through the extractor registry (inline body / Dencol confirm
    PDF / drawing PDF / LLM fallback). Returns the list of MaterialOrder rows for
    this record (created or existing). Skips silently (returns []) when nothing can
    recover order line items.
    """
    parsed = extract_order(record)
    if not parsed or not parsed.get("lines"):
        return []

    # The LLM fallback attaches its token usage here (deterministic extractors don't);
    # pop it now and ledger it after the order commits below.
    ai_usage_meter = parsed.pop("_ai_usage", None)

    # Surface unparseable orderers in the Render logs so future forward-chain
    # formats we can't read are visible and can be tuned (rather than failing
    # silently). The order still ingests; orderer fields are just left null.
    # Skipped for supplier status notifications (galv/stock), which have no
    # internal orderer to parse — a null there is expected, not a miss.
    if parsed.get("order_kind") in (None, "material") and not parsed.get("ordered_by"):
        logger.warning(
            "material_order_orderer_unparsed",
            source_record_id=record.id,
            po_number=parsed.get("po_number"),
            subject=(record.payload or {}).get("subject"),
        )

    # A galvanizing notification advances a SINGLE row per AZZ Job # — each new
    # status email (a different source record) upserts onto the same row rather
    # than piling up, so the shipping lane shows one galv job, not one per email.
    if parsed.get("order_kind") == "galvanizing" and parsed.get("supplier_order_no"):
        return [_upsert_galv(record, parsed)]

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
            supplier_order_no=parsed.get("supplier_order_no"),
            event_type=parsed.get("event_type"),
            order_kind=parsed.get("order_kind") or "material",
            shipping_status=parsed.get("shipping_status"),
            ordered_by=parsed.get("ordered_by"),
            ordered_by_email=parsed.get("ordered_by_email"),
            description=line.get("description"),
            quantity=line.get("quantity"),
            profile=line.get("profile"),
            gauge=line.get("gauge"),
            finish=line.get("finish"),
            dimension=line.get("dimension"),
            unit_price=line.get("unit_price"),
            extended_price=line.get("extended_price"),
            status="ordered",
            ordered_at=parsed.get("ordered_at"),
            ready_at=parsed.get("ready_at"),
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

    # Ledger the LLM-fallback spend (previously dropped). Own transaction, post-commit.
    if ai_usage_meter:
        from app.services import ai_usage
        ai_usage.record(
            "material_orders",
            model=ai_usage_meter.get("model"),
            input_tokens=ai_usage_meter.get("input_tokens") or 0,
            output_tokens=ai_usage_meter.get("output_tokens") or 0,
            entity_type="raw_source_record",
            entity_id=record.id,
        )

    return orders


def _upsert_galv(record, parsed):
    """Upsert the single MaterialOrder row for a galvanizing job (keyed on AZZ Job #).

    Successive AZZ status notifications ('Received' → 'Ready to Ship' → 'Shipped')
    advance the same row: we update the mutable status fields and re-point the row
    at the latest source record, rather than inserting one row per email.
    """
    line = parsed["lines"][0]
    existing = MaterialOrder.query.filter_by(
        supplier=parsed.get("supplier"), supplier_order_no=parsed.get("supplier_order_no")
    ).order_by(MaterialOrder.id.asc()).first()
    if existing is not None:
        existing.event_type = parsed.get("event_type")
        existing.shipping_status = parsed.get("shipping_status")
        existing.job = parsed.get("job")
        existing.release = parsed.get("release")
        existing.po_number = parsed.get("po_number")
        existing.supplier_contact = parsed.get("supplier_contact")
        existing.description = line.get("description")
        existing.finish = line.get("finish")
        existing.raw_line = line.get("raw_line")
        existing.ordered_at = parsed.get("ordered_at")
        existing.ready_at = parsed.get("ready_at")
        existing.source_record_id = record.id
        db.session.commit()
        logger.info("material_order_galv_updated", source_record_id=record.id,
                    supplier_order_no=parsed.get("supplier_order_no"),
                    shipping_status=parsed.get("shipping_status"))
        return existing

    order = MaterialOrder(
        job=parsed.get("job"),
        release=parsed.get("release"),
        supplier=parsed.get("supplier"),
        supplier_contact=parsed.get("supplier_contact"),
        po_number=parsed.get("po_number"),
        supplier_order_no=parsed.get("supplier_order_no"),
        event_type=parsed.get("event_type"),
        order_kind="galvanizing",
        shipping_status=parsed.get("shipping_status"),
        ordered_by=parsed.get("ordered_by"),
        ordered_by_email=parsed.get("ordered_by_email"),
        description=line.get("description"),
        finish=line.get("finish"),
        status="ordered",
        ordered_at=parsed.get("ordered_at"),
        ready_at=parsed.get("ready_at"),
        source=record.source,
        source_record_id=record.id,
        line_index=0,
        raw_line=line.get("raw_line"),
    )
    db.session.add(order)
    db.session.commit()
    logger.info("material_order_galv_created", source_record_id=record.id,
                supplier_order_no=parsed.get("supplier_order_no"),
                shipping_status=parsed.get("shipping_status"))
    return order


def ingest_unprocessed(limit=200):
    """Scan not-yet-scanned email RawSourceRecords once each; ingest any orders.

    Returns the count of orders created. Each record is attempted AT MOST ONCE:
    `material_order_scanned_at` is stamped after the attempt regardless of outcome,
    so a non-order email (which yields no MaterialOrder rows) is not re-sent to the
    LLM extractor on every poll — the previous "skip only records that produced an
    order" logic re-ran the Opus fallback on all non-order mail every 15 minutes.
    The marker is reset to NULL by the mail connector when a record's content
    changes (late-arriving attachment), so a changed record is scanned once more.
    """
    already = {
        rid for (rid,) in db.session.query(MaterialOrder.source_record_id)
        .filter(MaterialOrder.source_record_id.isnot(None)).distinct()
    }
    q = (
        RawSourceRecord.query
        .filter_by(record_type=EMAIL_RECORD_TYPE)
        .filter(RawSourceRecord.material_order_scanned_at.is_(None))
        .order_by(RawSourceRecord.id.desc())
        .limit(limit)
    )
    created = 0
    scanned_at = datetime.utcnow()
    for record in q:
        # Records that already produced orders (e.g. before this column existed)
        # are complete — mark them scanned without re-running the extractor.
        if record.id not in already:
            created += len(ingest_record(record))
        record.material_order_scanned_at = scanned_at
    db.session.commit()
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


def list_shipping_planning():
    """Read-model for the Timeline's Shipping Planning lane: orders still to bring in.

    An order is 'in planning' when shipping_status == 'planning' — set by the supplier-
    status extractors (DenCol stock "ready for pickup" = a PU, AZZ galv "Ready to Ship").
    This is a pure READ overlay: it never touches Releases rows; the timeline unions these
    cards onto the shipping lane alongside the release ship milestones.

    Each card carries the fields the lane needs to place + label it:
      - date: ready_at (when the supplier said it's ready) → ordered_at fallback → None
      - a short label (supplier + PO / description) and order_kind for styling.
    Sorted by date (nulls last), then id.
    """
    rows = (
        MaterialOrder.query
        .filter(MaterialOrder.shipping_status == "planning")
        .all()
    )
    cards = []
    for o in rows:
        date = o.ready_at or o.ordered_at
        cards.append({
            "id": o.id,
            "job": o.job,
            "release": o.release,
            "order_kind": o.order_kind,          # 'material' | 'galvanizing' | 'stock' (PU)
            "supplier": o.supplier,
            "po_number": o.po_number,
            "supplier_order_no": o.supplier_order_no,
            "description": o.description,
            "date": date.isoformat() if date else None,
            "ready_at": o.ready_at.isoformat() if o.ready_at else None,
            "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None,
        })
    cards.sort(key=lambda c: (c["date"] is None, c["date"] or "", c["id"]))
    return cards


def order_done(o):
    """True when an order needs no more attention.

    Galv/stock 'status orders' carry a shipping_status ('planning' → 'complete');
    plain material rows carry status ('ordered' → 'received'). Mirrors the
    green/amber badge logic in JobDetailsModal.jsx.
    """
    if o.shipping_status:
        return o.shipping_status == "complete"
    return o.status == "received"


def rollup_status(orders, overdue=False):
    """Roll a release's orders up to one status token for the Job Log indicator.

    Returns 'received' | 'pending' | 'overdue' | None:
      - None       no orders (blank, non-obtrusive indicator)
      - received   every order is done (green)
      - pending    at least one order still out (amber)
      - overdue    still out AND the release's install date has passed (red)
    """
    if not orders:
        return None
    if all(order_done(o) for o in orders):
        return "received"
    return "overdue" if overdue else "pending"


def start_install_overdue(release):
    """Hard start-install date that has already passed.

    Mirrors isHardDatePast in JobsTableRow.jsx: only a real committed date counts
    (not a formula-driven ETA, not a neutralized/no-color date, not ASAP).
    """
    if release is None or release.start_install is None:
        return False
    if release.start_install_formulaTF is not False:
        return False
    if release.start_install_no_color or release.start_install_asap:
        return False
    return release.start_install < date.today()


def status_summary():
    """Per-(job, release) material-order rollup for every release that has orders.

    Returns [{"job": int, "release": str, "status": "received|pending|overdue"}].
    Only releases WITH orders appear — the Job Log defaults everything else to
    blank. Stock/PU orders (null job/release) are skipped; they aren't tied to a
    release. Read-only: never mutates.
    """
    groups = {}
    for o in MaterialOrder.query.filter(MaterialOrder.job.isnot(None)).all():
        groups.setdefault((o.job, o.release), []).append(o)
    if not groups:
        return []

    jobs = {job for (job, _release) in groups}
    releases_by_key = {
        (r.job, r.release): r
        for r in Releases.query.filter(Releases.job.in_(jobs)).all()
    }

    summary = []
    for (job, release), orders in groups.items():
        overdue = start_install_overdue(releases_by_key.get((job, release)))
        status = rollup_status(orders, overdue=overdue)
        if status is None:
            continue
        summary.append({"job": job, "release": release, "status": status})
    return summary


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
