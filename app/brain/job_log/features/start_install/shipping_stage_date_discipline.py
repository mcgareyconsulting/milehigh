"""
@milehigh-header
schema_version: 1
purpose: N5 shipping-stage date discipline — when a release enters Ship Planning or Ship Complete, blank stale formula/estimated dates (and lock against re-estimation) or wash hard-date color to white. Complete-zone job_comp cascade stays separate; this owns only date behavior at shipping stages.
exports:
  apply_shipping_stage_date_discipline: Apply formula-blank or hard-date wash for Ship Planning / Ship Complete
  SHIPPING_STAGES: Stages that trigger the discipline
imports_from: [app.models, app.services.job_event_service, app.brain.job_log.features.start_install.neutralize_install_date_cascade]
imported_by: [app/brain/job_log/features/stage/command.py]
invariants:
  - Fork is hard date vs formula: hard = start_install_formulaTF is False AND start_install is set
  - Formula path blanks start_install, ship_date, formula text, and comp_eta; sets formulaTF=False so scheduling never re-estimates
  - Hard path keeps dates and washes color via neutralize_install_date_cascade (no ASAP red / green / yellow)
  - Idempotent: already-blank locked rows and already-neutral hard dates are no-ops
  - Child audit events carry parent_event_id for stage-undo bundling visibility
"""
from datetime import datetime

from app.models import Releases
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger
from app.brain.job_log.features.start_install.neutralize_install_date_cascade import (
    neutralize_install_date_cascade,
)

logger = get_logger(__name__)

SHIPPING_STAGES = ("Ship Planning", "Ship Complete")


def _is_hard_install(job_record: Releases) -> bool:
    return (
        job_record.start_install_formulaTF is False
        and job_record.start_install is not None
    )


def _already_blank_locked(job_record: Releases) -> bool:
    """Intentionally blank after formula strip: no dates, formulaTF=False, no formula text."""
    return (
        job_record.start_install is None
        and job_record.ship_date is None
        and job_record.start_install_formula is None
        and job_record.start_install_formulaTF is False
        and job_record.comp_eta is None
    )


def apply_shipping_stage_date_discipline(
    job_record: Releases,
    *,
    parent_event_id: int,
    stage: str,
    source: str = "Brain",
) -> dict:
    """Apply N5 date rules when a release is at Ship Planning or Ship Complete.

    Returns a small extras dict for the stage command response:
      - formula_dates_blanked: True when estimated dates were cleared
      - dates_washed: True when hard-date color was neutralized
    Empty dict on no-op / wrong stage. Caller commits.
    """
    if stage not in SHIPPING_STAGES:
        return {}

    reason = (
        "stage_set_to_ship_planning"
        if stage == "Ship Planning"
        else "stage_set_to_ship_complete"
    )

    if _is_hard_install(job_record):
        washed = neutralize_install_date_cascade(
            job_record,
            parent_event_id=parent_event_id,
            reason=reason,
            source=source,
        )
        if washed:
            logger.info(
                "shipping_stage_dates_washed",
                job=job_record.job,
                release=job_record.release,
                stage=stage,
                parent_event_id=parent_event_id,
            )
            return {"dates_washed": True}
        return {}

    # Formula / estimated (or empty formula-driven) path: blank and lock.
    if _already_blank_locked(job_record):
        return {}

    old_start = job_record.start_install
    old_ship = job_record.ship_date
    old_formula = job_record.start_install_formula
    old_tf = job_record.start_install_formulaTF
    old_comp_eta = job_record.comp_eta
    old_asap = bool(getattr(job_record, "start_install_asap", False))

    job_record.start_install = None
    job_record.ship_date = None
    job_record.start_install_formula = None
    # False + null dates = scheduling skips re-estimation (hard-date protection).
    job_record.start_install_formulaTF = False
    job_record.comp_eta = None
    job_record.start_install_asap = False
    job_record.start_install_no_color = False
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = source

    JobEventService.create_and_close(
        job=job_record.job,
        release=job_record.release,
        action="updated",
        source=source,
        payload={
            "field": "shipping_stage_formula_dates",
            "old_value": {
                "start_install": old_start.isoformat() if old_start else None,
                "ship_date": old_ship.isoformat() if old_ship else None,
                "start_install_formula": old_formula,
                "start_install_formulaTF": old_tf,
                "comp_eta": old_comp_eta.isoformat() if old_comp_eta else None,
                "start_install_asap": old_asap,
            },
            "new_value": {
                "start_install": None,
                "ship_date": None,
                "start_install_formula": None,
                "start_install_formulaTF": False,
                "comp_eta": None,
                "start_install_asap": False,
            },
            "reason": reason,
            "parent_event_id": parent_event_id,
        },
    )

    logger.info(
        "shipping_stage_formula_dates_blanked",
        job=job_record.job,
        release=job_record.release,
        stage=stage,
        parent_event_id=parent_event_id,
        prev_start_install=old_start.isoformat() if old_start else None,
        prev_ship_date=old_ship.isoformat() if old_ship else None,
    )
    return {"formula_dates_blanked": True}
