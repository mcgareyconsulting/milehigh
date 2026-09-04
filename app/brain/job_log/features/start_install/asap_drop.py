"""
@milehigh-header
schema_version: 1
purpose: The one ASAP-drop rule — once a release reaches `Ship Complete` or any later stage it is no longer a rush, so the flag comes off. Shared by every writer that advances a stage, because a rule that lives inside one caller is a rule the other callers silently skip.
exports:
  drop_asap_on_completion: Clear start_install_asap on a release that has reached Ship Complete or later, emitting a linked audit event
  ASAP_DROP_REASON: The CascadeReason string these child events carry
imports_from: [app.api.helpers, app.services.job_event_service]
imported_by: [app/brain/job_log/features/stage/command.py, app/brain/job_log/routes.py, app/trello/sync.py]
invariants:
  - Fires at rank(`Ship Complete`) <= rank(new stage) < 99 — 'or later', with Hold (99) excluded
  - Flag only: start_install / comp_eta / ship_date and the date's colour are never touched here
  - No-op (returns False) when the flag is already clear or the stage is earlier
  - Emits action='updated' with parent_event_id so the undo endpoint can bundle the revert
  - ASAP_DROP_REASON is FROZEN: it is written into stored event payloads, so the value stays
    even though the rule is 'Ship Complete or later' rather than Ship Complete alone
"""
from app.api.helpers import STAGE_PROGRESSION_RANK
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

logger = get_logger(__name__)

ASAP_DROP_REASON = 'asap_dropped_on_ship_complete'


def drop_asap_on_completion(job_record, *, new_stage, parent_event_id, source='Brain') -> bool:
    """Clear the ASAP flag on a release that has reached Ship Complete or later.

    The dates set while the release was a rush are LEFT intact — the PM owns the install
    date from then on. Only the flag (and with it the red) comes off.

    Callers pass the stage they just applied rather than reading it off the record, so a
    caller that computes the destination before writing it can still use this.

    Returns True if the flag was dropped, False on no-op. Caller commits.
    """
    if not bool(getattr(job_record, 'start_install_asap', False)):
        return False

    ship_complete_rank = STAGE_PROGRESSION_RANK['Ship Complete']
    new_rank = STAGE_PROGRESSION_RANK.get(new_stage, -1)
    # Hold sits at rank 99 and is not a completion — a held release keeps its rush flag.
    if not (ship_complete_rank <= new_rank < 99):
        return False

    job_record.start_install_asap = False
    JobEventService.create_and_close(
        job=job_record.job,
        release=job_record.release,
        action='updated',
        source=source,
        payload={
            'field': 'start_install_asap',
            'old_value': True,
            'new_value': False,
            'reason': ASAP_DROP_REASON,
            'parent_event_id': parent_event_id,
        },
    )
    logger.info(
        "asap_dropped",
        job=job_record.job,
        release=job_record.release,
        stage=new_stage,
        parent_event_id=parent_event_id,
        source=source,
    )
    return True
