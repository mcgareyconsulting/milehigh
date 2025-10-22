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

logger = get_logger(__name__)


def safe_log_sync_event(operation_id: str, level: str, message: str, **kwargs):
    """Safely log a sync event, converting problematic types."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Convert problematic types to safe JSON-serializable types
            def make_json_safe(obj):
                import numpy as np
                import pandas as pd
                from datetime import datetime, date
                from decimal import Decimal
                
                if obj is pd.NA:
                    return None
                if isinstance(obj, (np.integer, np.int64, np.int32)):
                    return int(obj)
                elif isinstance(obj, (np.floating, np.float64, np.float32)):
                    return float(obj)
                elif isinstance(obj, (np.bool_,)):
                    return bool(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, pd.Timestamp):
                    return obj.isoformat()
                elif isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                elif isinstance(obj, Decimal):
                    return float(obj)
                elif hasattr(obj, 'item'):  # other numpy scalars
                    return obj.item()
                elif isinstance(obj, dict):
                    return {k: make_json_safe(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [make_json_safe(item) for item in obj]
                elif isinstance(obj, set):
                    return [make_json_safe(item) for item in obj]
                else:
                    return obj
            
            # Extract well-known identifiers for first-class columns
            job_id = kwargs.pop("job_id", None)
            trello_card_id = kwargs.pop("trello_card_id", None) or kwargs.pop("card_id", None)
            excel_identifier = kwargs.pop("excel_identifier", None)

            safe_data = make_json_safe(kwargs)
            
            sync_log = SyncLog(
                operation_id=operation_id,
                level=level,
                message=message,
                job_id=job_id,
                trello_card_id=trello_card_id,
                excel_identifier=excel_identifier,
                data=safe_data
            )
            db.session.add(sync_log)
            db.session.commit()
            return  # Success, exit retry loop
            
        except Exception as e:
            # Don't let logging failures break the sync
            try:
                db.session.rollback()
            except Exception:
                pass
            
            if attempt < max_retries - 1:
                # Wait before retry (exponential backoff)
                import time
                time.sleep(0.1 * (2 ** attempt))
                continue
            else:
                # Final attempt failed
                logger.warning("Failed to log sync event after retries", 
                             error=str(e), 
                             operation_id=operation_id, 
                             message=message,
                             error_type=type(e).__name__)
                break

def safe_sync_op_call(sync_op, func, *args, **kwargs):
    """Safely call a function with sync operation context."""
    if sync_op:
        try:
            return func(sync_op.operation_id, *args, **kwargs)
        except Exception as e:
            logger.warning("Failed to execute sync operation call", 
                         error=str(e), 
                         operation_id=sync_op.operation_id,
                         function_name=func.__name__ if hasattr(func, '__name__') else str(func))
    return None

def check_database_connection():
    """Check if database connection is working."""
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning("Database connection check failed", error=str(e))
        return False

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
    """Update a sync operation record with proper error handling."""
    try:
        sync_op = SyncOperation.query.filter_by(operation_id=operation_id).first()
        if sync_op:
            for key, value in kwargs.items():
                if hasattr(sync_op, key):
                    setattr(sync_op, key, value)
            db.session.commit()
        return sync_op
    except Exception as e:
        # Log the error but don't let it break the sync
        logger.warning(
            "Failed to update sync operation", 
            operation_id=operation_id, 
            error=str(e),
            error_type=type(e).__name__
        )
        try:
            db.session.rollback()
        except Exception:
            pass  # Ignore rollback errors
        return None

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
    
    if new_trello_list == "Paint complete" or new_trello_list == "Store at MHMW for shipping" or new_trello_list == "Shipping planning":
        job.fitup_comp = "X"
        job.welded = "X"
        job.paint_comp = "X"
        job.ship = "T"
    elif new_trello_list == "Fit Up Complete.":
        job.fitup_comp = "X"
        job.welded = "O"
        job.paint_comp = ""
        job.ship = "T"
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
    # print type of card id
    print(type(card_id))
    
    event_time = parse_trello_datetime(event_info.get("time"))
    
    # Create sync operation record
    sync_op = create_sync_operation(
        operation_type="trello_webhook",
        source_system="trello",
        source_id=card_id
    )
    safe_log_sync_event(
        sync_op.operation_id,
        "INFO",
        "SyncOperation created",
        trello_card_id=card_id,
        event=event_info.get("event"),
    )
    
    with SyncContext("trello_webhook", sync_op.operation_id):
        try:
            # Update operation status
            update_sync_operation(sync_op.operation_id, status=SyncStatus.IN_PROGRESS)
            safe_log_sync_event(
                sync_op.operation_id, "INFO", "SyncOperation in_progress", trello_card_id=card_id
            )
            
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
                safe_log_sync_event(
                    sync_op.operation_id, "WARNING", "Card not found in Trello API", trello_card_id=card_id
                )
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
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "Comparing Trello card to DB record",
                    trello_card_id=card_id,
                    id=rec.id,
                    job=rec.job,
                    release=rec.release,
                    trello_name=card_data.get("name"),
                    db_name=rec.trello_card_name,
                )
            else:
                logger.info(
                    "No DB record found for card - ignoring webhook",
                    operation_id=sync_op.operation_id,
                    card_id=card_id,
                    trello_name=card_data.get("name")
                )
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "No DB record found for card - ignoring webhook",
                    trello_card_id=card_id,
                    trello_name=card_data.get("name"),
                )
                update_sync_operation(sync_op.operation_id, status=SyncStatus.SKIPPED, error_type="NoDbRecord")
                return

            # Check for duplicate updates
            if rec and rec.source_of_update == "Trello" and event_time <= rec.last_updated_at:
                logger.info(
                    "Skipping duplicate Trello update",
                    operation_id=sync_op.operation_id,
                    card_id=card_id,
                    event_time=event_time.isoformat() if event_time else None,
                    db_last_updated=rec.last_updated_at.isoformat() if rec.last_updated_at else None
                )
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "Duplicate Trello event skipped",
                    trello_card_id=card_id,
                    job_id=(rec.id if rec else None),
                    event_time=str(event_time),
                    db_last_updated=str(rec.last_updated_at if rec else None),
                )
                update_sync_operation(sync_op.operation_id, status=SyncStatus.SKIPPED)
                return

            # Check if update is needed
            diff = compare_timestamps(event_time, rec.last_updated_at if rec else None, sync_op.operation_id)
            if diff == "newer":
                logger.info("Updating DB record from Trello data", operation_id=sync_op.operation_id, card_id=card_id)
                safe_log_sync_event(
                    sync_op.operation_id, "INFO", "Updating DB from Trello", trello_card_id=card_id
                )
                
                if not rec:
                    logger.info("Creating new DB record", operation_id=sync_op.operation_id, card_id=card_id)
                    safe_log_sync_event(
                        sync_op.operation_id, "INFO", "Creating new DB record", trello_card_id=card_id
                    )
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
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "Card moved - updating DB fields",
                        trello_card_id=card_id,
                        to=get_list_name_by_id(card_data.get("idList")),
                    )
                    rectify_db_on_trello_move(rec, get_list_name_by_id(card_data.get("idList")), sync_op.operation_id)

                db.session.add(rec)
                db.session.commit()
                update_sync_operation(sync_op.operation_id, records_updated=1)
                
                logger.info("DB record updated successfully", operation_id=sync_op.operation_id, card_id=card_id)
                safe_log_sync_event(
                    sync_op.operation_id,
                    "INFO",
                    "DB record updated",
                    trello_card_id=card_id,
                    id=rec.id,
                    job=rec.job,
                    release=rec.release,
                )

                # Update Excel if needed
                if rec.source_of_update != "Excel":
                    logger.info("Updating Excel from Trello changes", operation_id=sync_op.operation_id)
                    safe_log_sync_event(
                        sync_op.operation_id,
                        "INFO",
                        "Updating Excel from Trello",
                        id=rec.id,
                        job=rec.job,
                        release=rec.release,
                        excel_identifier=f"{rec.job}-{rec.release}",
                    )
                    column_updates = {
                        "M": rec.fitup_comp,
                        "N": rec.welded,
                        "O": rec.paint_comp,
                        "P": rec.ship,
                    }

                    # Debug the lookup values
                    logger.info(
                        "Looking up Excel row",
                        operation_id=sync_op.operation_id,
                        job=rec.job,
                        release=rec.release,
                        job_type=type(rec.job).__name__,
                        release_type=type(rec.release).__name__
                    )
                    
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
                            safe_log_sync_event(
                                sync_op.operation_id,
                                "INFO",
                                "Found Excel row",
                                id=rec.id,
                                job=rec.job,
                                release=rec.release,
                                trello_card_id=card_id,
                                excel_identifier=f"{rec.job}-{rec.release}",
                                excel_row=index,
                            )
                        except Exception as log_err:
                            logger.warning("Failed to log Excel row info", error=str(log_err))
                        
                        for col, val in column_updates.items():
                            cell_address = col + str(index)
                            success = update_excel_cell(cell_address, val)
                            if success:
                                logger.info("Excel cell updated", operation_id=sync_op.operation_id, cell=cell_address, value=val)
                                safe_log_sync_event(
                                    sync_op.operation_id,
                                    "INFO",
                                    "Excel cell updated",
                                    id=rec.id,
                                    job=rec.job,
                                    release=rec.release,
                                    trello_card_id=card_id,
                                    excel_identifier=f"{rec.job}-{rec.release}",
                                    cell=cell_address,
                                    value=val,
                                )
                            else:
                                logger.error("Failed to update Excel cell", operation_id=sync_op.operation_id, cell=cell_address, value=val)
                                safe_log_sync_event(
                                    sync_op.operation_id,
                                    "ERROR",
                                    "Failed to update Excel cell",
                                    id=rec.id,
                                    job=rec.job,
                                    release=rec.release,
                                    trello_card_id=card_id,
                                    excel_identifier=f"{rec.job}-{rec.release}",
                                    cell=cell_address,
                                    value=val,
                                )
                    else:
                        logger.warning(
                            "Excel row not found for update", 
                            operation_id=sync_op.operation_id, 
                            job=rec.job, 
                            release=rec.release,
                            job_type=type(rec.job).__name__,
                            release_type=type(rec.release).__name__,
                            excel_identifier=f"{rec.job}-{rec.release}"
                        )
                        safe_log_sync_event(
                            sync_op.operation_id,
                            "WARNING",
                            "Excel row not found",
                            id=rec.id,
                            job=rec.job,
                            release=rec.release,
                            trello_card_id=card_id,
                            excel_identifier=f"{rec.job}-{rec.release}",
                            job_type=type(rec.job).__name__,
                            release_type=type(rec.release).__name__
                        )
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
            safe_log_sync_event(sync_op.operation_id, "INFO", "SyncOperation completed", trello_card_id=card_id)
            
        except Exception as e:
            # Rollback any pending database changes
            try:
                db.session.rollback()
            except Exception as rollback_error:
                logger.warning("Failed to rollback database changes", 
                             error=str(rollback_error), 
                             operation_id=sync_op.operation_id)
                
            error_context = {
                "operation_id": sync_op.operation_id,
                "card_id": card_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event_type": event_info.get("event") if event_info else None
            }
            
            logger.error("Trello sync failed", **error_context)
            
            try:
                safe_log_sync_event(
                    sync_op.operation_id,
                    "ERROR",
                    "Trello sync failed",
                    trello_card_id=card_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    event_type=event_info.get("event") if event_info else None
                )
            except Exception as log_error:
                logger.warning("Failed to log sync error", error=str(log_error))
            
            try:
                update_sync_operation(
                    sync_op.operation_id,
                    status=SyncStatus.FAILED,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    completed_at=datetime.utcnow(),
                    duration_seconds=(datetime.utcnow() - sync_op.started_at).total_seconds()
                )
            except Exception as update_error:
                logger.warning("Failed to update sync operation status", error=str(update_error))
            
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
        and rec.paint_comp == ""
        and rec.ship == "T"
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
                            logger.info(
                                f"{job}-{release} Updating DB {db_field} (formula-driven): {db_val!r} -> {excel_val!r}"
                            )
                            safe_log_sync_event(
                                sync_op.operation_id,
                                "INFO",
                                "DB field update (formula-driven)",
                                id=rec.id,
                                job=rec.job,
                                release=rec.release,
                                excel_identifier=identifier,
                                field=db_field,
                                old_value=str(db_val),
                                new_value=str(excel_val),
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
                            # Determine new start date and list ID
                            new_start_date = None
                            if not is_formula and rec.start_install:
                                # Set start date to 2 business days before the start_install date
                                new_start_date = calculate_business_days_before(rec.start_install, 2)

                            new_list_id = None
                            new_list_name = determine_trello_list_from_db(rec)
                            if new_list_name:
                                new_list = get_list_by_name(new_list_name)
                                if new_list:
                                    new_list_id = new_list["id"]

                            # Only update Trello if there's a change in start date or list
                            current_list_id = getattr(rec, "trello_list_id", None)
                            if (
                                new_start_date != rec.trello_card_date
                                or new_list_id != current_list_id
                            ):
                                logger.info(
                                    f"Updating Trello card {rec.trello_card_id}: Start Date={{new_start_date}} (was {rec.trello_card_date}), List={{new_list_name}} (was {rec.trello_list_name})"
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
                                    new_start_date=str(new_start_date) if new_start_date else None,
                                )
                                # Determine if we need to clear the start date
                                clear_start_date = (new_start_date is None and rec.trello_card_date is not None)
                                if clear_start_date:
                                    logger.info(
                                        "Clearing start date for Trello card",
                                        operation_id=sync_op.operation_id,
                                        trello_card_id=rec.trello_card_id,
                                        current_start_date=str(rec.trello_card_date)
                                    )
                                update_trello_card(
                                    rec.trello_card_id, new_list_id, new_start_date, clear_start_date
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
                                rec.trello_card_date = new_start_date
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
            safe_log_sync_event(sync_op.operation_id, "INFO", "No records needed updating")

        # Mark operation as completed
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