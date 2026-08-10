"""
@milehigh-header
schema_version: 1
purpose: Query and update helpers for the admin Subs installer-invoice page.
exports:
  list_subs_releases: Assigned releases for Invoice Paid (active + archived-until-complete)
  set_installer_invoice_paid: Toggle paid flag + audit event (no-op if unchanged)
  set_installer_invoice_progress: Set 0–100 progress + audit event (no-op if unchanged)
  set_installer_invoice_numbers: Set multi-line invoice numbers + audit event (no-op if unchanged)
imports_from: [app.models, app.services.job_event_service, app.logging_config]
imported_by: [app/brain/subs/routes.py]
invariants:
  - Live assigned releases appear; archived assigned releases stay until invoiced complete.
  - Oscar is MHMW staff (still in INSTALLER_TEAMS for scheduling) — hidden from this tab.
  - installer_invoice_* fields are independent of Releases.invoiced (customer billing).
  - No Trello / outbox / scheduling cascade.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, and_, cast, or_

from app.models import Releases, db
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)

# Installer crews that are not subcontractors. Still valid on INSTALLER_TEAMS /
# the job log for assignment, but never shown on Subs → Invoice Paid.
_SUBS_EXCLUDED_INSTALLERS = frozenset({"oscar"})


def _is_subs_excluded_installer(name: Optional[str]) -> bool:
    if not name:
        return False
    return name.strip().casefold() in _SUBS_EXCLUDED_INSTALLERS


def _serialize_release(rel: Releases) -> dict:
    return {
        "id": rel.id,
        "job": rel.job,
        "release": rel.release,
        "job_name": rel.job_name,
        "description": rel.description,
        "installer": rel.installer,
        "stage": rel.stage,
        "start_install": rel.start_install.isoformat() if rel.start_install else None,
        "job_comp": rel.job_comp,
        "is_archived": bool(rel.is_archived),
        "installer_invoice_paid": bool(rel.installer_invoice_paid),
        "installer_invoice_progress": rel.installer_invoice_progress,
        "installer_invoice_numbers": rel.installer_invoice_numbers or "",
    }


def _has_installer_clause():
    return and_(
        Releases.installer.isnot(None),
        Releases.installer != "",
    )


def _subs_list_base_query():
    """Releases that belong on Invoice Paid.

    - Active (non-archived, not soft-deleted) with an installer, or
    - Archived with an installer and *not* yet invoiced complete (outstanding sub balance).
    """
    has_installer = _has_installer_clause()
    live = and_(
        Releases.is_archived.is_(False),
        # Treat NULL is_active as active (legacy rows).
        (Releases.is_active.is_(None)) | (Releases.is_active.is_(True)),
        has_installer,
    )
    archived_outstanding = and_(
        Releases.is_archived.is_(True),
        Releases.installer_invoice_paid.is_(False),
        has_installer,
    )
    return Releases.query.filter(or_(live, archived_outstanding))


def list_subs_releases(
    *,
    paid: Optional[bool] = None,
    installer: Optional[str] = None,
    q: Optional[str] = None,
) -> dict:
    """Return releases for the Subs Invoice Paid page.

    Args:
        paid: If True/False, filter by installer_invoice_paid; None = all.
        installer: Exact installer team name filter; None = all.
        q: Free-text search (job, release, name, description, installer, invoice #).

    `installers` is always the full distinct set of crews still on this list
    (ignoring paid/installer/q filters) so filter chips stay stable.
    """
    # Stable roster for the installer dropdown (ignore paid/installer/search filters).
    installer_names = {
        name
        for (name,) in _subs_list_base_query()
        .with_entities(Releases.installer)
        .distinct()
        .all()
        if name and not _is_subs_excluded_installer(name)
    }

    query = _subs_list_base_query()

    if paid is not None:
        query = query.filter(Releases.installer_invoice_paid.is_(paid))

    if installer:
        # Don't let a filter resurrect an excluded (non-sub) crew.
        if _is_subs_excluded_installer(installer):
            return {"releases": [], "installers": sorted(installer_names)}
        query = query.filter(Releases.installer == installer)

    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        query = query.filter(
            or_(
                cast(Releases.job, String).ilike(like),
                Releases.release.ilike(like),
                Releases.job_name.ilike(like),
                Releases.description.ilike(like),
                Releases.installer.ilike(like),
                Releases.installer_invoice_numbers.ilike(like),
            )
        )

    rows = query.order_by(
        Releases.installer.asc(),
        Releases.job.asc(),
        Releases.release.asc(),
    ).all()

    releases = [
        _serialize_release(r)
        for r in rows
        if not _is_subs_excluded_installer(r.installer)
    ]
    installers = sorted(installer_names)

    return {"releases": releases, "installers": installers}


def set_installer_invoice_paid(
    job: int,
    release: str,
    paid: bool,
    *,
    source: str = "Brain",
) -> dict:
    """Set installer_invoice_paid on a release. No-op (no event) if unchanged.

    Returns:
        dict with status, installer_invoice_paid, and optional event_id.

    Raises:
        ValueError: release not found.
    """
    job_record = Releases.resolve(job, release)
    if not job_record:
        raise ValueError(f"Job {job}-{release} not found")

    old = bool(job_record.installer_invoice_paid)
    new = bool(paid)

    if old == new:
        logger.debug(
            "installer_invoice_paid_unchanged",
            job=job,
            release=release,
            installer_invoice_paid=new,
        )
        return {
            "status": "success",
            "installer_invoice_paid": new,
            "is_archived": bool(job_record.is_archived),
            "event_id": None,
            "changed": False,
        }

    event = JobEventService.create_and_close(
        job=job,
        release=release,
        action="update_installer_invoice_paid",
        source=source,
        payload={"from": old, "to": new},
    )

    job_record.installer_invoice_paid = new
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = source
    db.session.commit()

    logger.info(
        "installer_invoice_paid_updated",
        job=job,
        release=release,
        from_value=old,
        to_value=new,
        event_id=event.id if event else None,
    )

    return {
        "status": "success",
        "installer_invoice_paid": new,
        "is_archived": bool(job_record.is_archived),
        "event_id": event.id if event else None,
        "changed": True,
    }


def _normalize_progress(raw) -> Optional[int]:
    """Coerce client value to int 0–100 or None (clear). Raises ValueError on bad input."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise ValueError("installer_invoice_progress must be an integer 0–100")
    if isinstance(raw, float):
        if not raw.is_integer():
            raise ValueError("installer_invoice_progress must be a whole number 0–100")
        value = int(raw)
    elif isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        s = raw.strip()
        if s == "":
            return None
        try:
            value = int(s)
        except ValueError as exc:
            raise ValueError("installer_invoice_progress must be an integer 0–100") from exc
    else:
        raise ValueError("installer_invoice_progress must be an integer 0–100")

    if value < 0 or value > 100:
        raise ValueError("installer_invoice_progress must be between 0 and 100")
    return value


def set_installer_invoice_progress(
    job: int,
    release: str,
    progress,
    *,
    source: str = "Brain",
) -> dict:
    """Set installer_invoice_progress (0–100 or null). No-op if unchanged.

    Raises:
        ValueError: release not found, or progress out of range / invalid.
    """
    job_record = Releases.resolve(job, release)
    if not job_record:
        raise ValueError(f"Job {job}-{release} not found")

    try:
        new = _normalize_progress(progress)
    except ValueError as exc:
        # Distinguish not-found (also ValueError) from bad payload for the route layer.
        raise ValueError(f"invalid_progress:{exc}") from exc

    old = job_record.installer_invoice_progress
    if old == new:
        logger.debug(
            "installer_invoice_progress_unchanged",
            job=job,
            release=release,
            installer_invoice_progress=new,
        )
        return {
            "status": "success",
            "installer_invoice_progress": new,
            "event_id": None,
            "changed": False,
        }

    event = JobEventService.create_and_close(
        job=job,
        release=release,
        action="update_installer_invoice_progress",
        source=source,
        payload={"from": old, "to": new},
    )

    job_record.installer_invoice_progress = new
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = source
    db.session.commit()

    logger.info(
        "installer_invoice_progress_updated",
        job=job,
        release=release,
        from_value=old,
        to_value=new,
        event_id=event.id if event else None,
    )

    return {
        "status": "success",
        "installer_invoice_progress": new,
        "event_id": event.id if event else None,
        "changed": True,
    }


def _normalize_invoice_numbers(raw) -> Optional[str]:
    """Coerce client value to stripped multi-line text or None (clear)."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("installer_invoice_numbers must be a string")
    # Preserve internal newlines; trim only ends.
    text = raw.strip()
    return text if text else None


def set_installer_invoice_numbers(
    job: int,
    release: str,
    numbers,
    *,
    source: str = "Brain",
) -> dict:
    """Set installer_invoice_numbers (multi-line text or null). No-op if unchanged.

    Raises:
        ValueError: release not found, or numbers not a string.
    """
    job_record = Releases.resolve(job, release)
    if not job_record:
        raise ValueError(f"Job {job}-{release} not found")

    try:
        new = _normalize_invoice_numbers(numbers)
    except ValueError as exc:
        raise ValueError(f"invalid_numbers:{exc}") from exc

    old = job_record.installer_invoice_numbers or None
    if old == new:
        logger.debug(
            "installer_invoice_numbers_unchanged",
            job=job,
            release=release,
        )
        return {
            "status": "success",
            "installer_invoice_numbers": new or "",
            "event_id": None,
            "changed": False,
        }

    event = JobEventService.create_and_close(
        job=job,
        release=release,
        action="update_installer_invoice_numbers",
        source=source,
        payload={"from": old, "to": new},
    )

    job_record.installer_invoice_numbers = new
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = source
    db.session.commit()

    logger.info(
        "installer_invoice_numbers_updated",
        job=job,
        release=release,
        event_id=event.id if event else None,
    )

    return {
        "status": "success",
        "installer_invoice_numbers": new or "",
        "event_id": event.id if event else None,
        "changed": True,
    }
