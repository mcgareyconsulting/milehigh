"""
@milehigh-header
schema_version: 1
purpose: Dispatcher that replays a single stashed cell edit through the normal job-log business logic at stash-session apply time.
exports:
  apply_change: Apply one StashedJobChange to its target Releases row
imports_from: [app.models, app.services.job_event_service, app.services.outbox_service, app.brain.job_log.features.stage.command, app.brain.job_log.features.fab_order.command, app.trello.api]
imported_by: [app/brain/job_log/features/stash/service.py]
invariants:
  - Every path mirrors the matching /update-<field> route minus Flask HTTP concerns
  - JobEventService dedup hits (returns None) are treated as success (state may already be applied)
  - defer_cascade=True is passed to sub-commands; the stash service runs scheduling once at the end
  - applied_at + status are set by the caller on success; on failure this function sets status='failed' + error
"""
from datetime import datetime, date
from typing import Optional

from app.models import Releases, StashedJobChange, db
from app.services.job_event_service import JobEventService
from app.services.outbox_service import OutboxService
from app.logging_config import get_logger

logger = get_logger(__name__)


def apply_change(change: StashedJobChange, source: str = "Brain") -> None:
    """
    Apply a single StashedJobChange by replaying it through normal business logic.

    On success: sets change.status='applied', change.applied_at=now, change.error=None.
    On failure: sets change.status='failed' and change.error to a short reason.

    Does NOT commit — caller manages the transaction boundary.
    """
    record: Optional[Releases] = Releases.query.filter_by(
        job=change.job, release=change.release
    ).first()
    if record is None:
        change.status = 'failed'
        change.error = f'Release {change.job}-{change.release} not found'
        return

    try:
        field = change.field
        new_value = change.new_value

        if field == 'stage':
            _apply_stage(record, new_value, source)
        elif field == 'fab_order':
            _apply_fab_order(record, new_value, source)
        elif field == 'notes':
            _apply_notes(record, new_value, source)
        elif field == 'job_comp':
            _apply_job_comp(record, new_value, source)
        elif field == 'invoiced':
            _apply_invoiced(record, new_value, source)
        elif field == 'start_install':
            _apply_start_install(record, new_value, source)
        else:
            change.status = 'failed'
            change.error = f'Unknown field: {field}'
            return

        change.status = 'applied'
        change.applied_at = datetime.utcnow()
        change.error = None

    except Exception as e:
        logger.error(
            f"Failed to apply stash change {change.id} "
            f"({change.job}-{change.release} {change.field})",
            exc_info=True,
        )
        change.status = 'failed'
        change.error = str(e)[:2000]


# ---- per-field helpers ----

def _apply_stage(record: Releases, new_value, source: str) -> None:
    from app.brain.job_log.features.stage.command import UpdateStageCommand

    stage = new_value
    if not stage:
        raise ValueError("stage is required")

    try:
        UpdateStageCommand(
            job_id=record.job,
            release=record.release,
            stage=stage,
            source=source,
            defer_cascade=True,
        ).execute()
    except ValueError as e:
        # Dedup hit → treat as success; state likely already applied
        if 'already exists' in str(e).lower():
            logger.info(
                f"Stage event deduplicated for {record.job}-{record.release}; "
                f"treating as already applied"
            )
            return
        raise


def _apply_fab_order(record: Releases, new_value, source: str) -> None:
    from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
    import math

    fab_order = new_value
    if fab_order is not None:
        try:
            fab_order = float(fab_order)
            if math.isnan(fab_order):
                fab_order = None
        except (ValueError, TypeError):
            raise ValueError(f"fab_order must be a number, got {new_value!r}")

    try:
        UpdateFabOrderCommand(
            job_id=record.job,
            release=record.release,
            fab_order=fab_order,
            source=source,
            defer_cascade=True,
        ).execute()
    except ValueError as e:
        if 'already exists' in str(e).lower():
            logger.info(
                f"fab_order event deduplicated for {record.job}-{record.release}; "
                f"treating as already applied"
            )
            return
        raise


def _apply_notes(record: Releases, new_value, source: str) -> None:
    notes = '' if new_value is None else str(new_value).strip()

    old_notes = record.notes
    event = JobEventService.create(
        job=record.job,
        release=record.release,
        action='update_notes',
        source=source,
        payload={'from': old_notes, 'to': notes},
    )
    if event is None:
        logger.info(
            f"notes event deduplicated for {record.job}-{record.release}; "
            f"treating as already applied"
        )
        return

    record.notes = notes if notes else None
    record.last_updated_at = datetime.utcnow()
    record.source_of_update = source

    outbox_item_created = False
    if record.trello_card_id and notes:
        try:
            OutboxService.add(
                destination='trello', action='update_notes', event_id=event.id,
            )
            outbox_item_created = True
        except Exception as e:
            logger.error(f"Failed to create notes outbox for event {event.id}: {e}", exc_info=True)

    if not outbox_item_created:
        JobEventService.close(event.id)


def _normalize_short_field(value, max_len=8):
    if value is None:
        return None
    s = str(value).strip()
    return s[:max_len] if s else None


def _apply_job_comp(record: Releases, new_value, source: str) -> None:
    """Mirrors routes.update_job_comp, minus HTTP concerns.

    Cascades stage reversion (if clearing X) or stage='Complete' (if setting X).
    """
    from app.brain.job_log.routes import update_job_stage_fields
    from app.api.helpers import get_stage_group_from_stage
    from app.models import ReleaseEvents

    job_comp_str = _normalize_short_field(new_value)
    if job_comp_str and job_comp_str.upper() != 'X':
        try:
            num = float(job_comp_str.rstrip('%'))
            job_comp_str = f"{num:g}%"
        except ValueError:
            pass

    old_job_comp = record.job_comp
    record.job_comp = job_comp_str
    record.last_updated_at = datetime.utcnow()
    record.source_of_update = source

    JobEventService.create_and_close(
        job=record.job,
        release=record.release,
        action='updated',
        source=source,
        payload={'field': 'job_comp', 'old_value': old_job_comp, 'new_value': job_comp_str},
    )

    old_was_x = old_job_comp and old_job_comp.strip().upper() == 'X'
    new_is_x = job_comp_str and job_comp_str.upper() == 'X'

    if old_was_x and not new_is_x:
        current_stage = record.stage or 'Released'
        if current_stage == 'Complete':
            recent_stage_events = ReleaseEvents.query.filter_by(
                job=record.job, release=record.release, action='update_stage'
            ).order_by(ReleaseEvents.created_at.desc()).limit(20).all()

            revert_stage = 'Released'
            for evt in recent_stage_events:
                if evt.payload.get('to') == 'Complete' and evt.payload.get('from'):
                    revert_stage = evt.payload['from']
                    break

            update_job_stage_fields(record, revert_stage)
            JobEventService.create_and_close(
                job=record.job, release=record.release,
                action='update_stage', source=source,
                payload={'from': 'Complete', 'to': revert_stage, 'reason': 'job_comp_cleared'},
            )

    if new_is_x:
        current_stage = record.stage or 'Released'
        if current_stage != 'Complete':
            update_job_stage_fields(record, 'Complete')
            JobEventService.create_and_close(
                job=record.job, release=record.release,
                action='update_stage', source=source,
                payload={'from': current_stage, 'to': 'Complete', 'reason': 'job_comp_set_to_x'},
            )
        if record.fab_order is not None:
            old_fab = record.fab_order
            record.fab_order = None
            fab_event = JobEventService.create(
                job=record.job, release=record.release,
                action='update_fab_order', source=source,
                payload={'from': old_fab, 'to': None, 'reason': 'job_comp_complete'},
            )
            if fab_event:
                JobEventService.close(fab_event.id)


def _apply_invoiced(record: Releases, new_value, source: str) -> None:
    invoiced_str = _normalize_short_field(new_value)
    if invoiced_str and invoiced_str.upper() != 'X':
        try:
            num = float(invoiced_str.rstrip('%'))
            invoiced_str = f"{num:g}%"
        except ValueError:
            pass

    old_invoiced = record.invoiced
    record.invoiced = invoiced_str
    record.last_updated_at = datetime.utcnow()
    record.source_of_update = source

    JobEventService.create_and_close(
        job=record.job,
        release=record.release,
        action='updated',
        source=source,
        payload={'field': 'invoiced', 'old_value': old_invoiced, 'new_value': invoiced_str},
    )


def _apply_start_install(record: Releases, new_value, source: str) -> None:
    """new_value shape:
        { "action": "set" | "clear",
          "date": "YYYY-MM-DD" | null,
          "is_hard_date": bool }
    """
    from app.trello.api import update_trello_card

    if not isinstance(new_value, dict):
        raise ValueError(f"start_install new_value must be a dict, got {type(new_value).__name__}")

    action = new_value.get('action')
    date_str = new_value.get('date')
    is_hard_date = new_value.get('is_hard_date', True)

    if action == 'clear':
        old_start_install = record.start_install
        event = JobEventService.create(
            job=record.job,
            release=record.release,
            action='clear_hard_date',
            source=source,
            payload={
                'from': old_start_install.isoformat() if old_start_install else None,
                'to': None,
                'cleared_hard_date': True,
            },
        )
        if event is None:
            logger.info(
                f"clear_hard_date event deduplicated for {record.job}-{record.release}; "
                f"treating as already applied"
            )
            return

        record.start_install_formulaTF = True
        record.start_install_formula = None
        record.last_updated_at = datetime.utcnow()
        record.source_of_update = source

        if record.trello_card_id:
            try:
                update_trello_card(
                    card_id=record.trello_card_id,
                    new_due_date=None,
                    clear_due_date=True,
                )
            except Exception as e:
                logger.error(
                    f"Failed to clear Trello due date for {record.job}-{record.release}: {e}",
                    exc_info=True,
                )

        JobEventService.close(event.id)
        return

    # action == 'set' (or default)
    if not is_hard_date:
        logger.info(
            f"Skipping start_install apply for {record.job}-{record.release} — not a hard date"
        )
        return

    start_install_date = None
    if date_str:
        try:
            start_install_date = datetime.strptime(str(date_str).strip(), '%Y-%m-%d').date()
        except ValueError:
            raise ValueError(f"Invalid date format: {date_str!r}, expected YYYY-MM-DD")

    old_start_install = record.start_install
    event = JobEventService.create(
        job=record.job,
        release=record.release,
        action='update_start_install',
        source=source,
        payload={
            'from': old_start_install.isoformat() if old_start_install else None,
            'to': start_install_date.isoformat() if start_install_date else None,
            'is_hard_date': True,
        },
    )
    if event is None:
        logger.info(
            f"start_install event deduplicated for {record.job}-{record.release}; "
            f"treating as already applied"
        )
        return

    record.start_install = start_install_date
    record.start_install_formula = None
    record.start_install_formulaTF = False
    record.last_updated_at = datetime.utcnow()
    record.source_of_update = source

    if record.trello_card_id:
        try:
            update_trello_card(
                card_id=record.trello_card_id,
                new_due_date=start_install_date,
                clear_due_date=(start_install_date is None),
            )
        except Exception as e:
            logger.error(
                f"Failed to update Trello due date for {record.job}-{record.release}: {e}",
                exc_info=True,
            )

    JobEventService.close(event.id)
