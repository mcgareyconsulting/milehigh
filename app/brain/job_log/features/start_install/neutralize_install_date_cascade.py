"""
@milehigh-header
schema_version: 1
purpose: Neutralize a hard install date's color when a release reaches the complete zone (stage='Complete'/'Install Complete', job_comp='X', invoiced='X') — the DATE is retained, only its red/green/yellow color flagging is stripped (start_install_no_color = True) so a finished release doesn't show an alarming date. The ship date's color follows start_install_no_color, so it neutralizes with the install date and needs no separate flag. Emits a child audit event, linked by parent_event_id.
exports:
  neutralize_install_date_cascade: Set start_install_no_color (and clear start_install_asap) on a completed release, keeping the date
imports_from: [app.models, app.services.job_event_service]
imported_by: [app/brain/job_log/features/stage/command.py, app/brain/job_log/routes.py]
invariants:
  - Install neutralization is a no-op unless a hard date is present (start_install_formulaTF is False and start_install is set)
  - KEEPS start_install / ship_date and the hard-date flag (dates preserved; scheduling still skips hard rows)
  - Sets start_install_no_color=True (renders both install and ship neutral) and clears start_install_asap (no red)
  - Idempotent: no-op when already neutral and not ASAP
  - Emits action='updated' with parent_event_id for audit bundling
"""
from datetime import datetime
from typing import Literal

from app.models import Releases
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)

CascadeReason = Literal[
    'stage_set_to_complete',
    'stage_set_to_install_complete',
    'job_comp_set_to_x',
    'invoiced_set_to_x',
]


def neutralize_install_date_cascade(
    job_record: Releases,
    *,
    parent_event_id: int,
    reason: CascadeReason,
    source: str = 'Brain',
) -> bool:
    """Strip the color from a hard install date once the release is installed/complete.

    Keeps start_install (and the hard-date flag) so the actual date is preserved, but sets
    start_install_no_color=True so it renders neutral instead of red/green/yellow, and clears
    start_install_asap so a finished release never shows the red ASAP flag. The ship date's
    color follows start_install_no_color, so it goes neutral in lockstep — no separate write.

    Returns True if it changed anything, False on no-op. Caller commits.
    """
    changed = False

    def _emit_neutralized(field, old_value):
        """Record one *_no_color flip as a child audit event linked to the parent."""
        JobEventService.create_and_close(
            job=job_record.job,
            release=job_record.release,
            action='updated',
            source=source,
            payload={
                'field': field,
                'old_value': old_value,
                'new_value': True,
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
    if install_hard:
        already_neutral = bool(getattr(job_record, 'start_install_no_color', False))
        is_asap = bool(getattr(job_record, 'start_install_asap', False))
        if not (already_neutral and not is_asap):
            job_record.start_install_no_color = True
            job_record.start_install_asap = False
            _emit_neutralized('start_install_no_color', already_neutral)
            changed = True

    if not changed:
        return False

    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = source

    logger.info(
        "Neutralized install date color on completion cascade",
        extra={
            'job': job_record.job,
            'release': job_record.release,
            'reason': reason,
            'parent_event_id': parent_event_id,
        },
    )
    return True
