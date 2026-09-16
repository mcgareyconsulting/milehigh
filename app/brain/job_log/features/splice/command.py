"""
Release splicing (T9): "340.1", "340.2" child releases that carry install hours only.

Rules (Bill, 2026-09-15 — supersedes the 2026-09-02 mirror-card shape):
  - A splice is a first-class job-log row numbered ``<parent release>.<n>``.
  - The parent carries fabrication and the TOTAL install-hour pool. Every splice
    draws from that pool; the sum of active splices' install hours never exceeds it.
  - A splice carries no fab hours.
  - A splice is created only from its parent (+ Splice). Free-typing a dotted
    release number through the paste / verbal path is rejected, so a splice can
    never exist without a parent row.
  - Zero Trello interaction: no card, no outbox item, no mirror. Every command that
    pushes to Trello already guards on ``trello_card_id``, which a splice never has.
  - Starts in ``Released`` like any other release (start stage to be confirmed).
"""
import re
from datetime import date, datetime

from app.api.helpers import DEFAULT_FAB_ORDER
from app.logging_config import get_logger
from app.models import Releases, ReleaseEvents, db
from app.services.job_event_service import JobEventService

logger = get_logger(__name__)

# "<base>.<n>" — base is the parent's release number (digits), n a positive integer.
SPLICE_NUMBER_RE = re.compile(r"^(\d+)\.(\d+)$")


class SpliceError(ValueError):
    """Client-correctable splice violation. ``status`` is the HTTP code to return."""

    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


def parse_splice_number(release):
    """Return (base, n) for a dotted release number, else None."""
    m = SPLICE_NUMBER_RE.match(str(release or "").strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def is_splice_number(release):
    return parse_splice_number(release) is not None


def _live(row):
    """Active + not archived + not soft-deleted (NULL is_active counts as active)."""
    return row.is_active is not False and not row.is_archived


def splice_children(parent, include_dead=False):
    """Child rows linked by parent_release_id, oldest first."""
    rows = (
        Releases.query.filter_by(parent_release_id=parent.id)
        .order_by(Releases.id.asc())
        .all()
    )
    if include_dead:
        return rows
    return [r for r in rows if _live(r)]


def install_pool(parent, exclude_id=None):
    """Install-hour pool on ``parent``: (total, allocated, remaining).

    ``allocated`` sums the install hours of live splices (optionally excluding one,
    so an edit to that splice can be checked against the pool it will re-enter).
    ``total`` is None when the parent has no install hours yet — no pool to draw on.
    """
    total = parent.install_hrs
    allocated = 0.0
    for child in splice_children(parent):
        if exclude_id is not None and child.id == exclude_id:
            continue
        allocated += float(child.install_hrs or 0)
    remaining = None if total is None else round(float(total) - allocated, 4)
    return total, allocated, remaining


def next_splice_number(parent):
    """``<parent.release>.<n>`` where n is one past the highest suffix ever used
    under this parent (dead splices included, so a number is never re-issued)."""
    highest = 0
    for child in splice_children(parent, include_dead=True):
        parsed = parse_splice_number(child.release)
        if parsed and parsed[0] == str(parent.release):
            highest = max(highest, parsed[1])
    return f"{parent.release}.{highest + 1}"


def _coerce_hours(value, label):
    if value is None or str(value).strip() == "":
        raise SpliceError(f"{label} is required")
    try:
        hrs = float(value)
    except (TypeError, ValueError):
        raise SpliceError(f"{label} must be a number")
    if hrs != hrs or hrs <= 0:  # NaN or non-positive
        raise SpliceError(f"{label} must be greater than 0")
    return hrs


def pool_summary(parent):
    total, allocated, remaining = install_pool(parent)
    return {
        "parent_id": parent.id,
        "job": parent.job,
        "release": parent.release,
        "total_install_hrs": total,
        "allocated_install_hrs": allocated,
        "remaining_install_hrs": remaining,
        "next_splice_number": next_splice_number(parent),
        "splices": [
            {
                "id": c.id,
                "job": c.job,
                "release": c.release,
                "description": c.description,
                "install_hrs": c.install_hrs,
                "stage": c.stage,
                "released": c.released.isoformat() if c.released else None,
                "job_comp": c.job_comp,
                "installer": c.installer,
                "start_install": c.start_install.isoformat() if c.start_install else None,
            }
            for c in splice_children(parent)
        ],
    }


class CreateSpliceCommand:
    """Create one splice under ``parent``. Commits on success; raises SpliceError
    (no writes) on a rule violation."""

    def __init__(self, parent, install_hrs, description=None, released=None, user=None):
        self.parent = parent
        self.install_hrs_raw = install_hrs
        self.description = description
        self.released = released
        self.user = user

    def execute(self):
        parent = self.parent
        if parent.parent_release_id is not None:
            raise SpliceError(
                f"{parent.job}-{parent.release} is itself a splice; splice from the original release",
                status=409,
            )
        if not _live(parent):
            raise SpliceError("Cannot splice an archived or deleted release", status=409)
        if not str(parent.release or "").strip().isdigit():
            raise SpliceError(
                f"Release {parent.release} is not numeric; splicing needs a numeric parent number",
                status=409,
            )

        install_hrs = _coerce_hours(self.install_hrs_raw, "Install hours")
        total, allocated, remaining = install_pool(parent)
        if total is None:
            raise SpliceError(
                f"Set install hours on {parent.job}-{parent.release} first — a splice draws from that pool",
                status=409,
            )
        if install_hrs > remaining + 1e-9:
            raise SpliceError(
                f"Only {remaining:g} of {total:g} install hours remain on "
                f"{parent.job}-{parent.release} ({allocated:g} already spliced)",
                status=409,
                total_install_hrs=total,
                allocated_install_hrs=allocated,
                remaining_install_hrs=remaining,
            )

        release_number = next_splice_number(parent)
        released = self.released
        if isinstance(released, str) and released.strip():
            released = datetime.strptime(released.strip(), "%Y-%m-%d").date()
        elif not released:
            released = date.today()

        description = self.description
        if description is None or str(description).strip() == "":
            description = parent.description
        description = (str(description).strip() or None) if description else None
        if description and len(description) > 256:
            description = description[:253] + "..."

        payload = {
            "Job #": parent.job,
            "Release #": release_number,
            "Job": parent.job_name,
            "Description": description,
            "Fab Hrs": None,
            "Install HRS": install_hrs,
            "Paint color": parent.paint_color,
            "PM": parent.pm,
            "BY": parent.by,
            "Released": released.isoformat(),
            "Fab Order": None,
            "release_tag": parent.release_tag,
            "splice": True,
            "parent_release_id": parent.id,
            "parent_release": f"{parent.job}-{parent.release}",
            "pool": {
                "total_install_hrs": total,
                "allocated_before": allocated,
                "remaining_after": round(remaining - install_hrs, 4),
            },
        }

        splice = Releases(
            job=parent.job,
            release=release_number,
            job_name=parent.job_name,
            description=description,
            fab_hrs=None,
            install_hrs=install_hrs,
            paint_color=parent.paint_color,
            pm=parent.pm,
            by=parent.by,
            released=released,
            fab_order=DEFAULT_FAB_ORDER,
            stage="Released",
            stage_group="FABRICATION",
            release_tag=parent.release_tag,
            parent_release_id=parent.id,
            last_updated_at=datetime.utcnow(),
            source_of_update="Brain",
        )
        db.session.add(splice)

        # Deliberately NOT queued to the Trello outbox: splices have no card.
        event = JobEventService.create(
            job=parent.job,
            release=release_number,
            action="created",
            source="Brain",
            payload=payload,
            internal_user_id=self.user.id if self.user else None,
        )
        if event:
            JobEventService.close(event.id)
        db.session.commit()

        logger.info(
            "release_spliced",
            job=parent.job,
            release=release_number,
            parent_release=parent.release,
            parent_id=parent.id,
            install_hrs=install_hrs,
            remaining_install_hrs=round(remaining - install_hrs, 4),
            user_id=self.user.id if self.user else None,
        )
        return splice


def validate_field_edits(job_record, coerced):
    """Guard the PATCH field-edit path against breaking a splice link or its pool.

    ``coerced`` maps field -> (db_field, new_value) as built by update_job_fields.
    Raises SpliceError; the caller turns it into a 4xx. No writes here.
    """
    is_splice = job_record.parent_release_id is not None
    children = [] if is_splice else splice_children(job_record)

    if "release" in coerced:
        new_release = str(coerced["release"][1] or "").strip()
        if new_release != str(job_record.release):
            if is_splice:
                raise SpliceError("A splice's release number is derived from its parent and cannot be edited")
            if is_splice_number(new_release):
                raise SpliceError(
                    "Dotted release numbers are reserved for splices — use + Splice on the original release"
                )
            if children:
                raise SpliceError(
                    f"{job_record.job}-{job_record.release} has {len(children)} splice(s) numbered from it; "
                    "the release number cannot change while they exist",
                    status=409,
                )
    if "job" in coerced and (is_splice or children):
        if coerced["job"][1] != job_record.job:
            raise SpliceError("Job # cannot change on a release that is part of a splice group", status=409)

    if is_splice:
        if "fab_hrs" in coerced:
            v = coerced["fab_hrs"][1]
            if v is not None and float(v) != 0:
                raise SpliceError("A splice carries install hours only — fab hours stay on the original release")
        if "install_hrs" in coerced:
            parent = Releases.query.get(job_record.parent_release_id)
            new_hrs = coerced["install_hrs"][1]
            if new_hrs is None or float(new_hrs) <= 0:
                raise SpliceError("A splice must carry install hours greater than 0")
            if parent is not None:
                total, allocated, remaining = install_pool(parent, exclude_id=job_record.id)
                if total is not None and float(new_hrs) > remaining + 1e-9:
                    raise SpliceError(
                        f"Only {remaining:g} of {total:g} install hours remain on "
                        f"{parent.job}-{parent.release} for this splice ({allocated:g} on other splices)",
                        status=409,
                        total_install_hrs=total,
                        allocated_install_hrs=allocated,
                        remaining_install_hrs=remaining,
                    )
    elif children and "install_hrs" in coerced:
        total, allocated, _ = install_pool(job_record)
        new_total = coerced["install_hrs"][1]
        if new_total is None or float(new_total) + 1e-9 < allocated:
            raise SpliceError(
                f"{allocated:g} install hours are already spliced off {job_record.job}-{job_record.release}; "
                f"the total cannot drop below that",
                status=409,
                allocated_install_hrs=allocated,
            )
