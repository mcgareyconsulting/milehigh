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
    update_mirror_card_date_range,
    parse_num_guys_from_description,
    update_installation_duration_in_description,
    parse_installation_duration,
    update_trello_card_description,
    update_card_custom_field_number,
    copy_trello_card,
    link_cards,
    card_has_link_to,
    add_procore_link,
)
from app.models import Job, SyncOperation, SyncLog, SyncStatus, JobEvents, db
from datetime import datetime, date, timezone, time
from zoneinfo import ZoneInfo
from app.sync_lock import synchronized_sync, sync_lock_manager
from app.logging_config import get_logger, SyncContext, log_sync_operation
import uuid
import re
import hashlib
import json
from app.config import Config as cfg
from app.procore.procore import add_procore_link_to_trello_card

from app.sync.db_operations import create_sync_operation, update_sync_operation
from app.sync.context import sync_operation_context
from app.sync.logging import safe_log_sync_event, safe_sync_op_call
from app.sync.services.trello_list_mapper import TrelloListMapper
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
    # Handle pd.Timestamp, datetime, string, etc.
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


def sync_from_trello(event_info):
    """Sync data from Trello to database based on webhook payload."""
    from app.config import Config as cfg
    if event_info is None or not event_info.get("handled"):
        return

    # Extract card id and event time from event info
    card_id = event_info["card_id"]
    event_time = parse_trello_datetime(event_info.get("time"))
    
    # Use context manager - it handles everything!
    with sync_operation_context("trello_webhook", "trello", card_id) as sync_op:
        if sync_op is None:
            # Database unavailable, but we can still try to process
            # (context manager already logged warning)
            return
        
        # Log webhook received
        safe_log_sync_event(
            sync_op.operation_id,
            "WEBHOOK",
            "Trello webhook received",
            card_id=card_id,
            event_type=event_info.get("event"),
            change_types=event_info.get("change_types", []),
        )
        
        # Fetch card data
        card_data = get_trello_card_by_id(card_id)
        if not card_data:
            safe_log_sync_event(sync_op.operation_id, "ERROR", "Card not found in Trello", card_id=card_id)
            raise ValueError(f"Card {card_id} not found in Trello")
        
        # Check if card creation from Excel sync (skip Excel update)
        if event_info.get("event") == "card_created":
            rec = Job.query.filter_by(trello_card_id=card_id).first()
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
            rec = Job.query.filter_by(trello_card_id=card_id).first()
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
        rec = Job.query.filter_by(trello_card_id=card_id).one_or_none()
        
        if not rec:
            safe_log_sync_event(sync_op.operation_id, "INFO", "No DB record found for card", card_id=card_id)
            # Just return - not an error, card isn't tracked
            return

        duplicate_card_id = None
        list_move_payload_hash = None  # Store for setting applied_at later

        # Check for duplicate updates
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
        
        # Save old description for comparison
        old_description = rec.trello_card_description or ""
        
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
            
            # Apply list mapping to database
            TrelloListMapper.apply_trello_list_to_db(rec, rec.trello_list_name, sync_op.operation_id)
            
            # Check if stage actually changed (only create event if DB was updated)
            status_changed = old_stage_before_list_move != rec.stage
            
            if status_changed:
                # Create JobEvent for stage update (list movement that caused status change)
                action = "update_stage"
                # Use to_list_name as the stage name to match frontend format
                stage = to_list_name
                payload = {"to": stage}
                
                # Create payload hash matching the frontend format
                payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
                hash_string = f"{action}:{rec.job}:{rec.release}:{payload_json}"
                payload_hash = hashlib.sha256(hash_string.encode('utf-8')).hexdigest()
                list_move_payload_hash = payload_hash  # Store for later
                
                # Check for duplicate event
                existing_event = JobEvents.query.filter_by(
                    job=rec.job,
                    release=rec.release,
                    payload_hash=payload_hash
                ).first()
                
                if not existing_event:
                    event = JobEvents(
                        job=rec.job,
                        release=rec.release,
                        action=action,
                        payload=payload,
                        payload_hash=payload_hash,
                        source='Trello'
                    )
                    db.session.add(event)
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "JobEvent created for stage update",
                        job=rec.job,
                        release=rec.release,
                        from_list=from_list_name,
                        to_stage=stage
                    )
                else:
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "Duplicate stage update event detected, skipping",
                        job=rec.job,
                        release=rec.release,
                        payload_hash=payload_hash
                    )
            
            destination_name = event_info.get("to")
            # Temporarily disable duplicate-and-link flow for Fit Up Complete cards.
            # Keeping the structure ensures the surrounding sync logic still runs without Trello duplication.
            # if destination_name == "Fit Up Complete.":
            #     target_list_id = cfg.UNASSIGNED_CARDS_LIST_ID
            #     if target_list_id:
            #         if not card_has_link_to(card_id):
            #             cloned = copy_trello_card(card_id, target_list_id)
            #             duplicate_card_id = cloned["id"]
            #             link_cards(card_id, duplicate_card_id)
            #             update_trello_card(card_id, clear_due_date=True)
            #             update_trello_card(duplicate_card_id, clear_due_date=True)
            #             safe_log_sync_event(
            #                 sync_op.operation_id,
            #                 "INFO",
            #                 "Fit Up duplicate created and linked",
            #                 new_card_id=duplicate_card_id,
            #             )
            #         else:
            #             safe_log_sync_event(
            #                 sync_op.operation_id,
            #                 "INFO",
            #                 "Fit Up duplicate already exists; skipping clone",
            #             )
            #     else:
            #         safe_log_sync_event(
            #             sync_op.operation_id,
            #             "WARNING",
            #             "Unassigned cards list ID not configured; skipping duplicate",
            #         )

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
            
            if duplicate_card_id:
                viewer_url = rec.viewer_url
                if not viewer_url:
                    procore_result = add_procore_link_to_trello_card(rec.job, rec.release)
                    if procore_result and procore_result.get("viewer_url"):
                        viewer_url = procore_result["viewer_url"]
                if viewer_url:
                    add_procore_link(duplicate_card_id, viewer_url)
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "Procore link copied to duplicate card",
                        new_card_id=duplicate_card_id,
                    )
        
        # Handle description changes - recalculate installation duration if needed
        if event_info.get("has_description_change", False):
            new_description = card_data.get("desc", "") or ""
            
            if "Number of Guys:" in new_description:
                num_guys = parse_num_guys_from_description(new_description)
                
                # Recalculate duration if Number of Guys exists and we have install hours
                if num_guys and rec.install_hrs:
                    updated_description = update_installation_duration_in_description(
                        new_description,
                        rec.install_hrs,
                        num_guys
                    )
                    
                    # Only update if description changed
                    if updated_description != new_description:
                        update_trello_card_description(card_id, updated_description)
                        safe_log_sync_event(
                            sync_op.operation_id,
                            "INFO",
                            "Installation duration updated",
                            num_guys=num_guys,
                            install_hrs=rec.install_hrs
                        )

        # Commit DB changes
        db.session.add(rec)
        db.session.commit()

        # Set applied_at for any JobEvents created during this sync (after job record is updated)
        if list_move_payload_hash:
            event = JobEvents.query.filter_by(
                job=rec.job,
                release=rec.release,
                payload_hash=list_move_payload_hash
            ).first()
            
            if event and not event.applied_at:
                event.applied_at = datetime.utcnow()
                db.session.commit()
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "JobEvent applied_at set",
                    job=rec.job,
                    release=rec.release
                )

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

# Helper: detect if start_install is formula-driven
def is_formula_cell(row):
    formula_val = row.get("start_install_formula")
    formulaTF_val = row.get("start_install_formulaTF")
    return bool(formulaTF_val) or (
        isinstance(formula_val, str) and formula_val.startswith("=")
    )


# sync_from_onedrive and _update_trello_card_from_excel functions removed - OneDrive polling functionality removed

