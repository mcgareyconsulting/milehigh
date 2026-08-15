"""
@milehigh-header
schema_version: 1
purpose: Single source of truth for the fab_order a release should hold at a given stage, shared by every code path that writes a stage.
exports:
  FabOrderPlan: The value + reason a stage change implies for fab_order
  plan_fab_order_for_stage: Decide the fab_order for a stage (None = leave it alone)
  apply_fab_order_for_stage: Execute a plan — write the field and emit the linked event
imports_from: [app.models, app.api.helpers, app.services.job_event_service, app.logging_config]
imported_by: [app/brain/job_log/features/stage/command.py, app/brain/job_log/routes.py, app/trello/sync.py]
invariants:
  - Stage 'Complete' is terminal — fab_order is always NULL there
  - Fixed-tier stages always hold their tier value (0 Install, 1 Ship Complete, 2 Paint Complete/Store/Ship Planning)
  - Dynamic stages never hold a reserved value (< 3) or NULL — arriving with one is repaired to the back of that stage's deck
  - The DB field is written even when the audit event deduplicates; a dropped event must never leave fab_order stale
updated_by_agent: 2026-08-15T00:00:00Z

BUG-9. `fab_order` tier assignment used to live inline inside
`UpdateStageCommand`, which meant it only ran when a stage change came through
that one command. Three other paths write a stage:

  * the inbound Trello sync (`TrelloListMapper.apply_trello_list_to_db`) — how
    the shop actually moves work, and it touched `fab_order` not at all, so a
    card dragged from the paint list to a shipping list kept its tier-2 value
    forever ("it's not flipping the two and the one");
  * `update_job_comp` setting Install Start via `update_job_stage_fields` —
    same silence, so a tier-0 stage kept whatever the paint deck left behind;
  * `update_job_comp` setting Install Complete — which *cleared* fab_order to
    NULL, while `UpdateStageCommand` sets the same stage to tier 0. The same
    end state, two answers, depending on which button you pressed ("the fab
    order is being cleared and not cleared").

The rules were never in dispute — they are stated identically in
`migrate_unified.py`'s invariants and in `FIXED_TIER_STAGES`. They were just
implemented once and skipped three times. This module is that implementation,
and the four write paths call it instead of restating it.
"""
from dataclasses import dataclass
from typing import Optional

from app.logging_config import get_logger
from app.services.job_event_service import JobEventService

logger = get_logger(__name__)

#: Tiers 0-2 are reserved for fixed-tier stages, so a dynamic stage's fab_order
#: is always >= 3. A dynamic release holding less than this drifted there.
RESERVED_TIER_CEILING = 3

#: Terminal stage — ordering is meaningless once a release is done.
TERMINAL_STAGE = "Complete"


@dataclass(frozen=True)
class FabOrderPlan:
    """What a stage change implies for fab_order. `reason` lands in the event
    payload, so it is the explanation a user reads in the change log."""
    fab_order: Optional[float]
    reason: str


def _back_of_deck(stages, exclude_job, exclude_release) -> float:
    """First free slot behind everything currently sitting in `stages`.

    Floors the max at 2 so the result is never inside the reserved tier band,
    and ignores the DEFAULT_FAB_ORDER placeholder (80.555) — that value marks
    "unordered", not "last in line", and treating it as the back of the deck
    would push every repair into the eighties.
    """
    from sqlalchemy import func, or_
    from app.api.helpers import DEFAULT_FAB_ORDER, _get_all_variants_for_stages
    from app.models import Releases, db

    variants = _get_all_variants_for_stages(list(stages))
    current_max = db.session.query(func.max(Releases.fab_order)).filter(
        Releases.stage.in_(variants),
        Releases.fab_order.isnot(None),
        Releases.fab_order != DEFAULT_FAB_ORDER,
        Releases.is_archived != True,  # noqa: E712
        or_(
            Releases.job != exclude_job,
            Releases.release != exclude_release,
        ),
    ).scalar()
    base = current_max if current_max is not None and current_max >= 2 else 2
    return base + 1


def plan_fab_order_for_stage(job_record, new_stage, old_stage_group=None) -> Optional[FabOrderPlan]:
    """Decide what fab_order a release should hold once it sits at `new_stage`.

    Returns None when the current value is already right — callers write
    nothing and emit no event in that case. `old_stage_group` is the record's
    stage_group *before* the move and must be captured by the caller before it
    overwrites the field; it only affects the Welded QC department handoff.
    """
    from app.api.helpers import (
        DEFAULT_FAB_ORDER,
        STAGE_ORDER_EXEMPT,
        _normalize_stage,
        get_fixed_tier,
    )

    normalized = _normalize_stage(new_stage)
    if normalized is None:
        # Unrecognised stage: refuse to guess. Leaving the old value is the
        # conservative move — the stage itself is already suspect.
        return None

    current = job_record.fab_order

    # Complete is terminal — nothing to order.
    if normalized == TERMINAL_STAGE:
        return None if current is None else FabOrderPlan(None, "complete_clears_fab_order")

    tier = get_fixed_tier(normalized)
    if tier is not None:
        return None if current == tier else FabOrderPlan(tier, "fixed_tier")

    # Hold is a pause, not a position — it keeps whatever it had so the release
    # returns to roughly where it left.
    if normalized in STAGE_ORDER_EXEMPT:
        return None

    # Dynamic stage from here down.
    if normalized == "Welded QC" and old_stage_group != "READY_TO_SHIP":
        # Department handoff, Fab → Paint: land at the back of the paint deck so
        # a fresh arrival doesn't jump the line on work already in the booth.
        return FabOrderPlan(
            _back_of_deck(["Welded QC", "Paint Start"], job_record.job, job_record.release),
            "paint_handoff",
        )

    if current is not None and current >= RESERVED_TIER_CEILING:
        return None  # already a valid dynamic position; the user owns it

    # Arrived on a dynamic stage holding a reserved tier value or nothing at
    # all — i.e. it came back down from shipping/install, or was cleared by
    # Complete and then reopened. Either way it has no real position, and
    # leaving 0/1/2 in place sorts it in front of the entire shop.
    if normalized == "Released":
        # Released is the unordered pool; DEFAULT_FAB_ORDER is its placeholder
        # (same convention as fix_null_fab_orders).
        return FabOrderPlan(DEFAULT_FAB_ORDER, "reserved_tier_released")

    return FabOrderPlan(
        _back_of_deck([normalized], job_record.job, job_record.release),
        "reserved_tier_released",
    )


def apply_fab_order_for_stage(
    job_record,
    new_stage,
    old_stage_group=None,
    *,
    source="Brain",
    parent_event_id=None,
    stage_reason=None,
):
    """Plan and apply the fab_order for a stage move. Returns the FabOrderPlan
    that was applied, or None when nothing needed to change.

    The field is written whether or not the audit event survives dedup. The old
    inline version wrote the field only inside the `if event:` branch, so a
    deduplicated event left the release sitting on a stale tier — the very
    "cleared and not cleared" inconsistency this is fixing. The DB value is the
    truth; the event is the record of it.
    """
    plan = plan_fab_order_for_stage(job_record, new_stage, old_stage_group)
    if plan is None:
        return None

    old_fab_order = _json_safe(job_record.fab_order)
    payload = {
        "from": old_fab_order,
        "to": _json_safe(plan.fab_order),
        "reason": plan.reason if stage_reason is None else f"{plan.reason}:{stage_reason}",
    }
    if parent_event_id is not None:
        payload["parent_event_id"] = parent_event_id

    event = JobEventService.create(
        job=job_record.job,
        release=job_record.release,
        action="update_fab_order",
        source=source,
        payload=payload,
    )

    job_record.fab_order = plan.fab_order

    if event is None:
        logger.debug(
            "fab_order_event_deduplicated",
            job=job_record.job,
            release=job_record.release,
            fab_order=plan.fab_order,
        )
    else:
        JobEventService.close(event.id)

    logger.info(
        "fab_order_retiered",
        release_id=job_record.id,
        job=job_record.job,
        release=job_record.release,
        to_stage=new_stage,
        fab_order=plan.fab_order,
        reason=plan.reason,
    )
    return plan


def _json_safe(value):
    """NaN is not JSON — it has turned up in fab_order before (see the coercion
    in UpdateFabOrderCommand) and would poison the event payload."""
    import math

    if isinstance(value, float) and math.isnan(value):
        return None
    return value
