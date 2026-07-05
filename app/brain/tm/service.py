"""T&M ticket ingestion service — upload→extract→review→confirm/reject lifecycle.

Uploads land three artifacts before extraction is even attempted, so a failed
extraction never loses anything: the original bytes (content-addressed in
storage.py), a bronze RawSourceRecord row (source='upload'), and the TMTicket
row itself. Deny moves the ticket to 'rejected' — rows are never deleted.
"""
import hashlib
from datetime import datetime

from app.models import db, RawSourceRecord, Releases, TMTicket
from app.brain.tm import extract as tm_extract
from app.brain.tm import storage
from app.logging_config import get_logger

logger = get_logger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# Fields the review modal may set on confirm. Line-item lists are stored as
# given (the modal owns their shape); scalars are coerced below.
_CONFIRMABLE_FIELDS = (
    "job", "date_of_work", "customer", "work_description",
    "labor", "materials", "equipment", "signature_present", "signature_name",
)


def _parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


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
    """Store the document, land bronze, extract via vision, create a pending ticket.

    Extraction failure is non-fatal: the ticket is still created blank with
    extract_error set, so the reviewer can key it in manually.
    """
    storage_key = storage.save(data, media_type)
    record = _land_bronze(data, media_type, filename, storage_key, username)

    ticket = TMTicket(
        status="pending_review",
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
        logger.warning("tm_ticket_extraction_failed", filename=filename, error=str(e))

    db.session.add(ticket)
    db.session.commit()
    logger.info(
        "tm_ticket_created",
        ticket_id=ticket.id,
        job=ticket.job,
        extracted=ticket.extract_error is None,
        uploaded_by=username,
    )
    return ticket


def release_candidates(job) -> list:
    """Slim active releases matching a job number, for the review modal's picker."""
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


def confirm(ticket: TMTicket, body: dict, username: str) -> tuple[TMTicket | None, str | None]:
    """Apply reviewed fields and confirm the ticket. Returns (ticket, error)."""
    if ticket.status == "rejected":
        return None, "Ticket is rejected; cannot confirm"

    if "release_id" in body:
        release_id = body.get("release_id")
        if release_id is not None:
            release = db.session.get(Releases, release_id)
            if release is None:
                return None, f"Release {release_id} not found"
        ticket.release_id = release_id

    for field in _CONFIRMABLE_FIELDS:
        if field not in body:
            continue
        value = body[field]
        if field == "date_of_work":
            try:
                value = _parse_date(value)
            except ValueError:
                return None, "date_of_work must be YYYY-MM-DD"
        elif field == "job":
            try:
                value = int(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None, "job must be an integer"
        elif field == "signature_present":
            value = bool(value)
        elif field in ("labor", "materials", "equipment"):
            if value is not None and not isinstance(value, list):
                return None, f"{field} must be a list"
        setattr(ticket, field, value)

    ticket.status = "confirmed"
    ticket.reviewed_by = username
    ticket.reviewed_at = datetime.utcnow()
    db.session.commit()
    logger.info("tm_ticket_confirmed", ticket_id=ticket.id, job=ticket.job,
                release_id=ticket.release_id, reviewed_by=username)
    return ticket, None


def reject(ticket: TMTicket, username: str) -> TMTicket:
    """Deny the extraction — the row is kept (never deleted), just marked rejected."""
    ticket.status = "rejected"
    ticket.reviewed_by = username
    ticket.reviewed_at = datetime.utcnow()
    db.session.commit()
    logger.info("tm_ticket_rejected", ticket_id=ticket.id, reviewed_by=username)
    return ticket
