"""
Refactored sync module with reduced conditional complexity and improved structure.
"""
import pandas as pd
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.models import Job, SyncOperation, SyncStatus, db
from app.sync_config import sync_config, SyncEventType, SyncSource
from app.sync_exceptions import (
    SyncException, SyncCardNotFoundError, SyncValidationError
)
from app.sync_handlers import (
    SyncContext, CardCreationHandler, CardUpdateHandler, TrelloListMapper
)
from app.excel_sync_handlers import ExcelRowProcessor, TrelloUpdateHandler
from app.trello.api import get_trello_card_by_id
from app.trello.utils import parse_trello_datetime
from app.onedrive.utils import parse_excel_datetime
from app.sync import (
    safe_log_sync_event, update_sync_operation, create_sync_operation,
    check_database_connection, safe_sync_op_call
)
from app.logging_config import get_logger, SyncContext as LogSyncContext

logger = get_logger(__name__)


class SyncOperationFactory:
    """Factory for creating sync operations."""
    
    @staticmethod
    def create_trello_operation(card_id: str) -> SyncOperation:
        """Create a Trello sync operation."""
        return create_sync_operation(
            operation_type="trello_webhook",
            source_system=SyncSource.TRELLO.value,
            source_id=card_id
        )
    
    @staticmethod
    def create_onedrive_operation() -> Optional[SyncOperation]:
        """Create an OneDrive sync operation."""
        if not check_database_connection():
            logger.warning("Database connection unavailable - proceeding without sync operation logging")
            return None
        
        try:
            return create_sync_operation(
                operation_type="onedrive_poll",
                source_system=SyncSource.ONEDRIVE.value,
                source_id=None
            )
        except Exception as e:
            logger.warning(f"Failed to create sync operation: {str(e)}")
            return None


class SyncValidator:
    """Validates sync data and operations."""
    
    @staticmethod
    def validate_trello_event(event_info: Dict[str, Any]) -> bool:
        """Validate Trello event info."""
        if not event_info or not event_info.get("handled"):
            return False
        
        required_fields = ["card_id"]
        return all(field in event_info for field in required_fields)
    
    @staticmethod
    def validate_onedrive_data(data: Dict[str, Any]) -> bool:
        """Validate OneDrive data."""
        if not data:
            return False
        
        required_fields = ["last_modified_time", "data"]
        return all(field in data for field in required_fields)


class TrelloSyncManager:
    """Manages Trello sync operations."""
    
    def __init__(self, operation_id: str):
        self.operation_id = operation_id
        self.context = None
    
    def sync_from_trello(self, event_info: Dict[str, Any]) -> None:
        """Main entry point for Trello sync operations."""
        if not SyncValidator.validate_trello_event(event_info):
            logger.info("No actionable event info received from Trello webhook")
            return
        
        card_id = event_info["card_id"]
        event_time = parse_trello_datetime(event_info.get("time"))
        
        # Create sync context
        self.context = SyncContext(
            operation_id=self.operation_id,
            event_type=SyncEventType(event_info.get("event", "unhandled")),
            source_system=SyncSource.TRELLO.value,
            card_id=card_id,
            event_time=event_time
        )
        
        try:
            self._process_trello_event(event_info)
        except SyncException as e:
            self._handle_sync_error(e, event_info)
        except Exception as e:
            self._handle_unexpected_error(e, event_info)
    
    def _process_trello_event(self, event_info: Dict[str, Any]) -> None:
        """Process the Trello event."""
        update_sync_operation(self.operation_id, status=SyncStatus.IN_PROGRESS)
        
        # Get card data from Trello API
        card_data = get_trello_card_by_id(self.context.card_id)
        if not card_data:
            raise SyncCardNotFoundError(
                f"Card not found in Trello API: {self.context.card_id}",
                operation_id=self.operation_id,
                context={"card_id": self.context.card_id}
            )
        
        # Find existing job record
        job = Job.query.filter_by(trello_card_id=self.context.card_id).one_or_none()
        
        if not job:
            self._handle_new_card(card_data, event_info)
        else:
            self._handle_existing_card(card_data, job, event_info)
    
    def _handle_new_card(self, card_data: Dict[str, Any], event_info: Dict[str, Any]) -> None:
        """Handle new card creation."""
        if event_info.get("event") != "card_created":
            safe_log_sync_event(
                self.operation_id,
                "INFO",
                "No DB record found for card - ignoring webhook",
                trello_card_id=self.context.card_id,
                trello_name=card_data.get("name"),
            )
            update_sync_operation(
                self.operation_id,
                status=SyncStatus.SKIPPED,
                error_type="NoDbRecord"
            )
            return
        
        handler = CardCreationHandler(self.context)
        handler.handle_new_card(card_data)
    
    def _handle_existing_card(self, card_data: Dict[str, Any], job: Job, 
                            event_info: Dict[str, Any]) -> None:
        """Handle existing card updates."""
        handler = CardUpdateHandler(self.context)
        if handler.handle_card_update(card_data, job, event_info):
            self._update_excel_if_needed(job)
        
        self._complete_operation()
    
    def _update_excel_if_needed(self, job: Job) -> None:
        """Update Excel if needed."""
        if job.source_of_update == "Excel":
            return  # Skip if last update was from Excel
        
        logger.info("Updating Excel from Trello changes", operation_id=self.operation_id)
        
        # Use configuration for column mappings
        column_updates = {
            sync_config.excel_update_columns.get("fitup_comp", "M"): job.fitup_comp,
            sync_config.excel_update_columns.get("welded", "N"): job.welded,
            sync_config.excel_update_columns.get("paint_comp", "O"): job.paint_comp,
            sync_config.excel_update_columns.get("ship", "P"): job.ship,
        }
        
        self._apply_excel_updates(job, column_updates)
    
    def _apply_excel_updates(self, job: Job, column_updates: Dict[str, Any]) -> None:
        """Apply updates to Excel file."""
        from app.onedrive.utils import get_excel_row_and_index_by_identifiers
        from app.onedrive.api import update_excel_cell
        
        index, row = get_excel_row_and_index_by_identifiers(job.job, job.release)
        if index and row is not None:
            for col, val in column_updates.items():
                cell_address = col + str(index)
                success = update_excel_cell(cell_address, val)
                self._log_excel_update_result(job, cell_address, val, success)
        else:
            safe_log_sync_event(
                self.operation_id,
                "WARNING",
                "Excel row not found",
                id=job.id,
                job=job.job,
                release=job.release,
                trello_card_id=self.context.card_id,
                excel_identifier=f"{job.job}-{job.release}",
            )
    
    def _log_excel_update_result(self, job: Job, cell_address: str, value: Any, success: bool) -> None:
        """Log Excel update result."""
        level = "INFO" if success else "ERROR"
        message = "Excel cell updated" if success else "Failed to update Excel cell"
        
        safe_log_sync_event(
            self.operation_id,
            level,
            message,
            id=job.id,
            job=job.job,
            release=job.release,
            trello_card_id=self.context.card_id,
            excel_identifier=f"{job.job}-{job.release}",
            cell=cell_address,
            value=val,
        )
    
    def _complete_operation(self) -> None:
        """Mark operation as completed."""
        update_sync_operation(
            self.operation_id,
            status=SyncStatus.COMPLETED,
            completed_at=datetime.utcnow(),
        )
        safe_log_sync_event(self.operation_id, "INFO", "SyncOperation completed")
    
    def _handle_sync_error(self, error: SyncException, event_info: Dict[str, Any]) -> None:
        """Handle sync-specific errors."""
        logger.error(f"Trello sync failed: {error.error_type}", 
                    operation_id=self.operation_id,
                    error=str(error),
                    context=error.context)
        
        try:
            update_sync_operation(
                self.operation_id,
                status=SyncStatus.FAILED,
                error_type=error.error_type,
                error_message=str(error),
                completed_at=datetime.utcnow(),
            )
            safe_log_sync_event(
                self.operation_id,
                "ERROR",
                f"Trello sync failed: {error.error_type}",
                trello_card_id=self.context.card_id if self.context else None,
                error=str(error),
                context=error.context
            )
        except Exception as log_error:
            logger.warning(f"Failed to log sync error: {str(log_error)}")
    
    def _handle_unexpected_error(self, error: Exception, event_info: Dict[str, Any]) -> None:
        """Handle unexpected errors."""
        logger.error("Unexpected Trello sync error", 
                    operation_id=self.operation_id,
                    error=str(error),
                    error_type=type(error).__name__)
        
        try:
            update_sync_operation(
                self.operation_id,
                status=SyncStatus.FAILED,
                error_type=type(error).__name__,
                error_message=str(error),
                completed_at=datetime.utcnow(),
            )
        except Exception as update_error:
            logger.warning(f"Failed to update sync operation: {str(update_error)}")
        
        raise


class OneDriveSyncManager:
    """Manages OneDrive sync operations."""
    
    def __init__(self, operation_id: Optional[str]):
        self.operation_id = operation_id
    
    def sync_from_onedrive(self, data: Dict[str, Any]) -> None:
        """Main entry point for OneDrive sync operations."""
        if not SyncValidator.validate_onedrive_data(data):
            logger.warning("Invalid OneDrive data format")
            if self.operation_id:
                update_sync_operation(
                    self.operation_id,
                    status=SyncStatus.FAILED,
                    error_type="InvalidPayload"
                )
            return
        
        try:
            self._process_onedrive_data(data)
        except Exception as e:
            self._handle_sync_error(e, data)
    
    def _process_onedrive_data(self, data: Dict[str, Any]) -> None:
        """Process OneDrive data."""
        if self.operation_id:
            update_sync_operation(self.operation_id, status=SyncStatus.IN_PROGRESS)
        
        # Parse Excel timestamp
        excel_last_updated = parse_excel_datetime(data["last_modified_time"])
        df = data["data"]
        
        if df is None or df.empty:
            logger.warning("Empty DataFrame received from OneDrive")
            if self.operation_id:
                update_sync_operation(self.operation_id, status=SyncStatus.SKIPPED)
            return
        
        # Process Excel rows
        updated_records = self._process_excel_rows(df, excel_last_updated)
        
        if updated_records:
            self._commit_database_changes(updated_records)
            self._update_trello_cards(updated_records)
        else:
            logger.info("No records needed updating")
            if self.operation_id:
                safe_log_sync_event(self.operation_id, "INFO", "No records needed updating")
        
        self._complete_operation()
    
    def _process_excel_rows(self, df: pd.DataFrame, excel_last_updated: datetime) -> list:
        """Process all Excel rows and return updated records."""
        processor = ExcelRowProcessor(self.operation_id, excel_last_updated)
        updated_records = []
        
        for _, row in df.iterrows():
            result = processor.process_row(row)
            if result:
                updated_records.append(result)
        
        return updated_records
    
    def _commit_database_changes(self, updated_records: list) -> None:
        """Commit all database changes."""
        logger.info(f"Committing {len(updated_records)} updated records to DB")
        
        try:
            for job, _ in updated_records:
                db.session.add(job)
            db.session.commit()
            
            logger.info(f"Committed {len(updated_records)} updated records to DB")
            if self.operation_id:
                safe_log_sync_event(
                    self.operation_id,
                    "INFO",
                    "DB commit completed",
                    updated_records=len(updated_records),
                )
        except Exception as e:
            logger.error(f"Failed to commit database changes: {str(e)}")
            try:
                db.session.rollback()
            except Exception:
                pass
            raise
    
    def _update_trello_cards(self, updated_records: list) -> None:
        """Update Trello cards for updated records."""
        if not self.operation_id:
            return
        
        handler = TrelloUpdateHandler(self.operation_id)
        handler.update_trello_cards(updated_records)
    
    def _complete_operation(self) -> None:
        """Mark operation as completed."""
        if self.operation_id:
            try:
                duration = (datetime.utcnow() - 
                          SyncOperation.query.filter_by(operation_id=self.operation_id)
                          .first().started_at).total_seconds()
                
                update_sync_operation(
                    self.operation_id,
                    status=SyncStatus.COMPLETED,
                    completed_at=datetime.utcnow(),
                    duration_seconds=duration
                )
                safe_log_sync_event(self.operation_id, "INFO", "SyncOperation completed")
            except Exception as e:
                logger.warning(f"Failed to mark sync operation as completed: {str(e)}")
    
    def _handle_sync_error(self, error: Exception, data: Dict[str, Any]) -> None:
        """Handle sync errors."""
        logger.error("OneDrive sync failed", 
                    operation_id=self.operation_id,
                    error=str(error),
                    error_type=type(error).__name__)
        
        try:
            db.session.rollback()
        except Exception:
            pass
        
        if self.operation_id:
            try:
                duration = (datetime.utcnow() - 
                          SyncOperation.query.filter_by(operation_id=self.operation_id)
                          .first().started_at).total_seconds()
                
                update_sync_operation(
                    self.operation_id,
                    status=SyncStatus.FAILED,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    completed_at=datetime.utcnow(),
                    duration_seconds=duration
                )
            except Exception as update_error:
                logger.warning(f"Failed to update sync operation: {str(update_error)}")
        
        raise


# Public API functions that maintain backward compatibility
def sync_from_trello(event_info: Dict[str, Any]) -> None:
    """Sync data from Trello to OneDrive based on webhook payload."""
    sync_op = SyncOperationFactory.create_trello_operation(
        event_info.get("card_id", "unknown")
    )
    
    safe_log_sync_event(
        sync_op.operation_id,
        "INFO",
        "SyncOperation created",
        trello_card_id=event_info.get("card_id"),
        event=event_info.get("event"),
    )
    
    with LogSyncContext("trello_webhook", sync_op.operation_id):
        manager = TrelloSyncManager(sync_op.operation_id)
        manager.sync_from_trello(event_info)


def sync_from_onedrive(data: Dict[str, Any]) -> None:
    """Sync data from OneDrive to Trello based on polling payload."""
    sync_op = SyncOperationFactory.create_onedrive_operation()
    
    if sync_op:
        safe_log_sync_event(sync_op.operation_id, "INFO", "SyncOperation created")
        logger.info("OneDrive poll sync operation logged to database", 
                   operation_id=sync_op.operation_id)
    else:
        logger.warning("Database connection unavailable - proceeding without sync operation logging")
    
    manager = OneDriveSyncManager(sync_op.operation_id if sync_op else None)
    manager.sync_from_onedrive(data)
