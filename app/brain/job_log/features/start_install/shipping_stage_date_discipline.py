"""
@milehigh-header
schema_version: 1
purpose: N5 late-stage date discipline — two rules with two different triggers. (1) Formula/estimated dates blank and lock when a release enters Ship Planning or Ship Complete: an estimate that survived to the truck is stale by definition. (2) A hard date's COLOR dumps when the release reaches the Install Start STAGE (BUG-11) — not when a start_install date is set, and not at the ship stages. Complete-zone job_comp cascade stays separate.
exports:
  apply_shipping_stage_date_discipline: Route a stage change to the formula blank or the hard-date color dump
  SHIPPING_STAGES: Stages that blank stale formula dates
  COLOR_DUMP_STAGE / is_at_or_past_color_dump: Where a hard date loses its color
imports_from: [app.api.helpers, app.models, app.services.job_event_service, app.brain.job_log.features.start_install.neutralize_install_date_cascade]
imported_by: [app/brain/job_log/features/stage/command.py, app/brain/job_log/features/start_install/command.py]
invariants:
  - Fork is hard date vs formula: hard = start_install_formulaTF is False AND start_install is set
  - Formula path blanks start_install, ship_date, formula text, and comp_eta; sets formulaTF=False so scheduling never re-estimates
  - A hard date KEEPS its color through Ship Planning and Ship Complete (BUG-11). Yellow overdue must
    stay visible until install actually starts — it is a scored EOS metric, not something to sweep away.
  - The color dump fires on the Install Start stage and anything past it, via neutralize_install_date_cascade
  - Idempotent: already-blank locked rows and already-neutral hard dates are no-ops
  - Child audit events carry parent_event_id for stage-undo bundling visibility
"""
from datetime import datetime

from app.api.helpers import STAGE_PROGRESSION_RANK
from app.models import Releases
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger
from app.brain.job_log.features.start_install.neutralize_install_date_cascade import (
    neutralize_install_date_cascade,
)

logger = get_logger(__name__)

# Stale formula/estimated dates blank here. Hard dates are NOT touched at these
# stages — see COLOR_DUMP_STAGE.
SHIPPING_STAGES = ("Ship Planning", "Ship Complete")

# BUG-11: where a hard date loses its color. Bill reversed the 2026-08-15 rule that
# dumped it at the ship stages — "I might have given you bad information on where we
# wanted to change that". The trigger is the release reaching the Install Start STAGE,
# which is a different event from a start_install DATE being set: a release can carry a
# hard install date for weeks before install begins, and its color (green, or yellow once
# overdue) has to stay readable that whole time.
COLOR_DUMP_STAGE = "Install Start"
_HOLD_RANK = 99
_COLOR_DUMP_RANK = STAGE_PROGRESSION_RANK[COLOR_DUMP_STAGE]


def is_at_or_past_color_dump(stage: str | None) -> bool:
    """True once the release has reached Install Start (or later). Hold is not 'later'."""
    rank = STAGE_PROGRESSION_RANK.get(stage, -1)
    return _COLOR_DUMP_RANK <= rank < _HOLD_RANK


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
    """Route a stage change to the N5 date rule that owns it.

    Two rules, two triggers:
      - Install Start (BUG-11) → a hard date keeps its value but loses its color
      - Ship Planning / Ship Complete → stale formula dates blank and lock

    Returns a small extras dict for the stage command response:
      - formula_dates_blanked: True when estimated dates were cleared
      - dates_washed: True when hard-date color was neutralized
    Empty dict on no-op / wrong stage. Caller commits.
    """
    if stage == COLOR_DUMP_STAGE:
        if not _is_hard_install(job_record):
            return {}
        washed = neutralize_install_date_cascade(
            job_record,
            parent_event_id=parent_event_id,
            reason="stage_set_to_install_start",
            source=source,
        )
        if washed:
            logger.info(
                "install_start_dates_washed",
                job=job_record.job,
                release=job_record.release,
                stage=stage,
                parent_event_id=parent_event_id,
            )
            return {"dates_washed": True}
        return {}

    if stage not in SHIPPING_STAGES:
        return {}

    reason = (
        "stage_set_to_ship_planning"
        if stage == "Ship Planning"
        else "stage_set_to_ship_complete"
    )

    # BUG-11: a hard date rides through the ship stages with its color intact. Only the
    # estimate half of the fork is stale here, so a hard date is simply left alone.
    if _is_hard_install(job_record):
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
