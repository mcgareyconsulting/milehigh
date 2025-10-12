"""
Handler classes for different sync operations to reduce conditional complexity and improve maintainability.
"""
import pandas as pd
from datetime import datetime, date
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass

from app.models import Job, SyncOperation, SyncStatus, db
from app.sync_config import sync_config, SyncEventType
from app.sync_exceptions import (
    SyncException, SyncCardNotFoundError, SyncNoValidIdentifierError,
    SyncParseError, SyncAlreadyExistsError, SyncNotInExcelError,
    SyncDuplicateUpdateError
)
from app.trello.utils import extract_identifier, parse_trello_datetime
from app.trello.api import get_trello_card_by_id, get_list_name_by_id
from app.onedrive.utils import get_excel_row_and_index_by_identifiers
from app.seed import to_date, safe_truncate_string
from app.sync_utils import safe_log_sync_event, update_sync_operation, compare_timestamps


@dataclass
class SyncContext:
    """Context information for sync operations."""
    operation_id: str
    event_type: SyncEventType
    source_system: str
    card_id: Optional[str] = None
    event_time: Optional[datetime] = None


class TrelloListMapper:
    """Handles Trello list to database field mappings."""
    
    @staticmethod
    def determine_trello_list_from_db(job: Job) -> Optional[str]:
        """Determine Trello list based on database status."""
        for list_name, mapping in sync_config.trello_list_mappings.items():
            if (job.fitup_comp == mapping.fitup_comp and
                job.welded == mapping.welded and
                job.paint_comp == mapping.paint_comp and
                job.ship == mapping.ship):
                return list_name
        return None
    
    @staticmethod
    def update_db_from_trello_list(job: Job, trello_list_name: str, context: SyncContext):
        """Update database fields based on Trello list movement."""
        mapping = sync_config.trello_list_mappings.get(trello_list_name)
        if not mapping:
            return
        
        # Update job fields
        job.fitup_comp = mapping.fitup_comp
        job.welded = mapping.welded
        job.paint_comp = mapping.paint_comp
        job.ship = mapping.ship
        
        safe_log_sync_event(
            context.operation_id,
            "INFO",
            "Job status updated from Trello list",
            trello_card_id=context.card_id,
            new_list=trello_list_name,
            new_status={
                "fitup_comp": job.fitup_comp,
                "welded": job.welded,
                "paint_comp": job.paint_comp,
                "ship": job.ship
            }
        )


class IdentifierValidator:
    """Handles identifier extraction and validation."""
    
    @staticmethod
    def extract_and_validate_identifier(card_name: str, context: SyncContext) -> Tuple[int, str]:
        """Extract and validate job-release identifier from card name."""
        identifier = extract_identifier(card_name)
        if not identifier:
            raise SyncNoValidIdentifierError(
                f"No valid identifier found in card name: {card_name}",
                operation_id=context.operation_id,
                context={"card_name": card_name}
            )
        
        try:
            if "-V" in identifier.upper():
                job_str, release_str = identifier.split("-V", 1)
                job = int(job_str)
                release = f"V{release_str}"
            else:
                job_str, release = identifier.split("-", 1)
                job = int(job_str)
            
            return job, release
        except (ValueError, IndexError) as e:
            raise SyncParseError(
                f"Could not parse job-release from identifier: {identifier}",
                operation_id=context.operation_id,
                context={"identifier": identifier, "error": str(e)}
            )


class CardCreationHandler:
    """Handles new card creation logic."""
    
    def __init__(self, context: SyncContext):
        self.context = context
    
    def handle_new_card(self, card_data: Dict[str, Any]) -> bool:
        """Handle creation of a new card."""
        try:
            # Extract and validate identifier
            card_name = card_data.get("name", "")
            job, release = IdentifierValidator.extract_and_validate_identifier(
                card_name, self.context
            )
            identifier = f"{job}-{release}"
            
            # Check if already exists in DB
            existing_job = Job.query.filter_by(job=job, release=release).first()
            if existing_job:
                safe_log_sync_event(
                    self.context.operation_id,
                    "INFO",
                    "Job-release already exists in DB",
                    trello_card_id=self.context.card_id,
                    identifier=identifier,
                    existing_job_id=existing_job.id
                )
                update_sync_operation(
                    self.context.operation_id, 
                    status=SyncStatus.SKIPPED, 
                    error_type="AlreadyExists"
                )
                return False
            
            # Check if exists in Excel
            excel_index, excel_row = get_excel_row_and_index_by_identifiers(job, release)
            if excel_row is None:
                safe_log_sync_event(
                    self.context.operation_id,
                    "INFO",
                    "Job-release not found in Excel",
                    trello_card_id=self.context.card_id,
                    identifier=identifier
                )
                update_sync_operation(
                    self.context.operation_id,
                    status=SyncStatus.SKIPPED,
                    error_type="NotInExcel"
                )
                return False
            
            # Create new job record
            self._create_job_record(card_data, job, release, excel_row, identifier)
            return True
            
        except SyncException:
            raise
        except Exception as e:
            raise SyncException(
                f"Unexpected error creating new card: {str(e)}",
                operation_id=self.context.operation_id,
                context={"card_data": card_data}
            )
    
    def _create_job_record(self, card_data: Dict[str, Any], job: int, release: str, 
                          excel_row: pd.Series, identifier: str):
        """Create a new job record with combined Trello and Excel data."""
        card_name = card_data.get("name", "")
        
        new_job = Job(
            job=job,
            release=release,
            job_name=safe_truncate_string(card_name, 128),
            description=safe_truncate_string(excel_row.get("Description"), 256),
            fab_hrs=float(excel_row.get("Fab Hrs")) if excel_row.get("Fab Hrs") and not pd.isna(excel_row.get("Fab Hrs")) else None,
            install_hrs=float(excel_row.get("Install HRS")) if excel_row.get("Install HRS") and not pd.isna(excel_row.get("Install HRS")) else None,
            paint_color=safe_truncate_string(excel_row.get("Paint color"), 64),
            pm=safe_truncate_string(excel_row.get("PM"), 16),
            by=safe_truncate_string(excel_row.get("BY"), 16),
            released=to_date(excel_row.get("Released")) if excel_row.get("Released") and not pd.isna(excel_row.get("Released")) else None,
            fab_order=float(excel_row.get("Fab Order")) if excel_row.get("Fab Order") and not pd.isna(excel_row.get("Fab Order")) else None,
            cut_start=safe_truncate_string(excel_row.get("Cut start"), 8),
            fitup_comp=safe_truncate_string(excel_row.get("Fitup comp"), 8),
            welded=safe_truncate_string(excel_row.get("Welded"), 8),
            paint_comp=safe_truncate_string(excel_row.get("Paint Comp"), 8),
            ship=safe_truncate_string(excel_row.get("Ship"), 8),
            start_install=to_date(excel_row.get("Start install")) if excel_row.get("Start install") and not pd.isna(excel_row.get("Start install")) else None,
            start_install_formula=safe_truncate_string(excel_row.get("start_install_formula"), 256),
            start_install_formulaTF=excel_row.get("start_install_formulaTF", False),
            comp_eta=to_date(excel_row.get("Comp. ETA")) if excel_row.get("Comp. ETA") and not pd.isna(excel_row.get("Comp. ETA")) else None,
            job_comp=safe_truncate_string(excel_row.get("Job Comp"), 8),
            invoiced=safe_truncate_string(excel_row.get("Invoiced"), 8),
            notes=safe_truncate_string(excel_row.get("Notes"), 256),
            # Trello fields
            trello_card_id=self.context.card_id,
            trello_card_name=safe_truncate_string(card_name, 256),
            trello_list_id=card_data.get("idList"),
            trello_list_name=get_list_name_by_id(card_data.get("idList")),
            trello_card_description=safe_truncate_string(card_data.get("desc"), 512),
            trello_card_date=parse_trello_datetime(card_data.get("due")) if card_data.get("due") else None,
            # Metadata
            last_updated_at=self.context.event_time,
            source_of_update="Trello"
        )
        
        db.session.add(new_job)
        db.session.commit()
        
        safe_log_sync_event(
            self.context.operation_id,
            "INFO",
            "New job record created successfully",
            trello_card_id=self.context.card_id,
            identifier=identifier,
            new_job_id=new_job.id
        )
        
        update_sync_operation(
            self.context.operation_id,
            status=SyncStatus.COMPLETED,
            records_created=1
        )


class CardUpdateHandler:
    """Handles card update logic."""
    
    def __init__(self, context: SyncContext):
        self.context = context
    
    def handle_card_update(self, card_data: Dict[str, Any], job: Job, 
                          event_info: Dict[str, Any]) -> bool:
        """Handle card update logic."""
        try:
            # Check for duplicate updates
            if self._is_duplicate_update(job):
                return False
            
            # Check if update is needed
            if not self._is_update_needed(job):
                return False
            
            # Update Trello information
            self._update_trello_fields(job, card_data)
            
            # Handle special events
            if event_info.get("event") == "card_moved":
                self._handle_card_move(job, card_data)
            
            # Save changes
            db.session.add(job)
            db.session.commit()
            update_sync_operation(self.context.operation_id, records_updated=1)
            
            safe_log_sync_event(
                self.context.operation_id,
                "INFO",
                "DB record updated",
                trello_card_id=self.context.card_id,
                id=job.id,
                job=job.job,
                release=job.release,
            )
            
            return True
            
        except Exception as e:
            raise SyncException(
                f"Error updating card: {str(e)}",
                operation_id=self.context.operation_id,
                context={"card_data": card_data, "job_id": job.id}
            )
    
    def _is_duplicate_update(self, job: Job) -> bool:
        """Check if this is a duplicate update."""
        if (job.source_of_update == "Trello" and 
            self.context.event_time and 
            self.context.event_time <= job.last_updated_at):
            
            safe_log_sync_event(
                self.context.operation_id,
                "INFO",
                "Duplicate Trello event skipped",
                trello_card_id=self.context.card_id,
                job_id=job.id,
                event_time=str(self.context.event_time),
                db_last_updated=str(job.last_updated_at),
            )
            update_sync_operation(self.context.operation_id, status=SyncStatus.SKIPPED)
            return True
        return False
    
    def _is_update_needed(self, job: Job) -> bool:
        """Check if update is needed based on timestamps."""
        diff = compare_timestamps(
            self.context.event_time, 
            job.last_updated_at, 
            self.context.operation_id
        )
        return diff == "newer"
    
    def _update_trello_fields(self, job: Job, card_data: Dict[str, Any]):
        """Update Trello-related fields in the job record."""
        job.trello_card_name = card_data.get("name")
        job.trello_card_description = card_data.get("desc")
        job.trello_list_id = card_data.get("idList")
        job.trello_list_name = get_list_name_by_id(card_data.get("idList"))
        
        if card_data.get("due"):
            job.trello_card_date = parse_trello_datetime(card_data["due"])
        else:
            job.trello_card_date = None
        
        job.last_updated_at = self.context.event_time
        job.source_of_update = "Trello"
    
    def _handle_card_move(self, job: Job, card_data: Dict[str, Any]):
        """Handle card movement between lists."""
        trello_list_name = get_list_name_by_id(card_data.get("idList"))
        TrelloListMapper.update_db_from_trello_list(job, trello_list_name, self.context)
        
        safe_log_sync_event(
            self.context.operation_id,
            "INFO",
            "Card moved - updating DB fields",
            trello_card_id=self.context.card_id,
            to=trello_list_name,
        )
