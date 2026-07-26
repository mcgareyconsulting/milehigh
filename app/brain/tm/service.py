"""T&M ticket service — native mobile-creation lifecycle.

The live path is native digital creation: the field form POSTs ticket JSON, which
lands as a 'draft' (create_ticket), is edited while still a draft (update_ticket),
or discarded to 'void' (void_ticket) — rows are never deleted. Signature capture,
internal approval and the CO pipeline arrive in later phases.
"""
from datetime import datetime

from app.models import db, Releases, TMTicket
from app.logging_config import get_logger

logger = get_logger(__name__)

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


def submit_ticket(ticket: TMTicket, actor: str) -> tuple[TMTicket | None, str | None]:
    """Hand a filled-out draft back to the originator to confirm. draft-only,
    mirrors void_ticket's shape. `actor` identifies whoever submitted it —
    a plain username for an admin, or f"subcontractor:{id}:{email}" when
    called from the subcontractor-facing route — reusing the existing
    `reviewed_by` free-text column rather than adding a second actor column.
    """
    if ticket.status != "draft":
        return None, f"Ticket is {ticket.status}; only a draft can be submitted"
    ticket.status = "submitted"
    ticket.reviewed_by = actor
    ticket.reviewed_at = datetime.utcnow()
    db.session.commit()
    logger.info("tm_ticket_submitted", ticket_id=ticket.id, submitted_by=actor)
    return ticket, None


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
