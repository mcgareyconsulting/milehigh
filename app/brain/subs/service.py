"""
@milehigh-header
schema_version: 1
purpose: Query and update helpers for the admin Subs installer-invoice-paid page.
exports:
  list_subs_releases: Active assigned releases, sorted by installer / job / release
  set_installer_invoice_paid: Toggle paid flag + audit event (no-op if unchanged)
imports_from: [app.models, app.services.job_event_service, app.logging_config]
imported_by: [app/brain/subs/routes.py]
invariants:
  - Only active, non-archived releases with a non-empty installer appear in the list.
  - installer_invoice_paid is independent of Releases.invoiced (customer billing).
  - No Trello / outbox / scheduling cascade.
"""
from datetime import datetime
from typing import Optional

from app.models import Releases, db
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)


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
        "installer_invoice_paid": bool(rel.installer_invoice_paid),
    }


def _active_assigned_base_query():
    """Active, non-archived releases with a non-empty installer."""
    return Releases.query.filter(
        Releases.is_archived.is_(False),
        # Treat NULL is_active as active (legacy rows).
        (Releases.is_active.is_(None)) | (Releases.is_active.is_(True)),
        Releases.installer.isnot(None),
        Releases.installer != "",
    )


def list_subs_releases(
    *,
    paid: Optional[bool] = None,
    installer: Optional[str] = None,
) -> dict:
    """Return active releases with an installer, sorted for the Subs page.

    Args:
        paid: If True/False, filter by installer_invoice_paid; None = all.
        installer: Exact installer team name filter; None = all.

    `installers` is always the full distinct set of active assigned teams so
    filter chips stay stable when paid/installer filters shrink the table.
    """
    # Stable roster for the installer dropdown (ignore paid/installer filters).
    installer_names = {
        name
        for (name,) in _active_assigned_base_query()
        .with_entities(Releases.installer)
        .distinct()
        .all()
        if name
    }

    q = _active_assigned_base_query()

    if paid is not None:
        q = q.filter(Releases.installer_invoice_paid.is_(paid))

    if installer:
        q = q.filter(Releases.installer == installer)

    rows = q.order_by(
        Releases.installer.asc(),
        Releases.job.asc(),
        Releases.release.asc(),
    ).all()

    releases = [_serialize_release(r) for r in rows]
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
    job_record = Releases.query.filter_by(job=job, release=release).first()
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
        "event_id": event.id if event else None,
        "changed": True,
    }
