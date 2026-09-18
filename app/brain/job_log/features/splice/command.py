"""
Release splicing (T9): "340.1", "340.2" child releases that carry install hours only.

Rules (Bill, 2026-09-15 — supersedes the 2026-09-02 mirror-card shape):
  - A splice is a first-class job-log row numbered ``<parent release>.<n>``.
  - The parent carries fabrication and the TOTAL install-hour pool. Every splice
    draws from that pool; the sum of active splices' install hours never exceeds it.
  - A splice carries no fab hours.
  - The parent keeps the WHOLE pool in ``install_hrs``; the hours a splice drew are not
    subtracted from it, or the pool would shrink every time it was drawn on. So every
    view that shows a release's install hours shows what it still installs itself —
    150 total with 50 spliced reads as 100 on the original — via ``install_hours_view``
    below. ``install_hrs`` stays the total everywhere it is written or edited.
  - A splice is created only from its parent (+ Splice). Free-typing a dotted
    release number through the paste / verbal path is rejected, so a splice can
    never exist without a parent row.
  - Zero Trello interaction: no card, no outbox item, no mirror. Every command that
    pushes to Trello already guards on ``trello_card_id``, which a splice never has.
  - Starts in ``Released`` like any other release (start stage to be confirmed).

Splice modal spec (Bill, 2026-09-16):
  - The splice's description is REQUIRED and must differ from the parent's, so a
    group never reads as "what's this splice, what's this splice".
  - Installer is required; stage (default Released) and a hard start install date
    are chosen on create.
  - Budget install hours come out of the parent's pool. ADDITIONAL install hours come
    from outside it and require a note saying why. ``install_hrs`` on the splice is
    the total (budget + additional) because it drives comp_eta everywhere;
    ``additional_install_hrs`` is the part that never counted against the pool.
"""
import re
from datetime import date, datetime

from app.api.helpers import DEFAULT_FAB_ORDER, _normalize_stage, get_stage_group_from_stage
from app.brain.job_log.features.fab_order.tier import apply_fab_order_for_stage
from app.brain.job_log.features.start_install.neutralize_install_date_cascade import (
    COLOR_DUMP_STAGES,
)
from app.brain.job_log.scheduling.calculator import calculate_install_complete_date
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


def budget_hours(row):
    """Install hours a splice draws from its parent's pool: its total minus the
    additional hours that came from outside the pool (never below zero)."""
    total = float(row.install_hrs or 0)
    extra = float(row.additional_install_hrs or 0)
    return max(total - extra, 0.0)


def _norm_text(value):
    return " ".join(str(value or "").split()).casefold()


def install_pool(parent, exclude_id=None):
    """Install-hour pool on ``parent``: (total, allocated, remaining).

    ``allocated`` sums the BUDGET install hours of live splices (optionally excluding one,
    so an edit to that splice can be checked against the pool it will re-enter).
    ``total`` is None when the parent has no install hours yet — no pool to draw on.
    """
    total = parent.install_hrs
    allocated = 0.0
    for child in splice_children(parent):
        if exclude_id is not None and child.id == exclude_id:
            continue
        allocated += budget_hours(child)
    remaining = None if total is None else round(float(total) - allocated, 4)
    return total, allocated, remaining


def splice_allocations(parent_ids=None):
    """``{parent release id: BUDGET install hours its live splices drew}``.

    One query for a whole page of releases, so a list view never goes N+1 asking each
    row whether it has splices. Parents with nothing spliced off them are absent, so
    ``.get(row.id)`` reads as "this row still carries all of its install hours".
    """
    query = Releases.query.filter(Releases.parent_release_id.isnot(None))
    if parent_ids is not None:
        ids = sorted({i for i in parent_ids if i is not None})
        if not ids:
            return {}
        query = query.filter(Releases.parent_release_id.in_(ids))
    totals = {}
    for child in query.all():
        if not _live(child):
            continue
        totals[child.parent_release_id] = totals.get(child.parent_release_id, 0.0) + budget_hours(child)
    return {pid: round(hrs, 4) for pid, hrs in totals.items() if hrs > 0}


def install_hours_view(row, allocated):
    """``(spliced, remaining)`` install hours for one release row.

    ``spliced`` is what live splices drew out of the row's pool; ``remaining`` is what
    the row itself still installs (its total minus that). Both are None when nothing was
    spliced off it — the caller then shows the row's own ``install_hrs`` unchanged.

    This is the one place the "150 total, 50 spliced, 100 left on the original" reading
    is defined; every view that shows a release's install hours derives from it.
    """
    if not allocated:
        return None, None
    total = row.install_hrs
    if total is None:
        # No pool to draw on (budget hours are refused without one), so nothing to net out.
        return allocated, None
    return allocated, max(round(float(total) - allocated, 4), 0.0)


def next_splice_number(parent):
    """``<parent.release>.<n>`` where n is one past the highest suffix ever used
    under this parent (dead splices included, so a number is never re-issued)."""
    highest = 0
    for child in splice_children(parent, include_dead=True):
        parsed = parse_splice_number(child.release)
        if parsed and parsed[0] == str(parent.release):
            highest = max(highest, parsed[1])
    return f"{parent.release}.{highest + 1}"


def _coerce_hours(value, label, allow_blank=False):
    """Positive hours. With ``allow_blank``, blank/None/0 reads as 0 (not given)."""
    if value is None or str(value).strip() == "":
        if allow_blank:
            return 0.0
        raise SpliceError(f"{label} is required")
    try:
        hrs = float(value)
    except (TypeError, ValueError):
        raise SpliceError(f"{label} must be a number")
    if hrs != hrs or hrs < 0 or (hrs == 0 and not allow_blank):  # NaN, negative, or a required 0
        raise SpliceError(f"{label} must be greater than 0")
    return hrs


def pool_summary(parent):
    total, allocated, remaining = install_pool(parent)
    children = splice_children(parent)
    # Hours outside the pool, and the whole group's install hours (pool + those).
    # Owned here, not in the client: the Splices tab's bar, ledger and subtotal all
    # read these, and the tab must never add up a split the server defines.
    additional = round(sum(float(c.additional_install_hrs or 0) for c in children), 4)
    group_total = round(float(total or 0) + additional, 4) if (total is not None or additional) else None
    return {
        "parent_id": parent.id,
        "job": parent.job,
        "release": parent.release,
        "total_install_hrs": total,
        "allocated_install_hrs": allocated,
        "remaining_install_hrs": remaining,
        "additional_install_hrs": additional,
        "group_install_hrs": group_total,
        "next_splice_number": next_splice_number(parent),
        "parent": {
            "id": parent.id,
            "job": parent.job,
            "release": parent.release,
            "job_name": parent.job_name,
            "description": parent.description,
            "stage": parent.stage,
            "installer": parent.installer,
            "install_hrs": parent.install_hrs,
            "fab_hrs": parent.fab_hrs,
        },
        "splices": [
            {
                "id": c.id,
                "job": c.job,
                "release": c.release,
                "description": c.description,
                "install_hrs": c.install_hrs,
                "budget_install_hrs": budget_hours(c),
                "additional_install_hrs": c.additional_install_hrs,
                "additional_install_note": c.additional_install_note,
                "stage": c.stage,
                "released": c.released.isoformat() if c.released else None,
                "job_comp": c.job_comp,
                "installer": c.installer,
                "start_install": c.start_install.isoformat() if c.start_install else None,
            }
            for c in children
        ],
    }


class CreateSpliceCommand:
    """Create one splice under ``parent``. Commits on success; raises SpliceError
    (no writes) on a rule violation."""

    def __init__(
        self,
        parent,
        install_hrs,
        description=None,
        released=None,
        user=None,
        stage=None,
        installer=None,
        start_install=None,
        additional_install_hrs=None,
        additional_install_note=None,
    ):
        self.parent = parent
        self.install_hrs_raw = install_hrs
        self.description = description
        self.released = released
        self.user = user
        self.stage = stage
        self.installer = installer
        self.start_install = start_install
        self.additional_install_hrs_raw = additional_install_hrs
        self.additional_install_note = additional_install_note

    @staticmethod
    def _parse_date(value, label):
        if isinstance(value, date):
            return value
        if value is None or str(value).strip() == "":
            return None
        try:
            return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
        except ValueError:
            raise SpliceError(f"{label} must be a date (YYYY-MM-DD)")

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

        # Description: required, and it must say something the original's does not.
        description = " ".join(str(self.description or "").split())
        if not description:
            raise SpliceError("Description is required — say what this splice covers")
        if _norm_text(description) == _norm_text(parent.description):
            raise SpliceError(
                "The splice's description must differ from the original's — say what this splice covers"
            )
        if len(description) > 256:
            raise SpliceError("Description must be 256 characters or fewer")

        installer = str(self.installer or "").strip()
        if not installer:
            raise SpliceError("Installer is required")

        stage = "Released"
        if self.stage is not None and str(self.stage).strip():
            stage = _normalize_stage(str(self.stage).strip())
            if stage is None:
                raise SpliceError(f"Unknown stage '{self.stage}'")

        start_install = self._parse_date(self.start_install, "Start install")

        # Hours: budget from the pool, additional from outside it (with a reason).
        budget_hrs = _coerce_hours(self.install_hrs_raw, "Budget install hours", allow_blank=True)
        additional_hrs = _coerce_hours(
            self.additional_install_hrs_raw, "Additional install hours", allow_blank=True
        )
        additional_note = " ".join(str(self.additional_install_note or "").split()) or None
        if additional_hrs > 0 and not additional_note:
            raise SpliceError("Explain why additional install hours are needed")
        if additional_hrs == 0:
            additional_note = None
        if budget_hrs <= 0 and additional_hrs <= 0:
            raise SpliceError("Budget install hours must be greater than 0")

        total, allocated, remaining = install_pool(parent)
        if budget_hrs > 0:
            if total is None:
                raise SpliceError(
                    f"Set install hours on {parent.job}-{parent.release} first — budget hours draw from that pool",
                    status=409,
                )
            if budget_hrs > remaining + 1e-9:
                raise SpliceError(
                    f"Only {remaining:g} of {total:g} install hours remain on "
                    f"{parent.job}-{parent.release} ({allocated:g} already spliced). "
                    "Hours beyond the budget go in Additional install hours.",
                    status=409,
                    total_install_hrs=total,
                    allocated_install_hrs=allocated,
                    remaining_install_hrs=remaining,
                )
        install_hrs = round(budget_hrs + additional_hrs, 4)

        release_number = next_splice_number(parent)
        released = self._parse_date(self.released, "Released") or date.today()
        stage_group = get_stage_group_from_stage(stage)

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
            "Stage": stage,
            "installer": installer,
            "Start install": start_install.isoformat() if start_install else None,
            "release_tag": parent.release_tag,
            "splice": True,
            "parent_release_id": parent.id,
            "parent_release": f"{parent.job}-{parent.release}",
            "budget_install_hrs": budget_hrs,
            "additional_install_hrs": additional_hrs or None,
            "additional_install_note": additional_note,
            "pool": {
                "total_install_hrs": total,
                "allocated_before": allocated,
                "remaining_after": None if remaining is None else round(remaining - budget_hrs, 4),
            },
        }

        splice = Releases(
            job=parent.job,
            release=release_number,
            job_name=parent.job_name,
            description=description,
            fab_hrs=None,
            install_hrs=install_hrs,
            additional_install_hrs=additional_hrs or None,
            additional_install_note=additional_note,
            paint_color=parent.paint_color,
            pm=parent.pm,
            by=parent.by,
            released=released,
            fab_order=DEFAULT_FAB_ORDER,
            stage=stage,
            stage_group=stage_group,
            installer=installer,
            release_tag=parent.release_tag,
            parent_release_id=parent.id,
            last_updated_at=datetime.utcnow(),
            source_of_update="Brain",
        )
        if stage in ("Install Complete", "Complete"):
            splice.job_comp = "X"
        if start_install is not None:
            # A hard date, exactly as UpdateStartInstallCommand writes one.
            splice.start_install = start_install
            splice.start_install_formula = None
            splice.start_install_formulaTF = False
            splice.start_install_no_color = stage in COLOR_DUMP_STAGES
            splice.comp_eta = calculate_install_complete_date(start_install, install_hrs, None)
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
        # Same tiering a stage move applies (Complete -> NULL, ship stages -> fixed tiers).
        apply_fab_order_for_stage(
            splice,
            stage,
            None,
            source="Brain",
            parent_event_id=event.id if event else None,
            stage_reason="splice_created",
        )
        db.session.commit()

        logger.info(
            "release_spliced",
            job=parent.job,
            release=release_number,
            parent_release=parent.release,
            parent_id=parent.id,
            install_hrs=install_hrs,
            budget_install_hrs=budget_hrs,
            additional_install_hrs=additional_hrs,
            stage=stage,
            installer=installer,
            remaining_install_hrs=None if remaining is None else round(remaining - budget_hrs, 4),
            user_id=self.user.id if self.user else None,
        )
        return splice


class UpdateSpliceAdditionalHoursCommand:
    """Change a splice's additional install hours (the part outside the parent's pool).

    Budget hours stay as they are, so the splice's total install hours move by the
    difference and comp_eta follows a hard start date. The reason is written only when
    the splice has none yet (required then); an existing reason stays as recorded.
    Setting 0 clears the hours and keeps the reason. No Trello. Commits on success;
    raises SpliceError (no writes) on a rule violation.
    """

    def __init__(self, splice, additional_install_hrs, additional_install_note=None, user=None):
        self.splice = splice
        self.additional_install_hrs_raw = additional_install_hrs
        self.additional_install_note = additional_install_note
        self.user = user

    def execute(self):
        splice = self.splice
        if splice.parent_release_id is None:
            raise SpliceError(
                f"{splice.job}-{splice.release} is not a splice; additional install hours live on splices",
                status=409,
            )
        new_extra = _coerce_hours(
            self.additional_install_hrs_raw, "Additional install hours", allow_blank=True
        )
        old_extra = float(splice.additional_install_hrs or 0)
        old_total = splice.install_hrs
        budget = budget_hours(splice)

        note = splice.additional_install_note
        if new_extra > 0 and not note:
            note = " ".join(str(self.additional_install_note or "").split()) or None
            if not note:
                raise SpliceError("Explain why additional install hours are needed")
        new_total = round(budget + new_extra, 4)
        if new_total <= 0:
            raise SpliceError("A splice must carry install hours greater than 0")

        if abs(new_extra - old_extra) < 1e-9 and note == splice.additional_install_note:
            return splice

        payload = {
            "additional_install_hrs": {"old_value": old_extra or None, "new_value": new_extra or None},
            "install_hrs": {"old_value": old_total, "new_value": new_total},
        }
        if note != splice.additional_install_note:
            payload["additional_install_note"] = {
                "old_value": splice.additional_install_note,
                "new_value": note,
            }

        splice.additional_install_hrs = new_extra or None
        splice.additional_install_note = note
        splice.install_hrs = new_total
        if splice.start_install is not None and splice.start_install_formulaTF is False:
            splice.comp_eta = calculate_install_complete_date(
                splice.start_install, new_total, splice.num_guys
            )
        splice.last_updated_at = datetime.utcnow()
        splice.source_of_update = "Brain"

        # Deliberately NOT queued to the Trello outbox: splices have no card.
        event = JobEventService.create(
            job=splice.job,
            release=splice.release,
            action="updated",
            source="Brain",
            payload=payload,
            internal_user_id=self.user.id if self.user else None,
        )
        if event:
            JobEventService.close(event.id)
        db.session.commit()

        logger.info(
            "splice_additional_hours_updated",
            release_id=splice.id,
            job=splice.job,
            release=splice.release,
            from_hrs=old_extra,
            to_hrs=new_extra,
            install_hrs=new_total,
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
            additional = float(job_record.additional_install_hrs or 0)
            if float(new_hrs) + 1e-9 < additional:
                raise SpliceError(
                    f"This splice has {additional:g} additional install hours; "
                    "its install hours cannot drop below that",
                    status=409,
                )
            new_budget = float(new_hrs) - additional
            if parent is not None:
                total, allocated, remaining = install_pool(parent, exclude_id=job_record.id)
                if new_budget > 1e-9 and total is not None and new_budget > remaining + 1e-9:
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
