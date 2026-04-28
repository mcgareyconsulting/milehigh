"""
@milehigh-header
schema_version: 1
purpose: Encapsulate the full stage update workflow (DB write, stage_group sync, fab_order auto-assign, job_comp cascade, outbox queuing, scheduling recalc) as a single command object.
exports:
  UpdateStageCommand: Dataclass command that executes a stage update with all side effects
  StageUpdateResult: Dataclass result with event_id, job_comp/fab_order extras
imports_from: [app.models, app.services.outbox_service, app.services.job_event_service, app.api.helpers, app.brain.job_log.scheduling.service]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - Fixed-tier stages (Ready-to-Ship / Complete groups) auto-assign fab_order via get_fixed_tier
  - Setting stage='Complete' cascades job_comp='X'; leaving Complete clears job_comp='X'
  - Deduplicated events raise ValueError (event_exists); caller decides whether to treat as success
  - Scheduling recalculation failure is logged but does not roll back the update
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import math

from app.models import Releases, db
from app.services.job_event_service import JobEventService
from app.services.outbox_service import OutboxService
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class StageUpdateResult:
    job_id: int
    release: str
    event_id: int
    stage: str
    extras: dict = field(default_factory=dict)  # job_comp / fab_order if cascaded
    status: str = "success"

    def to_dict(self) -> dict:
        d = {
            "job_id": self.job_id,
            "release": self.release,
            "event_id": self.event_id,
            "stage": self.stage,
            "status": self.status,
        }
        d.update(self.extras)
        return d


@dataclass
class UpdateStageCommand:
    """
    Command to update the stage for a job-release combination.

    Mirrors the pre-extraction /update-stage route body:
      1. Fetch Releases row.
      2. Create primary `update_stage` event (dedup; raises ValueError on dedup hit).
      3. Write stage + stage_group fields.
      4. Cascade job_comp='X' on stage='Complete'; clear on leaving Complete.
      5. Auto-assign fab_order for fixed-tier stages (Ready-to-Ship / Complete).
      6. Enqueue Trello move_card outbox item if the row has a trello_card_id.
      7. Commit, then run scheduling cascade (FABRICATION).
    """
    job_id: int
    release: str
    stage: str
    source: str = "Brain"
    source_of_update: str = "Brain"
    # When True, skip the final recalculate_all_jobs_scheduling call — used by
    # the /brain/events/<id>/undo bundling path so the cascade runs once after
    # the parent + linked children all revert.
    defer_cascade: bool = False
    # When set, merged into the primary event payload as `undone_event_id`. Used by the
    # /brain/events/<id>/undo endpoint to (a) link the undo event back to its source for
    # audit trail rendering and (b) perturb the dedup hash so undo-the-undo within the
    # 30s bucket doesn't collide with the original event.
    undone_event_id: Optional[int] = None

    def execute(self) -> StageUpdateResult:
        from app.api.helpers import get_stage_group_from_stage, get_fixed_tier

        job_record: Releases = Releases.query.filter_by(
            job=self.job_id, release=self.release
        ).first()
        if not job_record:
            logger.warning(f"Job not found: {self.job_id}-{self.release}")
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        old_stage = job_record.stage if job_record.stage else 'Released'

        event_payload = {'from': old_stage, 'to': self.stage}
        if self.undone_event_id is not None:
            event_payload['undone_event_id'] = self.undone_event_id

        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_stage',
            source=self.source,
            payload=event_payload,
        )
        if event is None:
            logger.info(
                f"Event already exists for job {self.job_id}-{self.release} to stage {self.stage}"
            )
            raise ValueError("Event already exists")

        old_stage_group = job_record.stage_group
        new_stage_group = get_stage_group_from_stage(self.stage)
        logger.info(
            f"Stage change for job {self.job_id}-{self.release}: "
            f"old_stage_group={old_stage_group}, new_stage_group={new_stage_group}, "
            f"old_stage={old_stage}, new_stage={self.stage}"
        )

        fab_order_to_set = None
        old_fab_order_for_update = job_record.fab_order
        tier = get_fixed_tier(self.stage)
        if tier is not None:
            fab_order_to_set = tier
            logger.info(
                f"Job {self.job_id}-{self.release} moving to fixed tier {tier} "
                f"stage '{self.stage}'. Will set fab_order from "
                f"{old_fab_order_for_update} to {fab_order_to_set}"
            )
        elif self.stage == "Welded QC" and old_stage_group != "READY_TO_SHIP":
            # Department handoff: Fab → Paint. Land at the back of the paint
            # deck so the fresh arrival doesn't jump the line on existing
            # Welded QC / Paint Start work. Tiers 1-2 are reserved, so floor
            # the max at 2 — minimum result is 3.
            from sqlalchemy import func, or_
            current_max = db.session.query(func.max(Releases.fab_order)).filter(
                Releases.stage.in_(["Welded QC", "Paint Start"]),
                Releases.fab_order.isnot(None),
                Releases.is_archived != True,  # noqa: E712
                or_(
                    Releases.job != self.job_id,
                    Releases.release != self.release,
                ),
            ).scalar()
            base = current_max if current_max is not None and current_max >= 2 else 2
            fab_order_to_set = base + 1
            logger.info(
                f"Job {self.job_id}-{self.release} crossing Fab→R2S into Welded QC. "
                f"Will set fab_order from {old_fab_order_for_update} to {fab_order_to_set} "
                f"(max(WQC+PaintStart)={current_max})"
            )

        # Apply stage + stage_group
        job_record.stage = self.stage
        job_record.stage_group = new_stage_group

        extras: dict = {}

        # job_comp cascade. Linked events get `parent_event_id` so the undo
        # endpoint can find them and bundle their reverts with the parent's.
        if self.stage == 'Complete':
            current_job_comp = (job_record.job_comp or '').strip().upper()
            if current_job_comp != 'X':
                old_jc = job_record.job_comp
                job_record.job_comp = 'X'
                JobEventService.create_and_close(
                    job=self.job_id, release=self.release,
                    action='updated', source=self.source,
                    payload={
                        'field': 'job_comp',
                        'old_value': old_jc,
                        'new_value': 'X',
                        'reason': 'stage_set_to_complete',
                        'parent_event_id': event.id,
                    },
                )
                extras['job_comp'] = 'X'
        elif old_stage == 'Complete' and self.stage != 'Complete':
            current_job_comp = (job_record.job_comp or '').strip().upper()
            if current_job_comp == 'X':
                old_jc = job_record.job_comp
                job_record.job_comp = None
                JobEventService.create_and_close(
                    job=self.job_id, release=self.release,
                    action='updated', source=self.source,
                    payload={
                        'field': 'job_comp',
                        'old_value': old_jc,
                        'new_value': None,
                        'reason': 'stage_changed_from_complete',
                        'parent_event_id': event.id,
                    },
                )
                extras['job_comp'] = None

        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source_of_update

        # Complete is terminal — fab_order is always NULL.
        if self.stage == 'Complete' and old_fab_order_for_update is not None:
            payload_from = (
                None if (isinstance(old_fab_order_for_update, float) and math.isnan(old_fab_order_for_update))
                else old_fab_order_for_update
            )
            fab_order_event = JobEventService.create(
                job=self.job_id,
                release=self.release,
                action='update_fab_order',
                source=self.source,
                payload={
                    'from': payload_from,
                    'to': None,
                    'reason': 'stage_change_complete_clears_fab_order',
                    'parent_event_id': event.id,
                },
            )
            if fab_order_event is None:
                logger.warning(
                    f"Event already exists for fab_order clear on job "
                    f"{self.job_id}-{self.release}"
                )
            else:
                job_record.fab_order = None
                JobEventService.close(fab_order_event.id)
                extras['fab_order'] = None

        # fab_order auto-assign for fixed-tier stages
        if fab_order_to_set is not None and fab_order_to_set != old_fab_order_for_update:
            payload_from = (
                None if (isinstance(old_fab_order_for_update, float) and math.isnan(old_fab_order_for_update))
                else old_fab_order_for_update
            )
            payload_to = (
                None if (isinstance(fab_order_to_set, float) and math.isnan(fab_order_to_set))
                else fab_order_to_set
            )
            fab_order_event = JobEventService.create(
                job=self.job_id,
                release=self.release,
                action='update_fab_order',
                source=self.source,
                payload={
                    'from': payload_from,
                    'to': payload_to,
                    'reason': 'stage_change_unified',
                    'parent_event_id': event.id,
                },
            )
            if fab_order_event is None:
                logger.warning(
                    f"Event already exists for fab_order update on job "
                    f"{self.job_id}-{self.release}"
                )
            else:
                job_record.fab_order = fab_order_to_set
                JobEventService.close(fab_order_event.id)
                extras['fab_order'] = fab_order_to_set

        # Trello outbox — push only when the DB stage's forward-mapped Trello list
        # actually differs from the card's current list. This avoids redundant API
        # calls and bounce-back webhooks for same-zone moves (e.g. Welded QC →
        # Paint Start, both forward-mapping to "Fit Up Complete."). Hold is a pause
        # that never moves the card.
        from app.trello.list_mapper import TrelloListMapper

        outbox_item_created = False
        new_list_id = None
        target_list = None
        is_hold = self.stage == "Hold"

        if is_hold:
            should_push = False
        else:
            target_list = TrelloListMapper.DB_STAGE_TO_TRELLO_LIST.get(self.stage)
            should_push = (
                target_list is not None
                and target_list != job_record.trello_list_name
            )
            if should_push:
                try:
                    from app.brain.job_log.routes import get_list_id_by_stage
                    new_list_id = get_list_id_by_stage(self.stage)
                except Exception:
                    new_list_id = None

        if should_push and new_list_id and job_record.trello_card_id:
            try:
                OutboxService.add(
                    destination='trello',
                    action='move_card',
                    event_id=event.id,
                )
                outbox_item_created = True
                logger.info(
                    f"Outbox item created for Trello list move "
                    f"(job {self.job_id}-{self.release}, stage={self.stage}, "
                    f"target_list={target_list})"
                )
            except Exception as outbox_error:
                logger.error(
                    f"Failed to create outbox for event {event.id}: {outbox_error}",
                    exc_info=True,
                )
        else:
            if is_hold:
                logger.info(
                    "Skipping Trello push for Hold transition — card stays on its current list",
                    extra={'job': self.job_id, 'release': self.release},
                )
            elif target_list is None:
                logger.info(
                    "Skipping Trello push — stage has no forward-mapped Trello list",
                    extra={'job': self.job_id, 'release': self.release, 'stage': self.stage},
                )
            elif not should_push:
                logger.info(
                    "Skipping Trello push — target list matches current list",
                    extra={
                        'job': self.job_id, 'release': self.release,
                        'stage': self.stage,
                        'current_list': job_record.trello_list_name,
                        'target_list': target_list,
                    },
                )
            elif not new_list_id:
                logger.warning(
                    f"Could not resolve Trello list ID for stage '{self.stage}' "
                    f"(target_list={target_list}), skipping Trello update",
                    extra={'job': self.job_id, 'release': self.release, 'stage': self.stage},
                )
            elif not job_record.trello_card_id:
                logger.warning(
                    f"Job {self.job_id}-{self.release} has no trello_card_id, "
                    f"skipping Trello update",
                    extra={'job': self.job_id, 'release': self.release},
                )

        if not outbox_item_created:
            JobEventService.close(event.id)

        db.session.commit()

        if not self.defer_cascade:
            try:
                from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling
                recalculate_all_jobs_scheduling(stage_group='FABRICATION')
            except Exception as cascade_err:
                logger.error(
                    f"Scheduling cascade failed after stage change for "
                    f"{self.job_id}-{self.release}: {cascade_err}",
                    exc_info=True,
                )

        logger.info(
            "update_stage completed successfully",
            extra={'job': self.job_id, 'release': self.release, 'event_id': event.id},
        )

        return StageUpdateResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            stage=self.stage,
            extras=extras,
        )
