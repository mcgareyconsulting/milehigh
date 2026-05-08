"""
@milehigh-header
schema_version: 1
purpose: Idempotently clear a hard start_install date as a cascade from a completion-marking action (stage='Complete', job_comp='X', invoiced='X'), emitting a child audit event linked by parent_event_id.
exports:
  clear_hard_date_cascade: Function that clears the hard-date flag and emits a child event when a hard date is present
imports_from: [app.models, app.services.job_event_service]
imported_by: [app/brain/job_log/features/stage/command.py, app/brain/job_log/routes.py]
invariants:
  - No-op when start_install_formulaTF is not False (no hard date present)
  - Sets start_install_formulaTF=True and start_install_formula=None; does NOT touch start_install column or push to Trello
  - Emits action='updated', field='start_install_formulaTF' with parent_event_id so audit bundling under the triggering event works
"""
from datetime import datetime
from typing import Literal

from app.models import Releases
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)

CascadeReason = Literal[
    'stage_set_to_complete',
    'job_comp_set_to_x',
    'invoiced_set_to_x',
]


def clear_hard_date_cascade(
    job_record: Releases,
    *,
    parent_event_id: int,
    reason: CascadeReason,
    source: str = 'Brain',
) -> bool:
    """Idempotently clear a hard start_install date.

    Returns True if a hard date was present and cleared, False if no-op.
    Caller is responsible for the surrounding db.session.commit() and any
    scheduling cascade (which will recompute start_install from the formula).
    """
    if job_record.start_install_formulaTF is not False:
        return False

    job_record.start_install_formulaTF = True
    job_record.start_install_formula = None
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = source

    JobEventService.create_and_close(
        job=job_record.job,
        release=job_record.release,
        action='updated',
        source=source,
        payload={
            'field': 'start_install_formulaTF',
            'old_value': False,
            'new_value': True,
            'reason': reason,
            'parent_event_id': parent_event_id,
        },
    )

    logger.info(
        "Auto-cleared hard date on completion cascade",
        extra={
            'job': job_record.job,
            'release': job_record.release,
            'reason': reason,
            'parent_event_id': parent_event_id,
        },
    )
    return True
