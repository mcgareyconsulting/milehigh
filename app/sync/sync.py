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
)
from app.onedrive.utils import (
    get_excel_row_and_index_by_identifiers,
    parse_excel_datetime,
)
from app.onedrive.api import get_excel_dataframe, update_excel_cell
from app.models import Job, SyncOperation, SyncLog, SyncStatus, db
from datetime import datetime, date, timezone, time
from zoneinfo import ZoneInfo
from app.sync_lock import synchronized_sync, sync_lock_manager
from app.logging_config import get_logger, SyncContext, log_sync_operation
import uuid
import re

from app.sync.db_operations import create_sync_operation, update_sync_operation
from app.sync.context import sync_operation_context
from app.sync.logging import safe_log_sync_event, safe_sync_op_call
from app.sync.services.trello_list_mapper import TrelloListMapper
from app.sync.state_tracker import detect_and_track_state_changes

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
    """Sync data from Trello to OneDrive based on webhook payload."""
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
        
        # Check if card update shortly after Excel sync (skip entirely)
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

        # CAPTURE OLD VALUES before updating
        old_values = {
            'fitup_comp': rec.fitup_comp,
            'paint_comp': rec.paint_comp,
            'ship': rec.ship,
        }

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
            safe_log_sync_event(
                sync_op.operation_id,
                "INFO",
                "List move detected",
                from_list=event_info.get("from"),
                to_list=rec.trello_list_name
            )
            TrelloListMapper.apply_trello_list_to_db(rec, rec.trello_list_name, sync_op.operation_id)
            
            # Sort both source and destination lists by Fab Order (only for target lists)
            from app.config import Config as cfg
            
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

        # NEW: Track state changes after commit
        detect_and_track_state_changes(
            job_record=rec,
            old_values=old_values,
            operation_id=sync_op.operation_id,
            source="Trello"
        )
        
        safe_log_sync_event(
            sync_op.operation_id,
            "INFO",
            "DB update completed",
            job=rec.job,
            release=rec.release
        )

        # Update Excel if needed
        needs_excel_update = event_info.get("needs_excel_update", False)
        skip_excel = event_info.get("skip_excel_update", False)
        
        if needs_excel_update and not skip_excel:
            safe_log_sync_event(
                sync_op.operation_id,   
                "INFO",
                "Excel update started",
                job=rec.job,
                release=rec.release,
                change_types=event_info.get("change_types", [])
            )
            
            column_updates = {
                "M": rec.fitup_comp,
                "N": rec.welded,
                "O": rec.paint_comp,
                "P": rec.ship,
            }
            
            index, row = get_excel_row_and_index_by_identifiers(rec.job, rec.release)
            if index and row is not None:
                updated_cells = []
                failed_cells = []
                
                for col, val in column_updates.items():
                    cell_address = col + str(index)
                    success = update_excel_cell(cell_address, val)
                    if success:
                        updated_cells.append({
                            "address": cell_address,
                            "value": val
                        })
                    else:
                        failed_cells.append(cell_address)
                
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "Excel update completed",
                    job=rec.job,
                    release=rec.release,
                    updated_cells=updated_cells,
                    failed_cells=failed_cells
                )
            else:
                safe_log_sync_event(
                    sync_op.operation_id,
                    "ERROR",
                    "Excel row not found",
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


def sync_from_onedrive(data):
    """Sync data from OneDrive to Trello based on polling payload."""
    
    # Use context manager - handles all operation tracking
    with sync_operation_context("onedrive_poll", "onedrive", None) as sync_op:
        if sync_op is None:
            # Database unavailable - context manager already logged warning
            return
        
        # Validate input data
        if data is None:
            safe_log_sync_event(sync_op.operation_id, "ERROR", "No data received", {})
            return

        if "last_modified_time" not in data or "data" not in data:
            safe_log_sync_event(sync_op.operation_id, "ERROR", "invalid_payload", keys=list(data.keys()) if data else [])
            raise ValueError("Invalid OneDrive polling data format")

        # Parse Excel timestamp
        try:
            excel_last_updated = parse_excel_datetime(data["last_modified_time"])
        except Exception as e:
            safe_log_sync_event(
                sync_op.operation_id,
                "ERROR",
                "Invalid timestamp",
                last_modified_time=data.get("last_modified_time"),
                error=str(e)
            )
            raise ValueError(f"Failed to parse Excel timestamp: {e}")
        
        df = data["data"]
        
        # Validate DataFrame
        if df is None or df.empty:
            safe_log_sync_event(sync_op.operation_id, "ERROR", "Empty dataframe", rows=df.shape[0], cols=df.shape[1], last_modified=excel_last_updated.isoformat())
            return

        safe_log_sync_event(
            sync_op.operation_id,
            "INFO",
            "Processing started",
            rows=df.shape[0],
            cols=df.shape[1],
            last_modified=excel_last_updated.isoformat()
        )

        updated_records = []
        formula_updates_count = 0

        # Fields to check for diffs
        fields_to_check = [
            ("Fitup comp", "fitup_comp", "text"),
            ("Welded", "welded", "text"),
            ("Paint Comp", "paint_comp", "text"),
            ("Ship", "ship", "text"),
            ("Notes", "notes", "text"),
            ("Start install", "start_install", "date"),
            ("Fab Order", "fab_order", "float"),
        ]

        # Process each row
        for _, row in df.iterrows():
            job = row.get("Job #")
            release = row.get("Release #")
            
            if pd.isna(job) or pd.isna(release):
                continue

            job_num = int(job)
            release_str = str(release) if not pd.isna(release) else None

            rec = Job.query.filter_by(job=job_num, release=release_str).one_or_none()
            if not rec:
                continue

            # Skip if Excel event is older or duplicate from Excel
            if rec.source_of_update == "Excel" and excel_last_updated <= rec.last_updated_at:
                continue
            if excel_last_updated <= rec.last_updated_at:
                continue

            # NEW: CAPTURE OLD VALUES before any updates
            old_values = {
                'fitup_comp': rec.fitup_comp,
                'paint_comp': rec.paint_comp,
                'ship': rec.ship,
                'fab_order': rec.fab_order,
            }

            record_updated = False
            formula_status_for_trello = None

            # Check each field for changes
            for excel_field, db_field, field_type in fields_to_check:
                excel_val = row.get(excel_field)
                db_val = getattr(rec, db_field, None)

                # Normalize dates
                if field_type == "date":
                    excel_val = as_date(excel_val)
                    db_val = as_date(db_val)
                
                # Normalize floats
                if field_type == "float":
                    # Convert to float, handling NaN and None
                    if pd.isna(excel_val) or excel_val is None or str(excel_val).strip() == '':
                        excel_val = None
                    else:
                        try:
                            excel_val = float(excel_val)
                        except (TypeError, ValueError):
                            excel_val = None
                    
                    # Ensure db_val is also float for comparison
                    if db_val is not None:
                        try:
                            db_val = float(db_val)
                        except (TypeError, ValueError):
                            db_val = None

                if (pd.isna(excel_val) or excel_val is None) and db_val is None:
                    continue

                # Special handling for start_install
                if field_type == "date":
                    is_formula = is_formula_cell(row)
                    formula_status_for_trello = is_formula

                    if is_formula:
                        if excel_val != db_val:
                            formula_updates_count += 1
                            setattr(rec, db_field, excel_val)
                            setattr(rec, "start_install_formula", row.get("start_install_formula") or "")
                            setattr(rec, "start_install_formulaTF", bool(row.get("start_install_formulaTF")))
                            record_updated = True
                    else:
                        if excel_val != db_val:
                            setattr(rec, db_field, excel_val)
                            setattr(rec, "start_install_formula", "")
                            setattr(rec, "start_install_formulaTF", False)
                            record_updated = True
                    continue

                # Special handling for notes
                if excel_field == "Notes" and field_type == "text":
                    if excel_val != db_val and excel_val and str(excel_val).strip():
                        setattr(rec, db_field, excel_val)
                        rec._pending_note = excel_val
                        record_updated = True
                    continue

                # Generic field update
                if excel_val != db_val:
                    setattr(rec, db_field, excel_val)
                    record_updated = True

            if record_updated:
                rec.last_updated_at = excel_last_updated
                rec.source_of_update = "Excel"
                updated_records.append((rec, formula_status_for_trello, old_values))

        # Commit all DB updates
        if updated_records:
            for rec, _, _ in updated_records:
                db.session.add(rec)
            db.session.commit()

            # NEW: Track state changes for all updated records
            for rec, _, old_vals in updated_records:
                detect_and_track_state_changes(
                    job_record=rec,
                    old_values=old_vals,
                    operation_id=sync_op.operation_id,
                    source="Excel"
                )
            
            safe_log_sync_event(
                sync_op.operation_id,
                "INFO",
                "DB updated",
                records_updated=len(updated_records),
                formula_updates=formula_updates_count
            )

            # Update Trello cards
            trello_updates_success = 0
            trello_updates_failed = 0
            
            for rec, is_formula, old_vals in updated_records:
                if rec.source_of_update != "Trello" and hasattr(rec, "trello_card_id") and rec.trello_card_id:
                    try:
                        _update_trello_card_from_excel(rec, is_formula, sync_op, old_vals)
                        trello_updates_success += 1
                    except Exception as e:
                        trello_updates_failed += 1
                        logger.error(
                            f"Trello update failed for card {rec.trello_card_id}",
                            error=str(e),
                            operation_id=sync_op.operation_id
                        )
            
            if trello_updates_success > 0 or trello_updates_failed > 0:
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "Trello updates completed",
                    success=trello_updates_success,
                    failed=trello_updates_failed
                )
        else:
            safe_log_sync_event(sync_op.operation_id, "INFO", "No updates needed")
        
        # Context manager will automatically mark as COMPLETED


def _update_trello_card_from_excel(rec, is_formula, sync_op, old_values=None):
    """Update Trello card from Excel changes."""
    operation_id = sync_op.operation_id if sync_op else None
    from app.config import Config as cfg
    
    # Calculate new due date
    new_due_date = None
    if not is_formula and rec.start_install:
        new_due_date = calculate_business_days_before(rec.start_install, 2)

    # Determine target list with shipping state preservation
    new_list_name = TrelloListMapper.determine_trello_list_from_db(rec)
    current_list_name = getattr(rec, "trello_list_name", None)
    
    if (new_list_name == "Paint complete" and 
        TrelloListMapper.is_valid_shipping_state(current_list_name)):
        new_list_name = current_list_name
    
    new_list_id = None
    if new_list_name:
        new_list = get_list_by_name(new_list_name)
        if new_list:
            new_list_id = new_list["id"]

    # Update Trello if needed
    current_list_id = getattr(rec, "trello_list_id", None)
    if new_due_date != rec.trello_card_date or new_list_id != current_list_id:
        safe_log_sync_event(
            operation_id,
            "INFO",
            "Trello card update started",
            card_id=rec.trello_card_id,
            job=rec.job,
            release=rec.release,
            new_list=new_list_name,
            new_due_date=str(new_due_date) if new_due_date else "No date change"
        )
        
        clear_due_date = (new_due_date is None and rec.trello_card_date is not None)
        update_trello_card(rec.trello_card_id, new_list_id, new_due_date, clear_due_date)

        # Update mirror card if applicable
        if not is_formula and rec.start_install and rec.install_hrs:
            mirror_result = update_mirror_card_date_range(
                rec.trello_card_id,
                rec.start_install,
                rec.install_hrs
            )
            if mirror_result["success"]:
                safe_log_sync_event(
                    operation_id,
                    "INFO",
                    "Mirror card date range updated",
                    card_id=rec.trello_card_id,
                    mirror_short_link=mirror_result.get("card_short_link"),
                    update_type="date_range",
                    start_date=mirror_result.get("start_date"),
                    due_date=mirror_result.get("due_date"),
                    install_hrs=rec.install_hrs
                )

        # Update DB with new Trello info
        rec.trello_card_date = new_due_date
        rec.trello_list_id = new_list_id
        rec.trello_list_name = new_list_name
        rec.last_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        rec.source_of_update = "Excel"
        db.session.add(rec)
        db.session.commit()

    # Handle Fab Order custom field update
    if old_values and old_values.get('fab_order') != rec.fab_order:
        if cfg.FAB_ORDER_FIELD_ID and rec.fab_order is not None:
            # Convert to int (round up if float)
            try:
                if isinstance(rec.fab_order, float):
                    fab_order_int = math.ceil(rec.fab_order)
                else:
                    fab_order_int = int(rec.fab_order)
                
                # Update Trello custom field
                success = update_card_custom_field_number(
                    rec.trello_card_id,
                    cfg.FAB_ORDER_FIELD_ID,
                    fab_order_int
                )
                
                if success:
                    safe_log_sync_event(
                        operation_id,
                        "INFO",
                        "Fab Order custom field updated",
                        card_id=rec.trello_card_id,
                        job=rec.job,
                        release=rec.release,
                        fab_order=fab_order_int,
                        old_fab_order=old_values.get('fab_order')
                    )
                    
                    # Sort the list after updating Fab Order (only if it's a target list)
                    current_list_id = rec.trello_list_id
                    if current_list_id:
                        sort_list_if_needed(
                            current_list_id,
                            cfg.FAB_ORDER_FIELD_ID,
                            operation_id,
                            "list"
                        )
                else:
                    safe_log_sync_event(
                        operation_id,
                        "ERROR",
                        "Failed to update Fab Order custom field",
                        card_id=rec.trello_card_id,
                        job=rec.job,
                        release=rec.release
                    )
            except (ValueError, TypeError) as e:
                safe_log_sync_event(
                    operation_id,
                    "ERROR",
                    "Could not convert fab_order to int",
                    card_id=rec.trello_card_id,
                    fab_order=rec.fab_order,
                    error=str(e)
                )

    # Handle notes as comments
    if hasattr(rec, '_pending_note') and rec._pending_note:
        success = add_comment_to_trello_card(rec.trello_card_id, rec._pending_note, operation_id)
        
        safe_log_sync_event(
            operation_id,
            "INFO",
            "Note added to Trello" if success else "Note add failed",
            card_id=rec.trello_card_id,
            job=rec.job,
            release=rec.release
        )
        
        delattr(rec, '_pending_note')

