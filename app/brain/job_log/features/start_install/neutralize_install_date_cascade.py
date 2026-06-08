"""
@milehigh-header
schema_version: 1
purpose: Neutralize an install date's color when a release reaches the complete zone (stage='Complete'/'Install Complete', job_comp='X', invoiced='X') — the DATE is retained, only its red/green/yellow color flagging is stripped (start_install_no_color=True) so a finished release doesn't show an alarming date. Emits a child audit event linked by parent_event_id.
exports:
  neutralize_install_date_cascade: Set start_install_no_color (and clear start_install_asap) on a hard-dated release, keeping the date
imports_from: [app.models, app.services.job_event_service]
imported_by: [app/brain/job_log/features/stage/command.py, app/brain/job_log/routes.py]
invariants:
  - No-op unless a hard date is present (start_install_formulaTF is False and start_install is set)
  - KEEPS start_install and its hard-date flag (the date is preserved; scheduling still skips hard rows)
  - Sets start_install_no_color=True (renders neutral) and clears start_install_asap (no red)
  - Idempotent: no-op when already neutral and not ASAP
  - Emits action='updated', field='start_install_no_color' with parent_event_id for audit bundling
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

    Keeps start_install (and its hard-date flag) so the actual install date is preserved,
    but sets start_install_no_color=True so it renders neutral instead of red/green/yellow,
    and clears start_install_asap so a finished release never shows the red ASAP flag.

    Returns True if it changed anything, False on no-op. Caller commits.
    """
    # Only a hard date with a concrete value shows color worth neutralizing. Formula-driven
    # rows already render neutral, so leave them (and their recomputation) alone.
    if job_record.start_install_formulaTF is not False or job_record.start_install is None:
        return False

    already_neutral = bool(getattr(job_record, 'start_install_no_color', False))
    is_asap = bool(getattr(job_record, 'start_install_asap', False))
    if already_neutral and not is_asap:
        return False

    job_record.start_install_no_color = True
    job_record.start_install_asap = False
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = source

    JobEventService.create_and_close(
        job=job_record.job,
        release=job_record.release,
        action='updated',
        source=source,
        payload={
            'field': 'start_install_no_color',
            'old_value': already_neutral,
            'new_value': True,
            'reason': reason,
            'parent_event_id': parent_event_id,
        },
    )

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
