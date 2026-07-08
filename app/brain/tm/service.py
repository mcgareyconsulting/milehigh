"""T&M ticket service — native mobile-creation lifecycle.

The live path is native digital creation: the field form POSTs ticket JSON, which
lands as a 'draft' (create_ticket), is edited while still a draft (update_ticket),
or discarded to 'void' (void_ticket) — rows are never deleted. Signature capture,
internal approval and the CO pipeline arrive in later phases.

The legacy-paper vision path (create_from_upload + _land_bronze, calling
app/brain/tm/extract.py) is PARKED at the bottom of this file: kept intact for a
future "photograph a paper ticket" import, but no route exposes it.
"""
from datetime import datetime

from app.models import db, Releases, TMTicket
from app.logging_config import get_logger

logger = get_logger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# Fields the creation/edit form may set. Line-item lists are stored as given (the
# form owns their shape); scalars are coerced in _apply_fields. release_id is
# handled separately because it needs FK validation.
_EDITABLE_FIELDS = (
    "job", "date_of_work", "customer", "work_description",
    "location", "gc_company", "gc_contact_name", "foreman_name",
    "labor", "materials", "equipment", "signature_present", "signature_name",
)


def _parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


def _apply_release(ticket: TMTicket, body: dict) -> str | None:
    """Validate and set release_id if present in the body. Returns an error or None."""
    if "release_id" not in body:
        return None
    release_id = body.get("release_id")
    if release_id is not None:
        if db.session.get(Releases, release_id) is None:
            return f"Release {release_id} not found"
    ticket.release_id = release_id
    return None


def _apply_fields(ticket: TMTicket, body: dict) -> str | None:
    """Coerce and set the editable scalar/line-item fields. Returns an error or None."""
    for field in _EDITABLE_FIELDS:
        if field not in body:
            continue
        value = body[field]
        if field == "date_of_work":
            try:
                value = _parse_date(value)
            except ValueError:
                return "date_of_work must be YYYY-MM-DD"
        elif field == "job":
            try:
                value = int(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return "job must be an integer"
        elif field == "signature_present":
            value = bool(value)
        elif field in ("labor", "materials", "equipment"):
            if value is not None and not isinstance(value, list):
                return f"{field} must be a list"
        setattr(ticket, field, value)
    return None


def create_ticket(body: dict, username: str) -> tuple[TMTicket | None, str | None]:
    """Create a native T&M ticket as a draft. Returns (ticket, error)."""
    ticket = TMTicket(status="draft", created_by=username)
    error = _apply_release(ticket, body) or _apply_fields(ticket, body)
    if error:
        return None, error

    db.session.add(ticket)
    db.session.commit()
    logger.info("tm_ticket_created", ticket_id=ticket.id, job=ticket.job,
                release_id=ticket.release_id, created_by=username)
    return ticket, None


def update_ticket(ticket: TMTicket, body: dict, username: str) -> tuple[TMTicket | None, str | None]:
    """Edit a draft ticket in place. Only drafts are editable. Returns (ticket, error)."""
    if ticket.status != "draft":
        return None, f"Ticket is {ticket.status}; only drafts can be edited"

    error = _apply_release(ticket, body) or _apply_fields(ticket, body)
    if error:
        return None, error

    db.session.commit()
    logger.info("tm_ticket_updated", ticket_id=ticket.id, job=ticket.job,
                release_id=ticket.release_id, updated_by=username)
    return ticket, None


def void_ticket(ticket: TMTicket, username: str) -> TMTicket:
    """Discard a ticket — the row is kept (never deleted), just marked void."""
    ticket.status = "void"
    ticket.reviewed_by = username
    ticket.reviewed_at = datetime.utcnow()
    db.session.commit()
    logger.info("tm_ticket_voided", ticket_id=ticket.id, voided_by=username)
    return ticket


def release_candidates(job) -> list:
    """Slim active releases matching a job number, for the form's release picker."""
    if job in (None, ""):
        return []
    try:
        job = int(job)
    except (TypeError, ValueError):
        return []
    rows = (
        Releases.query.filter(
            Releases.job == job,
            Releases.is_active.isnot(False),
            Releases.is_archived.is_(False),
        )
        .order_by(Releases.release)
        .all()
    )
    return [
        {"id": r.id, "job": r.job, "release": r.release,
         "job_name": r.job_name, "description": r.description}
        for r in rows
    ]


def list_tickets(status=None) -> list:
    q = TMTicket.query
    if status:
        q = q.filter(TMTicket.status == status)
    return [t.to_dict() for t in q.order_by(TMTicket.created_at.desc(), TMTicket.id.desc()).all()]


def get_ticket(ticket_id) -> TMTicket | None:
    return db.session.get(TMTicket, ticket_id)


# ---------------------------------------------------------------------------
# PARKED: legacy-paper vision ingestion.
#
# create_from_upload reads a scanned/photographed paper ticket with Claude vision
# (app/brain/tm/extract.py) and lands a draft with the extracted fields plus a
# bronze RawSourceRecord. No route currently exposes this — it is retained for a
# future "photograph a paper ticket" import feature and is only reachable via a
# direct service call (see tests/tm/test_tm_extract.py for the extractor).
# ---------------------------------------------------------------------------

import hashlib  # noqa: E402 — parked path only

from app.models import RawSourceRecord  # noqa: E402
from app.brain.tm import extract as tm_extract  # noqa: E402
from app.brain.tm import storage  # noqa: E402


def _land_bronze(data: bytes, media_type: str, filename: str, storage_key: str, username: str) -> RawSourceRecord:
    """Upsert the upload into the bronze lake table, keyed by content hash."""
    digest = hashlib.sha256(data).hexdigest()
    external_id = f"sha256:{digest}"
    record = RawSourceRecord.query.filter_by(source="upload", external_id=external_id).first()
    if record is None:
        record = RawSourceRecord(
            source="upload",
            record_type="tm_ticket_scan",
            external_id=external_id,
            content_hash=digest,
            payload={
                "filename": filename,
                "media_type": media_type,
                "storage_key": storage_key,
                "uploaded_by": username,
            },
        )
        db.session.add(record)
        db.session.flush()
    return record


def create_from_upload(data: bytes, media_type: str, filename: str, username: str) -> TMTicket:
    """PARKED. Store the document, land bronze, extract via vision, create a draft.

    Extraction failure is non-fatal: the ticket is still created blank with
    extract_error set, so the reviewer can key it in manually.
    """
    storage_key = storage.save(data, media_type)
    record = _land_bronze(data, media_type, filename, storage_key, username)

    ticket = TMTicket(
        status="draft",
        source_storage_key=storage_key,
        source_filename=filename,
        source_media_type=media_type,
        source_record_id=record.id,
        uploaded_by=username,
        extract_model=tm_extract.EXTRACT_MODEL,
    )

    try:
        result = tm_extract.extract(data, media_type)
        ticket.job = result["job"]
        ticket.date_of_work = _parse_date(result["date_of_work"])
        ticket.customer = result["customer"]
        ticket.work_description = result["work_description"]
        ticket.labor = result["labor"]
        ticket.materials = result["materials"]
        ticket.equipment = result["equipment"]
        ticket.signature_present = result["signature_present"]
        ticket.signature_name = result["signature_name"]
        ticket.raw_extraction = result["raw"]
    except Exception as e:  # noqa: BLE001 — any failure → blank ticket for manual entry
        ticket.extract_error = str(e)[:512]
        logger.error("tm_ticket_extraction_failed", filename=filename, error=str(e),
                     error_type=type(e).__name__, exc_info=True)

    db.session.add(ticket)
    db.session.commit()
    logger.info(
        "tm_ticket_created_from_upload",
        ticket_id=ticket.id,
        job=ticket.job,
        extracted=ticket.extract_error is None,
        uploaded_by=username,
    )
    return ticket
