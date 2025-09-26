import openpyxl
import pandas as pd
from pandas import Timestamp
from app.trello.utils import (
    extract_card_name,
    extract_identifier,
    parse_trello_datetime,
)
from app.trello.api import (
    get_trello_card_by_id,
    get_list_name_by_id,
    get_list_by_name,
    update_trello_card,
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

logger = get_logger(__name__)

def safe_safe_log_sync_event(operation_id: str, level: str, message: str, **kwargs):
    """Safely log a sync event, converting problematic types."""
    try:
        # Convert problematic types to safe JSON-serializable types
        def make_json_safe(obj):
            import numpy as np
            import pandas as pd
            
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            elif isinstance(obj, pd.NaType):
                return None
            elif hasattr(obj, 'item'):  # other numpy scalars
                return obj.item()
            elif isinstance(obj, dict):
                return {k: make_json_safe(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [make_json_safe(item) for item in obj]
            else:
                return obj
        
        safe_data = make_json_safe(kwargs)
        
        sync_log = SyncLog(
            operation_id=operation_id,
            level=level,
            message=message,
            data=safe_data
        )
        db.session.add(sync_log)
        db.session.commit()
    except Exception as e:
        # Don't let logging failures break the sync
        logger.warning("Failed to log sync event", error=str(e), operation_id=operation_id, message=message)

def safe_log_sync_event(operation_id: str, level: str, message: str, **kwargs):
    """Safely log a sync event, converting problematic types."""
    try:
        # Convert problematic types to safe JSON-serializable types
        def make_json_safe(obj):
            import numpy as np
            import pandas as pd
            
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            elif isinstance(obj, pd.NaType):
                return None
            elif hasattr(obj, 'item'):  # other numpy scalars
                return obj.item()
            elif isinstance(obj, dict):
                return {k: make_json_safe(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [make_json_safe(item) for item in obj]
            else:
                return obj
        
        safe_data = make_json_safe(kwargs)
        
        sync_log = SyncLog(
            operation_id=operation_id,
            level=level,
            message=message,
            data=safe_data
        )
        db.session.add(sync_log)
        db.session.commit()
    except Exception as e:
        # Don't let logging failures break the sync
        logger.warning("Failed to log sync event", error=str(e), operation_id=operation_id, message=message)

def create_sync_operation(operation_type: str, source_system: str = None, source_id: str = None) -> SyncOperation:
    """Create a new sync operation record."""
    operation_id = str(uuid.uuid4())[:8]
    sync_op = SyncOperation(
        operation_id=operation_id,
        operation_type=operation_type,
        status=SyncStatus.PENDING,
        source_system=source_system,
        source_id=source_id
    )
    db.session.add(sync_op)
    db.session.commit()
    return sync_op

def update_sync_operation(operation_id: str, **kwargs):
    """Update a sync operation record."""
    sync_op = SyncOperation.query.filter_by(operation_id=operation_id).first()
    if sync_op:
        for key, value in kwargs.items():
            if hasattr(sync_op, key):
                setattr(sync_op, key, value)
        db.session.commit()
    return sync_op

def rectify_db_on_trello_move(job, new_trello_list, operation_id: str):
    """Update job status based on Trello list movement."""
    logger.info(
        "Updating job status for Trello list move",
        operation_id=operation_id,
        job_id=job.id,
        new_list=new_trello_list,
        current_status={
            "fitup_comp": job.fitup_comp,
            "welded": job.welded,
            "paint_comp": job.paint_comp,
            "ship": job.ship
        }
    )
    
    if new_trello_list == "Paint complete":
        job.fitup_comp = "X"
        job.welded = "X"
        job.paint_comp = "X"
        job.ship = "O"
    elif new_trello_list == "Fit Up Complete.":
        job.fitup_comp = "X"
        job.welded = "O"
        job.paint_comp = ""
        job.ship = ""
    elif new_trello_list == "Shipping completed":
        job.fitup_comp = "X"
        job.welded = "X"
        job.paint_comp = "X"
        job.ship = "X"
    
    logger.info(
        "Job status updated",
        operation_id=operation_id,
        job_id=job.id,
        new_status={
            "fitup_comp": job.fitup_comp,
            "welded": job.welded,
            "paint_comp": job.paint_comp,
            "ship": job.ship
        }
    )

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
    """Sync data from Trello to OneDrive based on the webhook payload."""
    if event_info is None or not event_info.get("handled"):
        logger.info("No actionable event info received from Trello webhook")
        return

    card_id = event_info["card_id"]
    event_time = parse_trello_datetime(event_info.get("time"))
    
    # Create sync operation record
    sync_op = create_sync_operation(
        operation_type="trello_webhook",
        source_system="trello",
        source_id=card_id
    )
    safe_safe_log_sync_event(sync_op.operation_id, "INFO", "SyncOperation created", card_id=card_id, event=event_info.get("event"))
    
    with SyncContext("trello_webhook", sync_op.operation_id):
        try:
            # Update operation status
            update_sync_operation(sync_op.operation_id, status=SyncStatus.IN_PROGRESS)
            safe_safe_log_sync_event(sync_op.operation_id, "INFO", "SyncOperation in_progress")
            
            logger.info(
                "Processing Trello card",
                operation_id=sync_op.operation_id,
                card_id=card_id,
                event_time=event_time.isoformat() if event_time else None,
                event_type=event_info.get("event")
            )
            
            card_data = get_trello_card_by_id(card_id)
            if not card_data:
                logger.warning("Card not found in Trello API", operation_id=sync_op.operation_id, card_id=card_id)
                safe_log_sync_event(sync_op.operation_id, "WARNING", "Card not found in Trello API", card_id=card_id)
                update_sync_operation(sync_op.operation_id, status=SyncStatus.FAILED, error_type="CardNotFound")
                return

            rec = Job.query.filter_by(trello_card_id=card_id).one_or_none()
            
            # Log comparison data
            if rec:
                logger.info(
                    "Comparing Trello card to DB record",
                    operation_id=sync_op.operation_id,
                    card_id=card_id,
                    job_id=rec.id,
                    trello_name=card_data.get("name"),
                    db_name=rec.trello_card_name,
                    trello_list=get_list_name_by_id(card_data.get("idList")),
                    db_list=rec.trello_list_name
                )
                safe_log_sync_event(sync_op.operation_id, "INFO", "Comparing Trello card to DB record", 
                              card_id=card_id, job_id=rec.id, trello_name=card_data.get("name"), db_name=rec.trello_card_name)
            else:
                logger.info(
                    "No DB record found for card",
                    operation_id=sync_op.operation_id,
                    card_id=card_id,
                    trello_name=card_data.get("name")
                )
                safe_log_sync_event(sync_op.operation_id, "INFO", "No DB record found for card", 
                              card_id=card_id, trello_name=card_data.get("name"))

            # Check for duplicate updates
            if rec and rec.source_of_update == "Trello" and event_time <= rec.last_updated_at:
                logger.info(
                    "Skipping duplicate Trello update",
                    operation_id=sync_op.operation_id,
                    card_id=card_id,
                    event_time=event_time.isoformat() if event_time else None,
                    db_last_updated=rec.last_updated_at.isoformat() if rec.last_updated_at else None
                )
                safe_log_sync_event(sync_op.operation_id, "INFO", "Duplicate Trello event skipped",
                              card_id=card_id, event_time=str(event_time), db_last_updated=str(rec.last_updated_at))
                update_sync_operation(sync_op.operation_id, status=SyncStatus.SKIPPED)
                return

            # Check if update is needed
            diff = compare_timestamps(event_time, rec.last_updated_at if rec else None, sync_op.operation_id)
            if diff == "newer":
                logger.info("Updating DB record from Trello data", operation_id=sync_op.operation_id, card_id=card_id)
                safe_log_sync_event(sync_op.operation_id, "INFO", "Updating DB from Trello", card_id=card_id)
                
                if not rec:
                    logger.info("Creating new DB record", operation_id=sync_op.operation_id, card_id=card_id)
                    safe_log_sync_event(sync_op.operation_id, "INFO", "Creating new DB record", card_id=card_id)
                    rec = Job(
                        job=0,  # Placeholder
                        release=0,  # Placeholder
                        job_name=card_data.get("name", "Unnamed Job"),
                        source_of_update="Trello",
                        last_updated_at=event_time,
                    )
                    update_sync_operation(sync_op.operation_id, records_created=1)

                # Update trello information
                rec.trello_card_name = card_data.get("name")
                rec.trello_card_description = card_data.get("desc")
                rec.trello_list_id = card_data.get("idList")
                rec.trello_list_name = get_list_name_by_id(card_data.get("idList"))
                if card_data.get("due"):
                    rec.trello_card_date = parse_trello_datetime(card_data["due"])
                else:
                    rec.trello_card_date = None

                rec.last_updated_at = event_time
                rec.source_of_update = "Trello"

                # Handle list movement
                if event_info["event"] == "card_moved":
                    logger.info("Card move detected, updating DB fields", operation_id=sync_op.operation_id)
                    safe_log_sync_event(sync_op.operation_id, "INFO", "Card moved - updating DB fields",
                                  to=get_list_name_by_id(card_data.get("idList")))
                    rectify_db_on_trello_move(rec, get_list_name_by_id(card_data.get("idList")), sync_op.operation_id)

                db.session.add(rec)
                db.session.commit()
                update_sync_operation(sync_op.operation_id, records_updated=1)
                
                logger.info("DB record updated successfully", operation_id=sync_op.operation_id, card_id=card_id)
                safe_log_sync_event(sync_op.operation_id, "INFO", "DB record updated", card_id=card_id, job_id=rec.id)

                # Update Excel if needed
                if rec.source_of_update != "Excel":
                    logger.info("Updating Excel from Trello changes", operation_id=sync_op.operation_id)
                    safe_log_sync_event(sync_op.operation_id, "INFO", "Updating Excel from Trello", job=rec.job, release=rec.release)
                    column_updates = {
                        "M": rec.fitup_comp,
                        "N": rec.welded,
                        "O": rec.paint_comp,
                        "P": rec.ship,
                    }

                    index, row = get_excel_row_and_index_by_identifiers(rec.job, rec.release)
                    if index and row is not None:
                        logger.info(
                            "Found Excel row for update",
                            operation_id=sync_op.operation_id,
                            job=rec.job,
                            release=rec.release,
                            excel_row=index
                        )
                        try:
                            safe_log_sync_event(sync_op.operation_id, "INFO", "Found Excel row", excel_row=index, job=rec.job, release=rec.release)
                        except Exception as log_err:
                            logger.warning("Failed to log Excel row info", error=str(log_err))
                        
                        for col, val in column_updates.items():
                            cell_address = col + str(index)
                            success = update_excel_cell(cell_address, val)
                            if success:
                                logger.info("Excel cell updated", operation_id=sync_op.operation_id, cell=cell_address, value=val)
                                safe_log_sync_event(sync_op.operation_id, "INFO", "Excel cell updated", cell=cell_address, value=val)
                            else:
                                logger.error("Failed to update Excel cell", operation_id=sync_op.operation_id, cell=cell_address, value=val)
                                safe_log_sync_event(sync_op.operation_id, "ERROR", "Failed to update Excel cell", cell=cell_address, value=val)
                    else:
                        logger.warning("Excel row not found for update", operation_id=sync_op.operation_id, job=rec.job, release=rec.release)
                        safe_log_sync_event(sync_op.operation_id, "WARNING", "Excel row not found", job=rec.job, release=rec.release)
            else:
                logger.info("No update needed for card", operation_id=sync_op.operation_id, card_id=card_id)
                safe_log_sync_event(sync_op.operation_id, "INFO", "No update needed for card", card_id=card_id)
                update_sync_operation(sync_op.operation_id, status=SyncStatus.SKIPPED)
                return

            # Mark operation as completed
            update_sync_operation(
                sync_op.operation_id,
                status=SyncStatus.COMPLETED,
                completed_at=datetime.utcnow(),
                duration_seconds=(datetime.utcnow() - sync_op.started_at).total_seconds()
            )
            safe_log_sync_event(sync_op.operation_id, "INFO", "SyncOperation completed")
            
        except Exception as e:
            # Rollback any pending database changes
            try:
                db.session.rollback()
            except:
                pass
                
            logger.error(
                "Trello sync failed",
                operation_id=sync_op.operation_id,
                card_id=card_id,
                error=str(e),
                error_type=type(e).__name__
            )
            safe_log_sync_event(sync_op.operation_id, "ERROR", "Trello sync failed", card_id=card_id, error=str(e), error_type=type(e).__name__)
            update_sync_operation(
                sync_op.operation_id,
                status=SyncStatus.FAILED,
                error_type=type(e).__name__,
                error_message=str(e),
                completed_at=datetime.utcnow(),
                duration_seconds=(datetime.utcnow() - sync_op.started_at).total_seconds()
            )
            raise

# Determine Trello list based on Excel/DB status
def determine_trello_list_from_db(rec):
    if (
        rec.fitup_comp == "X"
        and rec.welded == "X"
        and rec.paint_comp == "X"
        and (rec.ship == "O" or rec.ship == "T")
    ):
        return "Paint complete"
    elif (
        rec.fitup_comp == "X"
        and rec.welded == "O"
        and rec.paint_comp == None
        and rec.ship == None
    ):
        return "Fit Up Complete."
    elif (
        rec.fitup_comp == "X"
        and rec.welded == "X"
        and rec.paint_comp == "X"
        and rec.ship == "X"
    ):
        return "Shipping completed"
    else:
        return None  # no matching list


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
    if data is None:
        logger.info("No data received from OneDrive polling")
        return

    if "last_modified_time" not in data or "data" not in data:
        logger.warning("Invalid OneDrive polling data format")
        return

    # Convert Excel last_modified_time (string) → datetime
    excel_last_updated = parse_excel_datetime(data["last_modified_time"])
    df = data["data"]

    logger.info(f"Processing OneDrive data last modified at {excel_last_updated}")
    logger.info(f"DataFrame {df.shape[0]} rows, {df.shape[1]} columns")

    updated_records = []

    # Fields to check for diffs
    fields_to_check = [
        # ("Excel column name", "DB field name", "type")
        ("Fitup comp", "fitup_comp", "text"),
        ("Welded", "welded", "text"),
        ("Paint Comp", "paint_comp", "text"),
        ("Ship", "ship", "text"),
        ("Start install", "start_install", "date"),
    ]

    for _, row in df.iterrows():
        job = row.get("Job #")
        release = row.get("Release #")
        if pd.isna(job) or pd.isna(release):
            logger.warning(f"Skipping row with missing Job # or Release #: {row}")
            continue

        identifier = f"{job}-{release}"

        rec = Job.query.filter_by(job=job, release=release).one_or_none()
        if not rec:
            continue

        db_last_updated = rec.last_updated_at

        # Check for duplicate updates from Excel itself
        if rec.source_of_update == "Excel" and excel_last_updated <= db_last_updated:
            logger.info(
                f"Skipping Excel update for {identifier}: event is older or same timestamp and originated from Excel."
            )
            continue

        # Only log diffs if Excel is newer
        if excel_last_updated <= db_last_updated:
            logger.info(
                f"Skipping {identifier}: Excel last updated {excel_last_updated} <= DB {db_last_updated}"
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
                        logger.info(
                            f"{job}-{release} Updating DB {db_field} (formula-driven): {db_val!r} -> {excel_val!r}"
                        )
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
                        setattr(rec, db_field, excel_val)
                        setattr(rec, "start_install_formula", "")
                        setattr(rec, "start_install_formulaTF", False)
                        record_updated = True
                continue  # skip generic update for this field

            # Generic update for non-special fields
            if excel_val != db_val:
                logger.info(
                    f"{job}-{release} Updating DB {db_field}: {db_val!r} -> {excel_val!r}"
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
        for rec, _ in updated_records:
            db.session.add(rec)
        db.session.commit()
        logger.info(f"Committed {len(updated_records)} updated records to DB.")

        # Trello update: due dates and list movement ONLY if the last update was NOT from Trello
        for rec, is_formula in updated_records:
            if rec.source_of_update != "Trello":
                if hasattr(rec, "trello_card_id") and rec.trello_card_id:
                    try:
                        # Determine new due date and list ID
                        new_due_date = None
                        if not is_formula and rec.start_install:
                            new_due_date = rec.start_install

                        new_list_id = None
                        new_list_name = determine_trello_list_from_db(rec)
                        if new_list_name:
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
                            # Assuming a new function `update_trello_card` is available in app.trello.api
                            # This function would take card_id, new_list_id, and new_due_date as arguments
                            update_trello_card(
                                rec.trello_card_id, new_list_id, new_due_date
                            )

                            # Update DB record with new Trello info after successful API call
                            # This block is executed ONLY if update_trello_card was successful
                            rec.trello_card_date = new_due_date
                            rec.trello_list_id = new_list_id
                            rec.trello_list_name = new_list_name
                            rec.last_updated_at = datetime.now(timezone.utc).replace(
                                tzinfo=None
                            )
                            rec.source_of_update = (
                                "Excel"  # Mark as updated by Excel via Trello API
                            )
                            db.session.add(rec)
                            db.session.commit()
                    except Exception as e:
                        logger.error(
                            f"Error updating Trello card {rec.trello_card_id}: {e}"
                        )
    else:
        logger.info("[SYNC] No records needed updating.")

    logger.info("[SYNC] OneDrive sync complete.")