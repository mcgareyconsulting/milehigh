from numpy import safe_eval
import openpyxl
import pandas as pd
from pandas import Timestamp
from app.trello.utils import (
    extract_card_name,
    extract_identifier,
    parse_trello_datetime,
    calculate_business_days_before,
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
    """
    Sync data from OneDrive to Trello based on the polling payload
    TODO: List movement mapping errors, duplicate db records being passed on one change
    """
    # Check database connection before creating sync operation
    sync_op = None
    try:
        if check_database_connection():
            sync_op = create_sync_operation(
                operation_type="onedrive_poll",
                source_system="onedrive",
                source_id=None,
            )
            safe_log_sync_event(sync_op.operation_id, "INFO", "SyncOperation created")
            logger.info("OneDrive poll sync operation logged to database", operation_id=sync_op.operation_id)
        else:
            logger.warning("Database connection unavailable - proceeding without sync operation logging")
    except Exception as e:
        logger.warning("Failed to create sync operation - proceeding without database logging", error=str(e))

    try:
        
        # Only update sync operation if it was successfully created
        safe_sync_op_call(sync_op, update_sync_operation, status=SyncStatus.IN_PROGRESS)
        safe_sync_op_call(sync_op, safe_log_sync_event, "INFO", "SyncOperation in_progress")

        if data is None:
            logger.info("No data received from OneDrive polling")
            safe_log_sync_event(sync_op.operation_id, "INFO", "No data received from OneDrive polling")
            safe_sync_op_call(sync_op, update_sync_operation, status=SyncStatus.SKIPPED)
            return

        if "last_modified_time" not in data or "data" not in data:
            logger.warning("Invalid OneDrive polling data format")
            safe_log_sync_event(sync_op.operation_id, "WARNING", "Invalid OneDrive polling data format")
            safe_sync_op_call(sync_op, update_sync_operation, status=SyncStatus.FAILED, error_type="InvalidPayload")
            return

        # Convert Excel last_modified_time (string) → datetime
        try:
            excel_last_updated = parse_excel_datetime(data["last_modified_time"])
        except Exception as e:
            logger.error("Failed to parse Excel last modified time", 
                        error=str(e), 
                        last_modified_time=data.get("last_modified_time"))
            safe_log_sync_event(sync_op.operation_id, "ERROR", 
                              "Failed to parse Excel last modified time",
                              error=str(e),
                              last_modified_time=data.get("last_modified_time"))
            safe_sync_op_call(sync_op, update_sync_operation, 
                            status=SyncStatus.FAILED, 
                            error_type="InvalidTimestamp")
            return
            
        df = data["data"]
        
        # Validate DataFrame
        if df is None or df.empty:
            logger.warning("Empty DataFrame received from OneDrive")
            safe_log_sync_event(sync_op.operation_id, "WARNING", "Empty DataFrame received")
            safe_sync_op_call(sync_op, update_sync_operation, status=SyncStatus.SKIPPED)
            return

        logger.info(f"Processing OneDrive data last modified at {excel_last_updated}")
        logger.info(f"DataFrame {df.shape[0]} rows, {df.shape[1]} columns")
        safe_log_sync_event(
            sync_op.operation_id,
            "INFO",
            "Processing OneDrive data",
            last_modified=str(excel_last_updated),
            rows=int(df.shape[0]),
            cols=int(df.shape[1]),
        )

        updated_records = []
        formula_updates_count = 0  # Track formula-driven start_install updates

        # Fields to check for diffs
        fields_to_check = [
            # ("Excel column name", "DB field name", "type")
            ("Fitup comp", "fitup_comp", "text"),
            ("Welded", "welded", "text"),
            ("Paint Comp", "paint_comp", "text"),
            ("Ship", "ship", "text"),
            ("Notes", "notes", "text"), 
            ("Start install", "start_install", "date"),
        ]

        def normalize_int_like(value):
            if pd.isna(value) or value is None:
                return None
            if isinstance(value, (int,)):
                return value
            try:
                # Extract digits from strings like 'V862' -> 862
                if isinstance(value, str):
                    digits = re.findall(r"\d+", value)
                    if digits:
                        return int("".join(digits))
                    return None
                # numpy integers
                import numpy as np
                if isinstance(value, (np.integer,)):
                    return int(value)
            except Exception:
                return None
            return None

        for _, row in df.iterrows():
            job = row.get("Job #")
            release = row.get("Release #")
            if pd.isna(job) or pd.isna(release):
                logger.warning(f"Skipping row with missing Job # or Release #: {row}")
                continue

            job_num = normalize_int_like(job)
            # Don't normalize release - keep original format for string field
            release_str = str(release) if not pd.isna(release) else None
            identifier = f"{job}-{release}"

            rec = Job.query.filter_by(job=job_num, release=release_str).one_or_none()
            if not rec:
                print(f"No record found for {identifier}")
                continue

            db_last_updated = rec.last_updated_at

            # Check for duplicate updates from Excel itself
            if rec.source_of_update == "Excel" and excel_last_updated <= db_last_updated:
                logger.info(
                    f"Skipping Excel update for {identifier}: event is older or same timestamp and originated from Excel."
                )
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "Skipping Excel update (same origin/timestamp)",
                    id=rec.id,
                    job=rec.job,
                    release=rec.release,
                    excel_identifier=identifier,
                    excel_last_updated=str(excel_last_updated),
                    db_last_updated=str(db_last_updated),
                )
                continue

            # Only log diffs if Excel is newer
            if excel_last_updated <= db_last_updated:
                logger.info(
                    f"Skipping {identifier}: Excel last updated {excel_last_updated} <= DB {db_last_updated}"
                )
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "Skipping: Excel older than DB",
                    id=rec.id,
                    job=rec.job,
                    release=rec.release,
                    excel_identifier=identifier,
                    excel_last_updated=str(excel_last_updated),
                    db_last_updated=str(db_last_updated),
                )
                continue

            record_updated = False
            formula_status_for_trello = None  # For Trello update later

            for excel_field, db_field, field_type in fields_to_check:
                excel_val = row.get(excel_field)
                db_val = getattr(rec, db_field, None)
                

                # Normalize date fields if date
                if field_type == "date":
                    excel_val = as_date(excel_val)
                    db_val = as_date(db_val)

                # For most fields, treat NaN/None as equivalent
                if (pd.isna(excel_val) or excel_val is None) and db_val is None:
                    continue

                # Special handling for 'start_install' to check formula status
                if field_type == "date":
                    is_formula = is_formula_cell(row)
                    formula_status_for_trello = is_formula  # Track for Trello card update

                    if is_formula:
                        # If formula-driven, update DB if value differs, but do not update Trello
                        if excel_val != db_val:
                            # Track formula updates for summary logging instead of individual logs
                            formula_updates_count += 1
                            setattr(rec, db_field, excel_val)
                            setattr(
                                rec,
                                "start_install_formula",
                                row.get("start_install_formula") or "",
                            )
                            setattr(
                                rec,
                                "start_install_formulaTF",
                                bool(row.get("start_install_formulaTF")),
                            )
                            record_updated = True
                    else:
                        # Hard-coded: update DB if value differs and clear formula flags
                        if excel_val != db_val:
                            logger.info(
                                f"{job}-{release} Updating DB {db_field} (hard-coded): {db_val!r} -> {excel_val!r}"
                            )
                            safe_log_sync_event(
                                sync_op.operation_id,
                                "INFO",
                                "DB field update (hard-coded)",
                                id=rec.id,
                                job=rec.job,
                                release=rec.release,
                                excel_identifier=identifier,
                                field=db_field,
                                old_value=str(db_val),
                                new_value=str(excel_val),
                            )
                            setattr(rec, db_field, excel_val)
                            setattr(rec, "start_install_formula", "")
                            setattr(rec, "start_install_formulaTF", False)
                            record_updated = True
                    continue  # skip generic update for this field

                # Special handling for 'notes' - append to Trello custom field
                if excel_field == "Notes" and field_type == "text":
                    if excel_val != db_val and excel_val and str(excel_val).strip():
                        logger.info(
                            f"{job}-{release} Notes field updated, will append to Trello: {db_val!r} -> {excel_val!r}"
                        )
                        safe_log_sync_event(
                            sync_op.operation_id,
                            "INFO",
                            "Notes field updated, will append to Trello",
                            id=rec.id,
                            job=rec.job,
                            release=rec.release,
                            excel_identifier=identifier,
                            field=db_field,
                            old_value=str(db_val),
                            new_value=str(excel_val),
                        )
                        # Update DB with new note value
                        setattr(rec, db_field, excel_val)
                        record_updated = True
                        
                        # Store the note for Trello update later
                        if not hasattr(rec, '_pending_note'):
                            rec._pending_note = excel_val
                        else:
                            rec._pending_note = excel_val
                    continue  # skip generic update for this field

                # Generic update for non-special fields
                if excel_val != db_val:
                    logger.info(
                        f"{job}-{release} Updating DB {db_field}: {db_val!r} -> {excel_val!r}"
                    )
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "DB field update",
                        id=rec.id,
                        job=rec.job,
                        release=rec.release,
                        excel_identifier=identifier,
                        field=db_field,
                        old_value=str(db_val),
                        new_value=str(excel_val),
                    )
                    setattr(rec, db_field, excel_val)
                    record_updated = True

            if record_updated:
                rec.last_updated_at = excel_last_updated
                rec.source_of_update = "Excel"
                updated_records.append((rec, formula_status_for_trello))

        # Commit all DB updates at once
        if updated_records:
            logger.info(f"Committing {len(updated_records)} updated records to DB.")
            try:
                for rec, _ in updated_records:
                    db.session.add(rec)
                db.session.commit()
                logger.info(f"Committed {len(updated_records)} updated records to DB.")
                
                # Log formula updates summary if any occurred
                if formula_updates_count > 0:
                    logger.info(f"Updated {formula_updates_count} formula-driven start_install dates")
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "Formula-driven start_install updates summary",
                        formula_updates_count=formula_updates_count,
                    )
                
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "DB commit completed",
                    updated_records=len(updated_records),
                )
            except Exception as commit_error:
                logger.error("Failed to commit database changes", 
                           error=str(commit_error),
                           updated_records=len(updated_records))
                safe_log_sync_event(sync_op.operation_id, "ERROR", 
                                  "Failed to commit database changes",
                                  error=str(commit_error),
                                  updated_records=len(updated_records))
                try:
                    db.session.rollback()
                except Exception:
                    pass
                raise

            # Trello update: due dates and list movement ONLY if the last update was NOT from Trello
            for rec, is_formula in updated_records:
                if rec.source_of_update != "Trello":
                    if hasattr(rec, "trello_card_id") and rec.trello_card_id:
                        try:
                            # Determine new due date and list ID
                            new_due_date = None
                            if not is_formula and rec.start_install:
                                # Set due date to 2 business days before the start_install date
                                new_due_date = calculate_business_days_before(rec.start_install, 2)

                            new_list_id = None
                            new_list_name = TrelloListMapper.determine_trello_list_from_db(rec)
                            
                            # Special handling for shipping states
                            # If the current Trello list is already one of these valid states, preserve it
                            current_list_name = getattr(rec, "trello_list_name", None)
                            
                            if (new_list_name == "Paint complete" and 
                                TrelloListMapper.is_valid_shipping_state(current_list_name)):
                                # Keep the current list instead of forcing to "Paint complete"
                                new_list_name = current_list_name
                                new_list = get_list_by_name(current_list_name)
                                if new_list:
                                    new_list_id = new_list["id"]
                            elif new_list_name and not TrelloListMapper.is_valid_shipping_state(new_list_name):
                                # For non-shipping states, use the determined list
                                new_list = get_list_by_name(new_list_name)
                                if new_list:
                                    new_list_id = new_list["id"]
                            elif TrelloListMapper.is_valid_shipping_state(new_list_name):
                                # For shipping states, use the determined list
                                new_list = get_list_by_name(new_list_name)
                                if new_list:
                                    new_list_id = new_list["id"]

                            # Only update Trello if there's a change in due date or list
                            current_list_id = getattr(rec, "trello_list_id", None)
                            if (
                                new_due_date != rec.trello_card_date
                                or new_list_id != current_list_id
                            ):
                                logger.info(
                                    f"Updating Trello card {rec.trello_card_id}: Due Date={{new_due_date}} (was {rec.trello_card_date}), List={{new_list_name}} (was {rec.trello_list_name})"
                                )
                                safe_log_sync_event(
                                    sync_op.operation_id,
                                    "INFO",
                                    "Updating Trello card",
                                    id=rec.id,
                                    job=rec.job,
                                    release=rec.release,
                                    trello_card_id=rec.trello_card_id,
                                    current_list_name=rec.trello_list_name,
                                    new_list_name=new_list_name,
                                    new_due_date=str(new_due_date) if new_due_date else None,
                                )
                                # Determine if we need to clear the due date
                                clear_due_date = (new_due_date is None and rec.trello_card_date is not None)
                                if clear_due_date:
                                    logger.info(
                                        "Clearing due date for Trello card",
                                        operation_id=sync_op.operation_id,
                                        trello_card_id=rec.trello_card_id,
                                        current_due_date=str(rec.trello_card_date)
                                    )
                                update_trello_card(
                                    rec.trello_card_id, new_list_id, new_due_date, clear_due_date
                                )

                                # Update mirror card date range if we have a non-formula start date and install hours
                                if not is_formula and rec.start_install and rec.install_hrs:
                                    logger.info(
                                        f"Updating mirror card date range for card {rec.trello_card_id}",
                                        operation_id=sync_op.operation_id,
                                        start_date=str(rec.start_install),
                                        install_hrs=rec.install_hrs
                                    )
                                    mirror_result = update_mirror_card_date_range(
                                        rec.trello_card_id, 
                                        rec.start_install,  # Use exact date, no business day adjustment
                                        rec.install_hrs
                                    )
                                    if mirror_result["success"]:
                                        logger.info(
                                            f"Successfully updated mirror card date range",
                                            operation_id=sync_op.operation_id,
                                            trello_card_id=rec.trello_card_id,
                                            mirror_card_short_link=mirror_result.get("card_short_link"),
                                            start_date=mirror_result.get("start_date"),
                                            due_date=mirror_result.get("due_date")
                                        )
                                        safe_log_sync_event(
                                            sync_op.operation_id,
                                            "INFO",
                                            "Mirror card date range updated",
                                            id=rec.id,
                                            job=rec.job,
                                            release=rec.release,
                                            trello_card_id=rec.trello_card_id,
                                            mirror_card_short_link=mirror_result.get("card_short_link"),
                                            start_date=mirror_result.get("start_date"),
                                            due_date=mirror_result.get("due_date")
                                        )
                                    else:
                                        logger.warning(
                                            f"Failed to update mirror card date range: {mirror_result['error']}",
                                            operation_id=sync_op.operation_id,
                                            trello_card_id=rec.trello_card_id
                                        )
                                        safe_log_sync_event(
                                            sync_op.operation_id,
                                            "WARNING",
                                            "Failed to update mirror card date range",
                                            id=rec.id,
                                            job=rec.job,
                                            release=rec.release,
                                            trello_card_id=rec.trello_card_id,
                                            error=mirror_result.get("error")
                                        )

                                # Update DB record with new Trello info after successful API call
                                rec.trello_card_date = new_due_date
                                rec.trello_list_id = new_list_id
                                rec.trello_list_name = new_list_name
                                rec.last_updated_at = datetime.now(timezone.utc).replace(
                                    tzinfo=None
                                )
                                rec.source_of_update = "Excel"
                                db.session.add(rec)
                                db.session.commit()
                                safe_log_sync_event(
                                    sync_op.operation_id,
                                    "INFO",
                                    "Trello card updated",
                                    id=rec.id,
                                    job=rec.job,
                                    release=rec.release,
                                    trello_card_id=rec.trello_card_id,
                                    list_name=new_list_name,
                                )
                            
                            # Handle notes update to Trello comments
                            if hasattr(rec, '_pending_note') and rec._pending_note:
                                logger.info(
                                    f"Adding note as comment to Trello card {rec.trello_card_id}: {rec._pending_note}"
                                )
                                safe_log_sync_event(
                                    sync_op.operation_id,
                                    "INFO",
                                    "Adding note as comment to Trello card",
                                    id=rec.id,
                                    job=rec.job,
                                    release=rec.release,
                                    trello_card_id=rec.trello_card_id,
                                    note=rec._pending_note,
                                )
                                
                                success = add_comment_to_trello_card(
                                    rec.trello_card_id, 
                                    rec._pending_note,
                                    sync_op.operation_id
                                )
                                
                                if success:
                                    safe_log_sync_event(
                                        sync_op.operation_id,
                                        "INFO",
                                        "Note successfully added as comment to Trello",
                                        id=rec.id,
                                        job=rec.job,
                                        release=rec.release,
                                        trello_card_id=rec.trello_card_id,
                                    )
                                else:
                                    safe_log_sync_event(
                                        sync_op.operation_id,
                                        "ERROR",
                                        "Failed to add note as comment to Trello",
                                        id=rec.id,
                                        job=rec.job,
                                        release=rec.release,
                                        trello_card_id=rec.trello_card_id,
                                        note=rec._pending_note,
                                    )
                                
                                # Clear the pending note after processing
                                delattr(rec, '_pending_note')
                            else:
                                # Handle notes update even if no other Trello updates needed
                                if hasattr(rec, '_pending_note') and rec._pending_note:
                                    logger.info(
                                        f"Adding note as comment to Trello card {rec.trello_card_id}: {rec._pending_note}"
                                    )
                                    safe_log_sync_event(
                                        sync_op.operation_id,
                                        "INFO",
                                        "Adding note as comment to Trello card (no other updates)",
                                        id=rec.id,
                                        job=rec.job,
                                        release=rec.release,
                                        trello_card_id=rec.trello_card_id,
                                        note=rec._pending_note,
                                    )
                                    
                                    success = add_comment_to_trello_card(
                                        rec.trello_card_id, 
                                        rec._pending_note,
                                        sync_op.operation_id
                                    )
                                    
                                    if success:
                                        safe_log_sync_event(
                                            sync_op.operation_id,
                                            "INFO",
                                            "Note successfully added as comment to Trello",
                                            id=rec.id,
                                            job=rec.job,
                                            release=rec.release,
                                            trello_card_id=rec.trello_card_id,
                                        )
                                    else:
                                        safe_log_sync_event(
                                            sync_op.operation_id,
                                            "ERROR",
                                            "Failed to add note as comment to Trello",
                                            id=rec.id,
                                            job=rec.job,
                                            release=rec.release,
                                            trello_card_id=rec.trello_card_id,
                                            note=rec._pending_note,
                                        )
                                    
                                    # Clear the pending note after processing
                                    delattr(rec, '_pending_note')
                                
                        except Exception as e:
                            logger.error(
                                f"Error updating Trello card {rec.trello_card_id}: {e}"
                            )
                            safe_log_sync_event(
                                sync_op.operation_id,
                                "ERROR",
                                "Error updating Trello card",
                                id=rec.id,
                                job=rec.job,
                                release=rec.release,
                                trello_card_id=rec.trello_card_id,
                                error=str(e),
                            )
        else:
            logger.info("[SYNC] No records needed updating.")
            safe_log_sync_event(sync_op.operation_id, "INFO", "No records needed updating")        # Mark operation as completed
        if sync_op:
            try:
                duration = (datetime.utcnow() - sync_op.started_at).total_seconds()
                safe_sync_op_call(sync_op, update_sync_operation, 
                    status=SyncStatus.COMPLETED,
                    completed_at=datetime.utcnow(),
                    duration_seconds=duration
                )
                safe_log_sync_event(sync_op.operation_id, "INFO", "SyncOperation completed")
            except Exception as e:
                logger.warning("Failed to mark sync operation as completed", error=str(e))
        else:
            logger.info("OneDrive sync completed successfully (no database logging available)")

    except Exception as e:
        # Rollback any pending database changes
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.warning("Failed to rollback database changes", 
                         error=str(rollback_error),
                         operation_id=sync_op.operation_id if sync_op else None)
        
        error_context = {
            "error": str(e),
            "error_type": type(e).__name__,
            "operation_id": sync_op.operation_id if sync_op else None,
            "data_shape": data.get("data").shape if data and "data" in data else None
        }
        
        logger.error("OneDrive sync failed", **error_context)
        
        # Try to log the error to database if possible
        if sync_op:
            try:
                duration = (datetime.utcnow() - sync_op.started_at).total_seconds()
                safe_sync_op_call(sync_op, update_sync_operation,
                    status=SyncStatus.FAILED,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    completed_at=datetime.utcnow(),
                    duration_seconds=duration
                )
                safe_log_sync_event(sync_op.operation_id,
                    "ERROR",
                    "OneDrive sync failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    data_shape=data.get("data").shape if data and "data" in data else None
                )
            except Exception as db_error:
                logger.warning("Failed to log sync error to database", 
                             db_error=str(db_error),
                             operation_id=sync_op.operation_id)
        else:
            logger.info("OneDrive sync failed (no database logging available)", 
                       error=str(e), 
                       error_type=type(e).__name__)
        raise

