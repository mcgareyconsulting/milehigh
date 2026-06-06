"""
@milehigh-header
schema_version: 1
purpose: Processes inbound Trello webhooks by reconciling card changes (moves, edits, due-date updates) with the DB and creating JobEvents for the audit trail.
exports:
  sync_from_trello: Main webhook handler that fetches card data, updates the Job record, and emits JobEvents.
imports_from: [app.trello.api, app.trello.utils, app.trello.operations, app.trello.context, app.trello.logging, app.trello.list_mapper, app.models, app.services.job_event_service, app.config]
imported_by: [app/trello/__init__.py]
invariants:
  - Echo webhooks from Brain's own outbox calls are detected and skipped (90-second window, content-matched).
  - All DB changes are committed only after JobEvents are created; on failure the context manager rolls back everything.
  - Duplicate events (same or older timestamp) are silently dropped.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""

from numpy import safe_eval
import openpyxl
import pandas as pd
from pandas import Timestamp
import math
from app.trello.utils import (
    extract_card_name,
    extract_identifier,
    parse_trello_datetime,
    calculate_business_days_before,
    should_sort_list_by_fab_order,
    sort_list_if_needed,
)
from app.trello.api import (
    get_trello_card_by_id,
    get_list_name_by_id,
    get_list_by_name,
    update_trello_card,
    add_comment_to_trello_card,
    parse_num_guys_from_description,
    update_installation_duration_in_description,
    update_num_guys_in_description,
    update_trello_card_description,
    update_card_custom_field_number,
    set_mirror_date_range,
    sync_num_guys_on_card,
    set_num_guys_in_description,
)
from app.models import Releases, SyncOperation, SyncLog, SyncStatus, ReleaseEvents, TrelloOutbox, db
from datetime import datetime, date, timezone, time, timedelta
from zoneinfo import ZoneInfo
from app.logging_config import get_logger, SyncContext, log_sync_operation
from app.services.job_event_service import JobEventService
import uuid
import re
from app.config import Config as cfg

from app.trello.operations import create_sync_operation, update_sync_operation
from app.trello.context import sync_operation_context
from app.trello.logging import safe_log_sync_event, safe_sync_op_call
from app.trello.list_mapper import TrelloListMapper
logger = get_logger(__name__)


def check_database_connection():
    """Check if database connection is working."""
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning("Database connection check failed", error=str(e))
        return False

def compare_timestamps(event_time, source_time, operation_id: str):
    """Compare external event timestamp with database record timestamp."""
    if not event_time:
        logger.warning("Invalid event_time (None)", operation_id=operation_id)
        return None

    if not source_time:
        logger.info("No DB timestamp — treating event as newer", operation_id=operation_id)
        return "newer"

    if event_time > source_time:
        logger.info("Event is newer than DB record", operation_id=operation_id)
        return "newer"
    else:
        logger.info("Event is older than DB record", operation_id=operation_id)
        return "older"

def as_date(val):
    if pd.isna(val) or val is None:
        return None
    # Handle pd.Timestamp, datetime, date, string, etc.
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    # Try parsing string
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


def _is_brain_echo_webhook(rec, event_info):
    """
    True if webhook is the echo of our own Brain->Trello API call for this card.
    Cross-references Outbox by card (job/release) and change content to avoid
    skipping legitimate user changes (e.g. Brain moves to A, user moves to B).
    """
    if rec.source_of_update != "Brain":
        return False
    last_updated = rec.last_updated_at.replace(tzinfo=None) if rec.last_updated_at else None
    if not last_updated or (datetime.utcnow() - last_updated).total_seconds() >= 90:
        return False

    # Find recently completed Trello outbox for this card (job/release)
    cutoff = datetime.utcnow() - timedelta(seconds=90)
    recent_outbox = (
        db.session.query(TrelloOutbox)
        .join(ReleaseEvents, TrelloOutbox.event_id == ReleaseEvents.id)
        .filter(
            ReleaseEvents.job == rec.job,
            ReleaseEvents.release == rec.release,
            TrelloOutbox.destination == "trello",
            TrelloOutbox.status == "completed",
            TrelloOutbox.completed_at >= cutoff,
        )
        .order_by(TrelloOutbox.completed_at.desc())
        .first()
    )
    if not recent_outbox or not recent_outbox.event:
        return False

    # Content match: only skip if webhook change matches what we sent
    our_action = recent_outbox.action
    our_payload = recent_outbox.event.payload or {}

    if our_action == "move_card":
        if not event_info.get("has_list_move"):
            return False
        our_dest = our_payload.get("to")  # stage/list name
        webhook_dest = event_info.get("to")  # list name from listAfter
        return our_dest == webhook_dest

    # update_fab_order, update_notes: don't produce updateCard list_move webhooks
    return False


def _apply_num_guys_change(rec, new_num_guys, *, source, trello_user_id=None):
    """Persist a num_guys change and recompute comp_eta from it.

    num_guys drives install duration, so a change re-stretches the install bar from a
    FIXED start_install (the start never moves): comp_eta = start_install + duration(
    install_hrs, num_guys). The new comp_eta is written to the release and pushed to the
    mirror card's due (the bar end). Only hard-dated releases recompute here — formula-driven
    rows get their comp_eta from the scheduling engine, which already reads rec.num_guys.

    Mutates rec and emits events but does NOT commit (the caller commits). Returns True if
    anything changed.
    """
    if not new_num_guys or new_num_guys <= 0:
        return False

    changed = False
    if rec.num_guys != new_num_guys:
        rec.num_guys = new_num_guys
        changed = True
        # DB is the source of truth: push the canonical value to BOTH cards so the primary
        # and mirror never disagree. The triggering card is already correct (no-op push);
        # the resulting echo webhook re-parses the same value and no-ops.
        for cid in (rec.trello_card_id, rec.mirror_trello_card_id):
            if cid:
                try:
                    sync_num_guys_on_card(cid, rec.install_hrs, new_num_guys)
                except Exception as e:
                    logger.error(
                        f"num_guys change: failed to sync card {cid} for "
                        f"{rec.job}-{rec.release}: {e}", exc_info=True,
                    )

    if rec.start_install is not None and rec.start_install_formulaTF is False:
        from app.brain.job_log.scheduling.calculator import calculate_install_complete_date
        new_comp_eta = calculate_install_complete_date(
            rec.start_install, rec.install_hrs, new_num_guys
        )
        if new_comp_eta != rec.comp_eta:
            old_comp_eta = rec.comp_eta
            rec.comp_eta = new_comp_eta
            changed = True
            JobEventService.create_and_close(
                job=rec.job, release=rec.release,
                action="updated", source=source,
                payload={
                    "field": "comp_eta",
                    "old_value": old_comp_eta.isoformat() if old_comp_eta else None,
                    "new_value": new_comp_eta.isoformat() if new_comp_eta else None,
                    "reason": "num_guys_changed",
                    "num_guys": new_num_guys,
                },
                external_user_id=trello_user_id,
            )
            # Push the new bar end to the mirror card (start unchanged). Best-effort; the
            # resulting due webhook is a no-op echo (DB already == card).
            if rec.trello_card_id:
                try:
                    set_mirror_date_range(rec.trello_card_id, rec.start_install, new_comp_eta)
                except Exception as e:
                    logger.error(
                        f"num_guys change: failed to update mirror bar for "
                        f"{rec.job}-{rec.release}: {e}", exc_info=True,
                    )
    return changed


def _handle_mirror_writeback(card_id, card_data, event_info, sync_op):
    """If `card_id` is a tracked mirror card, apply its changes back to the release and
    return True. Returns False when the card isn't a known mirror.

    The mirror card is the installer-team editing surface:
      - sliding `start`/`due` writes start_install/comp_eta back VERBATIM, and
      - editing "Number of Guys" in the description recomputes comp_eta (the bar end) from
        the fixed start_install.
    A value-diff guard makes Brain's own pushes no-op echoes; outbound pushes target only the
    primary due / the mirror due, so there is no inbound loop.
    """
    mirror_rec = Releases.query.filter_by(mirror_trello_card_id=card_id).one_or_none()
    if not mirror_rec:
        return False

    change_types = event_info.get("change_types", [])
    trello_user_id = event_info.get("trello_user_id")
    event_time = parse_trello_datetime(event_info.get("time")) or datetime.utcnow()
    changed = False

    # 1) Date slides -> verbatim write-back.
    if "start_date_change" in change_types or "due_date_change" in change_types:
        new_start = parse_trello_datetime(card_data["start"]) if card_data.get("start") else None
        new_due = parse_trello_datetime(card_data["due"]) if card_data.get("due") else None
        new_start_date = new_start.date() if isinstance(new_start, datetime) else new_start
        new_due_date = new_due.date() if isinstance(new_due, datetime) else new_due

        cur_start = mirror_rec.start_install
        cur_due = mirror_rec.comp_eta
        start_changed = new_start_date is not None and new_start_date != cur_start
        due_changed = new_due_date is not None and new_due_date != cur_due

        if start_changed:
            old_start = cur_start
            # Verbatim: the mirror start becomes a hard start_install (normal color).
            mirror_rec.start_install = new_start_date
            mirror_rec.start_install_formula = None
            mirror_rec.start_install_formulaTF = False
            mirror_rec.start_install_no_color = False
            JobEventService.create_and_close(
                job=mirror_rec.job, release=mirror_rec.release,
                action="update_start_install", source="Trello",
                payload={
                    "from": old_start.isoformat() if old_start else None,
                    "to": new_start_date.isoformat(),
                    "is_hard_date": True,
                    "via": "mirror_card",
                },
                external_user_id=trello_user_id,
            )
            changed = True
            # Realign the primary card due to the new start_install.
            if mirror_rec.trello_card_id:
                try:
                    update_trello_card(
                        card_id=mirror_rec.trello_card_id,
                        new_due_date=new_start_date,
                        clear_due_date=False,
                    )
                except Exception as e:
                    logger.error(
                        f"Mirror writeback: failed to realign primary due for "
                        f"{mirror_rec.job}-{mirror_rec.release}: {e}", exc_info=True,
                    )

        if due_changed:
            old_due = cur_due
            mirror_rec.comp_eta = new_due_date
            JobEventService.create_and_close(
                job=mirror_rec.job, release=mirror_rec.release,
                action="updated", source="Trello",
                payload={
                    "field": "comp_eta",
                    "old_value": old_due.isoformat() if old_due else None,
                    "new_value": new_due_date.isoformat(),
                    "via": "mirror_card",
                },
                external_user_id=trello_user_id,
            )
            changed = True

    # 2) num_guys edited in the mirror description -> recompute comp_eta (the bar end).
    if "description_change" in change_types:
        ng = parse_num_guys_from_description(card_data.get("desc", "") or "")
        if _apply_num_guys_change(mirror_rec, ng, source="Trello", trello_user_id=trello_user_id):
            changed = True

    if not changed:
        safe_log_sync_event(
            sync_op.operation_id, "INFO", "Mirror change — no actionable delta (echo or non-date)",
            job=mirror_rec.job, release=mirror_rec.release, card_id=card_id,
        )
        return True

    mirror_rec.last_updated_at = event_time
    mirror_rec.source_of_update = "Trello"
    db.session.commit()

    safe_log_sync_event(
        sync_op.operation_id, "INFO", "Mirror write-back applied",
        job=mirror_rec.job, release=mirror_rec.release,
        start_install=mirror_rec.start_install.isoformat() if mirror_rec.start_install else None,
        comp_eta=mirror_rec.comp_eta.isoformat() if mirror_rec.comp_eta else None,
    )
    return True


def sync_from_trello(event_info):
    """Sync data from Trello to database based on webhook payload."""
    from app.config import Config as cfg
    if event_info is None or not event_info.get("handled"):
        return

    # Extract card id and event time from event info
    card_id = event_info["card_id"]
    event_time = parse_trello_datetime(event_info.get("time"))

    trello_source = "Trello"
    
    # Use context manager - it handles everything!
    with sync_operation_context("trello_webhook", "trello", card_id) as sync_op:
        if sync_op is None:
            # Database unavailable, but we can still try to process
            # (context manager already logged warning)
            return
        
        # Log webhook received (incl. trello_user_id for event attribution)
        safe_log_sync_event(
            sync_op.operation_id,
            "WEBHOOK",
            "Trello webhook received",
            card_id=card_id,
            event_type=event_info.get("event"),
            change_types=event_info.get("change_types", []),
            trello_user_id=event_info.get("trello_user_id"),
        )
        
        # Fetch card data
        card_data = get_trello_card_by_id(card_id)
        if not card_data:
            safe_log_sync_event(sync_op.operation_id, "ERROR", "Card not found in Trello", card_id=card_id)
            raise ValueError(f"Card {card_id} not found in Trello")
        
        # Check if card creation from Excel sync (skip Excel update)
        if event_info.get("event") == "card_created":
            rec = Releases.query.filter_by(trello_card_id=card_id).first()
            if rec and rec.source_of_update == "Excel":
                time_diff = datetime.utcnow() - rec.last_updated_at.replace(tzinfo=None) if rec.last_updated_at else None
                if time_diff and time_diff.total_seconds() < 300:  # 5 minutes
                    event_info["skip_excel_update"] = True
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "Skipping Excel update because card was created from Excel sync",
                        reason="card_from_excel_sync",
                        time_diff_seconds=time_diff.total_seconds()
                    )

        elif event_info.get("event") == "card_updated":
            rec = Releases.query.filter_by(trello_card_id=card_id).first()
            if rec and rec.source_of_update == "Excel":
                time_diff = datetime.utcnow() - rec.last_updated_at.replace(tzinfo=None) if rec.last_updated_at else None
                if time_diff and time_diff.total_seconds() < 120:  # 2 minutes
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "Skipping Excel update because card was updated shortly after Excel sync",
                        reason="card_updated_from_excel_sync",
                        time_diff_seconds=time_diff.total_seconds()
                    )
                    # Just return - context manager will mark as COMPLETED
                    return

        # Find DB record
        rec = Releases.query.filter_by(trello_card_id=card_id).one_or_none()

        if not rec:
            # Not a primary card — it may be a release's mirror (installer-team) card.
            # Mirror start/due edits write back to the release verbatim.
            if _handle_mirror_writeback(card_id, card_data, event_info, sync_op):
                return
            safe_log_sync_event(sync_op.operation_id, "INFO", "No DB record found for card", card_id=card_id)
            # Just return - not an error, card isn't tracked
            return

        # Skip echo webhooks from Brain's own Trello API calls (outbox -> update_trello_card).
        # Cross-reference with Outbox by card (job/release) and change content so we don't
        # skip legitimate user changes (e.g. Brain moves to A, user moves to B).
        if _is_brain_echo_webhook(rec, event_info):
            safe_log_sync_event(
                sync_op.operation_id,
                "INFO",
                "Skipping webhook echo from Brain's Trello API call (matched outbox for card)",
                job=rec.job,
                release=rec.release,
                card_id=card_id,
            )
            return

        # Check for duplicate updates (Trello-originated changes)
        if rec.source_of_update == "Trello" and event_time <= rec.last_updated_at:
            safe_log_sync_event(
                sync_op.operation_id,
                "INFO",
                "Duplicate event detected",
                event_time=event_time.isoformat(),
                db_last_updated=rec.last_updated_at.isoformat()
            )
            return

        # Check if event is newer
        if event_time <= rec.last_updated_at:
            safe_log_sync_event(
                sync_op.operation_id,
                "INFO",
                "Event is older than DB record",
                event_time=event_time.isoformat(),
                db_last_updated=rec.last_updated_at.isoformat()
            )
            return

        # Log DB update starting
        safe_log_sync_event(
            sync_op.operation_id,
            "INFO",
            "DB update started",
            job=rec.job,
            release=rec.release,
            card_name=card_data.get("name")
        )
        
        # Save old values for comparison and event creation
        old_description = rec.trello_card_description or ""
        old_name = rec.trello_card_name or ""
        old_due_date = rec.trello_card_date
        
        # Track created events to close them after successful update
        created_events = []
        trello_user_id = event_info.get("trello_user_id")
        
        # Create JobEvents for all changes before updating the Job record
        change_types = event_info.get("change_types", [])
        
        # Handle name changes
        if "name_change" in change_types:
            new_name = card_data.get("name", "")
            if new_name != old_name:
                event = JobEventService.create(
                    job=rec.job,
                    release=rec.release,
                    action="update_name",
                    source=trello_source,
                    payload={"from": old_name, "to": new_name},
                    external_user_id=trello_user_id,
                )
                if event:
                    created_events.append(event)
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "JobEvent created for name update",
                        job=rec.job,
                        release=rec.release,
                        event_id=event.id
                    )
        
        # Handle description changes
        if "description_change" in change_types:
            new_description = card_data.get("desc", "") or ""
            if new_description != old_description:
                event = JobEventService.create(
                    job=rec.job,
                    release=rec.release,
                    action="update_description",
                    source=trello_source,
                    payload={"from": old_description, "to": new_description},
                    external_user_id=trello_user_id,
                )
                if event:
                    created_events.append(event)
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "JobEvent created for description update",
                        job=rec.job,
                        release=rec.release,
                        event_id=event.id
                    )
        
        # Handle due date changes
        if "due_date_change" in change_types:
            new_due_date = parse_trello_datetime(card_data["due"]) if card_data.get("due") else None
            # Compare dates (convert datetime to date if needed)
            old_date = old_due_date.date() if isinstance(old_due_date, datetime) else old_due_date
            new_date = new_due_date.date() if isinstance(new_due_date, datetime) else new_due_date
            if old_date != new_date:
                event = JobEventService.create(
                    job=rec.job,
                    release=rec.release,
                    action="update_due_date",
                    source=trello_source,
                    payload={
                        "from": old_due_date.isoformat() if old_due_date else None,
                        "to": new_due_date.isoformat() if new_due_date else None
                    },
                    external_user_id=trello_user_id,
                )
                if event:
                    created_events.append(event)
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "JobEvent created for due date update",
                        job=rec.job,
                        release=rec.release,
                        event_id=event.id
                    )
        
        # Update Trello fields
        rec.trello_card_name = card_data.get("name")
        rec.trello_card_description = card_data.get("desc")
        rec.trello_list_id = card_data.get("idList")
        rec.trello_list_name = get_list_name_by_id(card_data.get("idList"))
        rec.trello_card_date = parse_trello_datetime(card_data["due"]) if card_data.get("due") else None
        rec.last_updated_at = event_time
        rec.source_of_update = "Trello"

        # Handle list movement
        if event_info.get("has_list_move", False):
            from_list_name = event_info.get("from")
            to_list_name = rec.trello_list_name
            from_list_id = event_info.get("list_id_before")
            to_list_id = event_info.get("list_id_after")
            
            safe_log_sync_event(
                sync_op.operation_id,
                "INFO",
                "List move detected",
                from_list=from_list_name,
                to_list=to_list_name
            )
            
            # Capture old stage value before applying list mapping
            old_stage_before_list_move = rec.stage

            # Apply list mapping to database. Returns True only if the rank gate
            # actually advanced rec.stage; False means the inbound was skipped
            # (echo of our own push, backward Trello drag, or DB already at/ahead
            # of the inbound list zone).
            applied = TrelloListMapper.apply_trello_list_to_db(
                rec, rec.trello_list_name, sync_op.operation_id
            )

            if applied:
                # Use to_list_name as the stage name to match frontend format
                stage = to_list_name
                # Use from_list_name from webhook for "from" value (more reliable
                # than DB stage); fall back to old DB stage if unavailable.
                from_stage = (
                    from_list_name
                    if from_list_name
                    else (old_stage_before_list_move if old_stage_before_list_move else None)
                )

                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "Creating stage update event for list move",
                    job=rec.job,
                    release=rec.release,
                    from_list=from_list_name,
                    to_list=to_list_name,
                    old_stage=old_stage_before_list_move,
                    new_stage=stage,
                )

                event = JobEventService.create(
                    job=rec.job,
                    release=rec.release,
                    action="update_stage",
                    source=trello_source,
                    payload={"from": from_stage, "to": stage},
                    external_user_id=trello_user_id,
                )
                if event:
                    created_events.append(event)
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "JobEvent created for stage update",
                        job=rec.job,
                        release=rec.release,
                        from_list=from_list_name,
                        to_stage=stage,
                        event_id=event.id,
                    )
                else:
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "WARNING",
                        "Duplicate stage update event detected, skipping",
                        job=rec.job,
                        release=rec.release,
                        from_list=from_list_name,
                        to_list=to_list_name,
                        payload_from=from_stage,
                        payload_to=stage,
                    )
            else:
                # Rank gate skipped the apply — DB stage was not advanced. No
                # phantom update_stage event is recorded; the audit trail stays
                # honest. The skip itself is logged inside apply_trello_list_to_db.
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "Skipping JobEvent — inbound Trello list move did not advance DB stage",
                    job=rec.job,
                    release=rec.release,
                    from_list=from_list_name,
                    to_list=to_list_name,
                    db_stage=old_stage_before_list_move,
                )
            
            # Sort both source and destination lists by Fab Order (only for target lists)
            if cfg.FAB_ORDER_FIELD_ID:
                # Sort destination list (where card was moved to)
                destination_list_id = event_info.get("list_id_after")
                if destination_list_id:
                    sort_list_if_needed(
                        destination_list_id,
                        cfg.FAB_ORDER_FIELD_ID,
                        sync_op.operation_id,
                        "destination"
                    )
                
                # Sort source list (where card was moved from)
                source_list_id = event_info.get("list_id_before")
                if source_list_id:
                    sort_list_if_needed(
                        source_list_id,
                        cfg.FAB_ORDER_FIELD_ID,
                        sync_op.operation_id,
                        "source"
                    )

        # Handle description changes — keep num_guys (and the derived comp_eta) in sync.
        if event_info.get("has_description_change", False):
            new_description = card_data.get("desc", "") or ""

            # Ensure the Number of Guys field exists, seeded from the DB (the source of truth)
            # so we never clobber a value set on the other card with a default.
            if rec.install_hrs and "Number of Guys:" not in new_description:
                seed = int(rec.num_guys) if rec.num_guys else 2
                updated_description = set_num_guys_in_description(new_description, seed)
                if updated_description != new_description:
                    update_trello_card_description(card_id, updated_description)
                    new_description = updated_description

            # Parse and apply: persists num_guys, recomputes comp_eta, and syncs both cards'
            # Number of Guys / Installation Duration text + the mirror date bar.
            if "Number of Guys:" in new_description:
                num_guys = parse_num_guys_from_description(new_description)
                if _apply_num_guys_change(rec, num_guys, source="Trello", trello_user_id=trello_user_id):
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "num_guys change applied (comp_eta + both cards synced)",
                        num_guys=num_guys,
                        install_hrs=rec.install_hrs,
                    )

        # Commit DB changes
        db.session.add(rec)
        db.session.commit()

        # Close all created events (mark as applied) after successful update
        for event in created_events:
            if event and not event.applied_at:
                JobEventService.close(event.id)
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "JobEvent marked as applied",
                    job=rec.job,
                    release=rec.release,
                    event_id=event.id,
                    action=event.action
                )
        
        # Commit event closures
        if created_events:
            db.session.commit()

        safe_log_sync_event(
            sync_op.operation_id,
            "INFO",
            "DB update completed",
            job=rec.job,
            release=rec.release
        )
        
        # Context manager will automatically:
        # - Mark sync_op as COMPLETED
        # - Calculate duration
        # - Log success
        # If any exception occurs, it will:
        # - Rollback database
        # - Mark sync_op as FAILED
        # - Log error
        # - Re-raise exception

