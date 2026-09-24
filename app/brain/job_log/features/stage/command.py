"""
@milehigh-header
schema_version: 1
purpose: Encapsulate the full stage update workflow (DB write, stage_group sync, fab_order auto-assign, job_comp cascade, outbox queuing, scheduling recalc) as a single command object.
exports:
  UpdateStageCommand: Dataclass command that executes a stage update with all side effects
  StageUpdateResult: Dataclass result with event_id, job_comp/fab_order extras
imports_from: [app.models, app.services.outbox_service, app.services.job_event_service, app.api.helpers, app.brain.job_log.scheduling.service, app.brain.job_log.features.fab_order.tier, app.brain.job_log.features.start_install.neutralize_install_date_cascade, app.brain.job_log.features.start_install.asap_drop, app.brain.job_log.features.start_install.shipping_stage_date_discipline]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - fab_order re-tiering is delegated to features/fab_order/tier.py, shared with the Trello sync and job_comp paths
  - Setting stage='Complete' cascades job_comp='X'; leaving Complete clears job_comp='X'
  - Paint Complete + hard start_install auto-rolls to Ship Planning (N5; generalizes ASAP intercept)
  - Ship Planning / Ship Complete apply N5 formula-date blanking only; a hard date keeps its color there (BUG-11)
  - A transition into `Install Start` or later dumps a hard date's color (COLOR_DUMP_STAGES);
    the date itself is kept — ASAP rows included, since ASAP no longer stamps a date
  - Deduplicated events raise ValueError (event_exists); caller decides whether to treat as success
  - Scheduling recalculation failure is logged but does not roll back the update
  - parent_event_id links this stage change to the event that caused it, so the undo endpoint
    reverts both halves of a single gesture as one bundle (mirrors AssignInstallerCommand)
  - Department photo gate (T13): a forward stage_group crossing owes a photo tagged with the
    destination's entry stage (features/stage/gate.py) or a gate_exception_note; the requested
    stage is what is checked, before the N5 intercept; undo never gates; the outcome is recorded
    on the stage event as `gate` / `gate_exception`
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

from app.models import Releases, db
from app.services.job_event_service import JobEventService
from app.services.outbox_service import OutboxService
from app.logging_config import get_logger
from app.api.helpers import GATE_ENTRY_STAGE
from app.brain.job_log.features.stage.gate import (  # noqa: F401 — StagePhotoRequiredError re-exported for routes/tests
    StagePhotoRequiredError,
    gate_photo_exists,
    gate_stage_for,
)
from app.brain.job_log.features.fab_order.tier import apply_fab_order_for_stage
from app.brain.job_log.features.start_install.neutralize_install_date_cascade import (
    neutralize_install_date_cascade,
    COLOR_DUMP_STAGES,
    reason_for_stage,
)
from app.brain.job_log.features.start_install.asap_drop import drop_asap_on_completion
from app.brain.job_log.features.start_install.shipping_stage_date_discipline import (
    apply_shipping_stage_date_discipline,
)

logger = get_logger(__name__)


# Master switch for the department photo gate. ON since 2026-09-23 (T13): every
# forward department crossing — Fab → Paint, Paint → Ship, Ship → Install — owes
# a handoff photo or a written reason there is none. Built 2026-06-07 behind
# this flag and never deployed (timing, not a defect); the rule now comes from
# the stage_group axis (features/stage/gate.py) instead of a hand-kept set. The
# frontend pre-opens the gate dialog from the same rule (utils/stageGroups.js);
# this check is the authoritative one. Flip to False to disarm without a deploy
# of anything else.
STAGE_PHOTO_GATE_ENABLED = True

# Kept for readers and tests that ask "which stages are gated": the entry stage
# of every gated department. Derived, never edited by hand.
STAGE_PHOTO_GATES = frozenset(GATE_ENTRY_STAGE.values())


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
    # Actor outside the users table (a subcontractor account changes stage as
    # "sub:<id>"); stamped on the primary event and its job_comp cascade rows.
    external_user_id: Optional[str] = None
    # When set, merged into the primary event payload as `undone_event_id`. Used by the
    # /brain/events/<id>/undo endpoint to (a) link the undo event back to its source for
    # audit trail rendering and (b) perturb the dedup hash so undo-the-undo within the
    # 30s bucket doesn't collide with the original event.
    undone_event_id: Optional[int] = None
    # Set when this stage change is one half of a larger action rather than something the user
    # asked for directly — today, the Ship Planning roll that follows a first hard Start install
    # date (features/start_install/ship_planning_roll.py). The undo endpoint collects events
    # carrying a parent_event_id and reverts the whole bundle, so linking here is what keeps
    # undoing the date from leaving the release stranded in the stage the date put it in.
    parent_event_id: Optional[int] = None
    # The "no photos available" exit from the department gate: a written reason the
    # handoff has no photo. Satisfies the gate in place of a tagged photo and is kept
    # on the stage event (`gate_exception`) so the trail says why the proof is words.
    # Ignored when the transition owes no gate.
    gate_exception_note: Optional[str] = None

    def execute(self) -> StageUpdateResult:
        from app.api.helpers import get_stage_group_from_stage

        job_record: Releases = Releases.resolve(self.job_id, self.release)
        if not job_record:
            logger.debug("job_not_found", job=self.job_id, release=self.release)
            raise ValueError(f"Job {self.job_id}-{self.release} not found")

        old_stage = job_record.stage if job_record.stage else 'Released'

        # Department photo gate (T13): a forward crossing between stage groups owes a
        # photo tagged with the destination department's entry stage, or a written
        # reason there is none. Checked against the REQUESTED stage, before the N5
        # intercept below, so "Paint Complete" still demands its photo even when it
        # gets rerouted to Ship Planning. Skipped on undo (restoring a prior valid
        # state). Inbound Trello list moves never come through here — that bypass is
        # recorded on the roadmap (T13, Open question 6) and dies with T4.
        gate_stage = None
        gate_note = (self.gate_exception_note or '').strip() or None
        if STAGE_PHOTO_GATE_ENABLED and self.undone_event_id is None:
            gate_stage = gate_stage_for(old_stage, self.stage)
        if gate_stage is not None and gate_note is None:
            if not gate_photo_exists(job_record.id, gate_stage):
                logger.debug(
                    "stage_gate_blocked",
                    job=self.job_id,
                    release=self.release,
                    stage=gate_stage,
                    requested_stage=self.stage,
                )
                raise StagePhotoRequiredError(gate_stage, requested_stage=self.stage)

        # Paint Complete intercept (N5): hard start_install OR ASAP rips the release
        # straight to Ship Planning (widens the earlier ASAP-only intercept). Override
        # self.stage so stage_group / fab_order / Trello target Ship Planning. Payload
        # keeps `via: 'Paint Complete'` plus intercept flags for audit. One event, one move.
        event_payload = {'from': old_stage, 'to': self.stage}
        has_hard_install = (
            job_record.start_install_formulaTF is False
            and job_record.start_install is not None
        )
        was_asap = bool(getattr(job_record, 'start_install_asap', False))
        if (
            self.stage == 'Paint Complete'
            and (has_hard_install or was_asap)
            and old_stage != 'Ship Planning'
        ):
            self.stage = 'Ship Planning'
            event_payload = {
                'from': old_stage,
                'to': 'Ship Planning',
                'via': 'Paint Complete',
            }
            if has_hard_install:
                event_payload['hard_date_intercepted'] = True
            if was_asap:
                event_payload['asap_intercepted'] = True

        # The gate's trail lives on the stage event itself: which handoff was owed and
        # whether words stood in for the photo. Absent when nothing was owed.
        if gate_stage is not None:
            event_payload['gate'] = gate_stage
            if gate_note is not None:
                event_payload['gate_exception'] = gate_note

        if self.undone_event_id is not None:
            event_payload['undone_event_id'] = self.undone_event_id
        if self.parent_event_id is not None:
            event_payload['parent_event_id'] = self.parent_event_id

        event = JobEventService.create(
            job=self.job_id,
            release=self.release,
            action='update_stage',
            source=self.source,
            payload=event_payload,
            external_user_id=self.external_user_id,
        )
        if event is None:
            logger.debug(
                "stage_update_deduplicated",
                job=self.job_id,
                release=self.release,
                to_stage=self.stage,
            )
            raise ValueError("Event already exists")

        old_stage_group = job_record.stage_group
        new_stage_group = get_stage_group_from_stage(self.stage)
        logger.debug(
            "stage_group_resolved",
            job=self.job_id,
            release=self.release,
            old_stage_group=old_stage_group,
            new_stage_group=new_stage_group,
            from_stage=old_stage,
            to_stage=self.stage,
        )

        # Apply stage + stage_group
        job_record.stage = self.stage
        job_record.stage_group = new_stage_group

        extras: dict = {}

        # ASAP drop once install begins: when an ASAP release reaches Install Start or any
        # later stage it is no longer a rush, so the flag comes off. Ship Planning / Ship
        # Complete keep it — the ASAP must persist in the ship lanes. The dates set while
        # it was a rush are LEFT intact — the PM owns the install date from then on.
        #
        # The rule lives in its own module rather than inline here because this command
        # is NOT the only writer that advances a stage (the Install Prog route calls it
        # too). Same shape as BUG-9's fab_order and BUG-16's drafting-status drop: one
        # rule, every writer calls it.
        if drop_asap_on_completion(
            job_record,
            new_stage=self.stage,
            parent_event_id=event.id,
            source=self.source,
        ):
            extras['asap_dropped'] = True

        # job_comp cascade. 'Install Complete' and 'Complete' form a single
        # "complete zone" for the Install Prog marker (job_comp='X'): entering
        # the zone sets 'X', moving within it (Install Complete <-> Complete)
        # keeps 'X', and leaving it clears 'X'. Note the asymmetry on the reverse
        # path: 'X' in Install Prog only ever implies 'Install Complete' (see the
        # update_job_comp route) — it never pushes a release to 'Complete'.
        # Linked events get `parent_event_id` so the undo endpoint can find them
        # and bundle their reverts with the parent's.
        COMPLETE_ZONE = ('Install Complete', 'Complete')
        if self.stage in COMPLETE_ZONE:
            current_job_comp = (job_record.job_comp or '').strip().upper()
            if current_job_comp != 'X':
                old_jc = job_record.job_comp
                job_record.job_comp = 'X'
                JobEventService.create_and_close(
                    job=self.job_id, release=self.release,
                    action='updated', source=self.source,
                    external_user_id=self.external_user_id,
                    payload={
                        'field': 'job_comp',
                        'old_value': old_jc,
                        'new_value': 'X',
                        'reason': (
                            'stage_set_to_install_complete'
                            if self.stage == 'Install Complete'
                            else 'stage_set_to_complete'
                        ),
                        'parent_event_id': event.id,
                    },
                )
                extras['job_comp'] = 'X'
        elif old_stage in COMPLETE_ZONE and self.stage not in COMPLETE_ZONE:
            current_job_comp = (job_record.job_comp or '').strip().upper()
            if current_job_comp == 'X':
                old_jc = job_record.job_comp
                job_record.job_comp = None
                JobEventService.create_and_close(
                    job=self.job_id, release=self.release,
                    action='updated', source=self.source,
                    external_user_id=self.external_user_id,
                    payload={
                        'field': 'job_comp',
                        'old_value': old_jc,
                        'new_value': None,
                        'reason': (
                            'stage_changed_from_install_complete'
                            if old_stage == 'Install Complete'
                            else 'stage_changed_from_complete'
                        ),
                        'parent_event_id': event.id,
                    },
                )
                extras['job_comp'] = None

        # Install-date neutralize: once install has started, KEEP the install date but strip
        # its color (and any ASAP red) so it stops showing as an alarming red/green/yellow
        # date. No-op when no hard date is present.
        #
        # BUG-11: the trigger is a transition whose DESTINATION is `Install Start` or any
        # later stage — not the ship stages, which used to wash it here far too early, and
        # never the `start_install` date arriving. Matching the whole tail rather than just
        # `Install Start` is deliberate: a release can jump Ship Planning -> `Complete` and
        # skip `Install Start` entirely.
        if self.stage in COLOR_DUMP_STAGES:
            if neutralize_install_date_cascade(
                job_record,
                parent_event_id=event.id,
                reason=reason_for_stage(self.stage),
                source=self.source,
            ):
                extras['hard_date_cleared'] = True

        # N5 shipping-stage date discipline: at Ship Planning / Ship Complete, blank
        # stale formula dates (locked against re-estimation) or wash hard-date color.
        # Independent of the complete-zone job_comp cascade above.
        shipping_extras = apply_shipping_stage_date_discipline(
            job_record,
            parent_event_id=event.id,
            stage=self.stage,
            source=self.source,
        )
        extras.update(shipping_extras)

        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = self.source_of_update

        # fab_order re-tiering. One rule set, shared with the Trello inbound sync
        # and the job_comp routes — see features/fab_order/tier.py (BUG-9).
        fab_order_plan = apply_fab_order_for_stage(
            job_record,
            self.stage,
            old_stage_group,
            source=self.source,
            parent_event_id=event.id,
            stage_reason='stage_change_unified',
        )
        if fab_order_plan is not None:
            extras['fab_order'] = fab_order_plan.fab_order

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
                logger.debug(
                    "stage_outbox_queued",
                    job=self.job_id,
                    release=self.release,
                    stage=self.stage,
                    target_list=target_list,
                )
            except Exception as outbox_error:
                logger.error(
                    "stage_outbox_failed",
                    job=self.job_id,
                    release=self.release,
                    event_id=event.id,
                    error=str(outbox_error),
                    error_type=type(outbox_error).__name__,
                    exc_info=True,
                )
        else:
            if is_hold:
                logger.debug(
                    "stage_trello_skipped_hold",
                    job=self.job_id,
                    release=self.release,
                )
            elif target_list is None:
                logger.debug(
                    "stage_trello_skipped_no_mapping",
                    job=self.job_id,
                    release=self.release,
                    stage=self.stage,
                )
            elif not should_push:
                logger.debug(
                    "stage_trello_skipped_same_list",
                    job=self.job_id,
                    release=self.release,
                    stage=self.stage,
                    current_list=job_record.trello_list_name,
                    target_list=target_list,
                )
            elif not new_list_id:
                logger.warning(
                    "stage_trello_list_unresolved",
                    job=self.job_id,
                    release=self.release,
                    stage=self.stage,
                    target_list=target_list,
                )
            elif not job_record.trello_card_id:
                logger.debug(
                    "trello_push_skipped_no_card",
                    job=self.job_id,
                    release=self.release,
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
                    "scheduling_recalc_failed",
                    job=self.job_id,
                    release=self.release,
                    error=str(cascade_err),
                    error_type=type(cascade_err).__name__,
                    exc_info=True,
                )

        logger.info(
            "stage_updated",
            release_id=job_record.id,
            job=self.job_id,
            release=self.release,
            event_id=event.id,
            from_stage=old_stage,
            to_stage=self.stage,
        )

        return StageUpdateResult(
            job_id=self.job_id,
            release=self.release,
            event_id=event.id,
            stage=self.stage,
            extras=extras,
        )
