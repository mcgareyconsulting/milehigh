"""
@milehigh-header
schema_version: 1
purpose: Roll a Ready-to-Ship release into Ship Planning the moment it is given its first hard Start install date. The stage and the date are one fact stated twice — "we know when this ships" — so setting one settles the other, whichever surface the user typed it on.
exports:
  ROLL_STAGES: The stages this roll fires from (Ready to Ship minus Ship Planning itself)
  roll_to_ship_planning_on_first_hard_date: Apply the roll; returns True when the stage moved
imports_from: [app.models, app.brain.job_log.features.stage.command]
imported_by: [app/brain/job_log/features/start_install/command.py]
invariants:
  - Fires ONLY on the first hard date. A release that already had one is having its date CHANGED,
    not planned, and a reschedule must never re-stage anything.
  - Fires only from ROLL_STAGES. A projected date exists on nearly every fab row, so widening this
    to "any stage" would yank half the shop floor into Ship Planning on an ordinary recalc.
  - A formula/projected date is NOT a date here: the test is the same hard-date test the ship lanes
    and the Job Log's Start install cell use (start_install_formulaTF is False AND start_install).
  - Clearing a date never rolls anything; only setting one does.
  - Never fires on an UNDO. Undo restores a prior state verbatim; cascading off it would leave the
    release in a stage it was never in.
  - The roll is a CHILD event: UpdateStageCommand is called with parent_event_id set to the
    start_install event, so /brain/events/<id>/undo reverts the date and the stage as one bundle.
    Without that link, undoing the date would leave the release stranded in Ship Planning.
  - Delegates to UpdateStageCommand rather than writing job_record.stage directly, so the roll gets
    the same stage_group sync, fab_order re-tier, Trello list move and N5 date discipline every
    other stage change gets. defer_cascade=True: the caller runs the scheduling recalc once, after.
  - Never raises. A failed roll is logged and the date write (already committed) stands — the user
    typed a date and got a date; losing the stage nudge is not worth losing that.
"""
from typing import Optional

from app.models import Releases
from app.logging_config import get_logger

logger = get_logger(__name__)

# Where the roll fires from: the Ready-to-Ship stages a release sits in while it waits for a ship
# day, minus Ship Planning, which is where it lands. Mirrored client-side by
# READY_TO_SHIP_COLUMN_STAGES / ROLLS_TO_SHIP_PLANNING (frontend/src/utils/readyToShipColumn.js,
# frontend/src/components/GanttChart.jsx) — the Timeline decides whether it must name the stage
# itself off this exact set, so keep the two identical.
ROLL_STAGES = ("Store at MHMW", "Paint QC")

SHIP_PLANNING_STAGE = "Ship Planning"


def roll_to_ship_planning_on_first_hard_date(
    job_record: Releases,
    *,
    parent_event_id: int,
    had_hard_date: bool,
    is_undo: bool = False,
    source: str = "Brain",
) -> bool:
    """Move `job_record` to Ship Planning if it just got its first hard Start install date.

    Call AFTER the date write has committed. Returns True when the stage moved.

    Args:
        job_record:      the release, already carrying its new date
        parent_event_id: the `update_start_install` event this roll hangs off, for undo bundling
        had_hard_date:   whether the release carried a hard date BEFORE this write
        is_undo:         True when the date write was itself an undo (suppresses the roll)
    """
    if is_undo or had_hard_date:
        return False
    if job_record.stage not in ROLL_STAGES:
        return False
    # The write may have cleared the date rather than set one; only a real hard date rolls.
    if job_record.start_install is None or job_record.start_install_formulaTF is not False:
        return False

    from_stage = job_record.stage
    from app.brain.job_log.features.stage.command import UpdateStageCommand

    try:
        UpdateStageCommand(
            job_id=job_record.job,
            release=job_record.release,
            stage=SHIP_PLANNING_STAGE,
            source=source,
            source_of_update=source,
            # The caller recalculates once for the whole gesture.
            defer_cascade=True,
            parent_event_id=parent_event_id,
        ).execute()
    except ValueError as exc:
        # Dedup collision inside the 30s bucket: the same release was just staged by hand, so the
        # roll has nothing left to do. Anything else is a real failure of a best-effort nudge.
        if str(exc) == "Event already exists":
            logger.debug(
                "ship_planning_roll_deduplicated",
                job=job_record.job,
                release=job_record.release,
            )
        else:
            logger.error(
                "ship_planning_roll_failed",
                job=job_record.job,
                release=job_record.release,
                parent_event_id=parent_event_id,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
        return False
    except Exception as exc:  # noqa: BLE001 — the date write already committed; never lose it
        logger.error(
            "ship_planning_roll_failed",
            job=job_record.job,
            release=job_record.release,
            parent_event_id=parent_event_id,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return False

    logger.info(
        "rolled_to_ship_planning",
        release_id=job_record.id,
        job=job_record.job,
        release=job_record.release,
        from_stage=from_stage,
        to_stage=SHIP_PLANNING_STAGE,
        parent_event_id=parent_event_id,
        start_install=job_record.start_install.isoformat() if job_record.start_install else None,
    )
    return True


def has_hard_start_install(job_record: Optional[Releases]) -> bool:
    """The hard-date test, shared so callers capture `had_hard_date` the same way."""
    if job_record is None:
        return False
    return (
        job_record.start_install_formulaTF is False
        and job_record.start_install is not None
    )
