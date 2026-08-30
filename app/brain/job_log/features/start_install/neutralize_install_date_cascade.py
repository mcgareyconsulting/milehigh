"""
@milehigh-header
schema_version: 1
purpose: Neutralize a hard install date's color once install has started or the release is closed out (stage `Install Start` or later, job_comp='X', invoiced='X') — the DATE is retained, only its red/green/yellow color flagging is stripped (start_install_no_color = True) so a finished release doesn't show an alarming date. The ship date's color follows start_install_no_color, so it neutralizes with the install date and needs no separate flag. Emits a child audit event, linked by parent_event_id.
exports:
  neutralize_install_date_cascade: Set start_install_no_color (and clear start_install_asap) on a started/completed release, keeping the date
  COLOR_DUMP_STAGES: Stages at which a hard install date's color drops (`Install Start` or later)
  reason_for_stage: Map a color-dump stage to its CascadeReason
imports_from: [app.models, app.services.job_event_service]
imported_by: [app/brain/job_log/features/stage/command.py, app/brain/job_log/features/start_install/command.py, app/brain/job_log/routes.py]
invariants:
  - Install neutralization is a no-op unless a hard date is present (start_install_formulaTF is False and start_install is set)
  - The trigger is the STAGE reaching `Install Start` or later, never the `start_install` date arriving (BUG-11)
  - Color survives the ship stages; Ship Planning / Ship Complete no longer wash it
  - KEEPS start_install / ship_date and the hard-date flag, EXCEPT an ASAP row's placeholder date, which is
    rewritten to install_started_on when the caller passes it (stage transitions into the dump zone only)
  - Sets start_install_no_color=True (renders both install and ship neutral) and clears start_install_asap (no red)
  - Idempotent: no-op when already neutral and not ASAP
  - Emits action='updated' with parent_event_id for audit bundling
"""
from datetime import date, datetime
from typing import Literal, Optional

from app.models import Releases
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)

CascadeReason = Literal[
    'stage_set_to_install_start',
    'stage_set_to_install_complete',
    'stage_set_to_complete',
    'job_comp_set_to_x',
    'invoiced_set_to_x',
]

# The stages at which a hard install date's color drops: a transition whose
# DESTINATION is `Install Start` or any stage after it (BUG-11).
#
# Mind the two look-alike names: `start_install` is the date field, `Install
# Start` is the stage value. The trigger is the stage, never the date arriving —
# a date-driven dump fires on schedule even when the install slipped, hiding the
# yellow-overdue signal that must never silently disappear.
#
# "Or later" is load-bearing: a release can jump Ship Planning -> `Complete` and
# skip `Install Start` entirely, so a bare equality check on `Install Start`
# would miss it. This is the tail of the canonical stage order in
# app.api.helpers.STAGE_HOUR_PERCENTAGES, starting at `Install Start`;
# tests/brain/test_install_start_color_dump.py asserts the two stay in step.
COLOR_DUMP_STAGES = ('Install Start', 'Install Complete', 'Complete')


def reason_for_stage(stage: str) -> CascadeReason:
    """Map a color-dump stage to its audit reason. Caller checks COLOR_DUMP_STAGES first."""
    return {
        'Install Start': 'stage_set_to_install_start',
        'Install Complete': 'stage_set_to_install_complete',
        'Complete': 'stage_set_to_complete',
    }[stage]


def neutralize_install_date_cascade(
    job_record: Releases,
    *,
    parent_event_id: int,
    reason: CascadeReason,
    source: str = 'Brain',
    install_started_on: Optional[date] = None,
) -> bool:
    """Strip the color from a hard install date once install has started (or it is complete).

    Keeps start_install (and the hard-date flag) so the actual date is preserved, but sets
    start_install_no_color=True so it renders neutral instead of red/green/yellow, and clears
    start_install_asap so a finished release never shows the red ASAP flag. The ship date's
    color follows start_install_no_color, so it goes neutral in lockstep — no separate write.

    Args:
        install_started_on: The date install actually began — the date of the stage event
            that triggered this. When given, the hard start_install is rewritten to it.

            Pass it ONLY for an ASAP row entering `Install Start` or later. An ASAP date
            was never a plan: it was an anchor five business days out, stamped to make the
            row shout, so the day install starts is the truer value. A hand-set hard date
            is a real commitment and must never be rewritten — omit it and no date moves.

            The ASAP test is the CALLER's to make, deliberately: UpdateStageCommand drops
            start_install_asap earlier in the same command, so by the time this runs the
            flag is already False and cannot be re-derived here.

    Returns True if it changed anything, False on no-op. Caller commits.
    """
    changed = False

    def _emit(field, old_value, new_value):
        """Record one field change as a child audit event linked to the parent."""
        JobEventService.create_and_close(
            job=job_record.job,
            release=job_record.release,
            action='updated',
            source=source,
            payload={
                'field': field,
                'old_value': old_value,
                'new_value': new_value,
                'reason': reason,
                'parent_event_id': parent_event_id,
            },
        )

    # --- Install date ---
    # Only a hard date with a concrete value shows color worth neutralizing. Formula-driven
    # rows already render neutral, so leave them (and their recomputation) alone.
    install_hard = (
        job_record.start_install_formulaTF is False and job_record.start_install is not None
    )
    was_asap = bool(getattr(job_record, 'start_install_asap', False))
    if install_hard:
        already_neutral = bool(getattr(job_record, 'start_install_no_color', False))
        if not (already_neutral and not was_asap):
            job_record.start_install_no_color = True
            job_record.start_install_asap = False
            _emit('start_install_no_color', already_neutral, True)
            changed = True

        # Rewrite an ASAP row's placeholder date to the day install actually started.
        # The caller decides whether this row qualifies (see the arg doc — the ASAP flag
        # is already cleared by the time we get here). The event carries both values so
        # the anchor it replaced stays recoverable.
        if install_started_on is not None:
            old_start = job_record.start_install
            if old_start != install_started_on:
                job_record.start_install = install_started_on
                _emit(
                    'start_install',
                    old_start.isoformat() if old_start else None,
                    install_started_on.isoformat(),
                )
                logger.info(
                    "asap_date_reset_to_install_start",
                    job=job_record.job,
                    release=job_record.release,
                    old=old_start.isoformat() if old_start else None,
                    new=install_started_on.isoformat(),
                    parent_event_id=parent_event_id,
                )
                changed = True

    if not changed:
        return False

    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = source

    logger.info(
        "install_date_color_neutralized",
        job=job_record.job,
        release=job_record.release,
        reason=reason,
        parent_event_id=parent_event_id,
    )
    return True
