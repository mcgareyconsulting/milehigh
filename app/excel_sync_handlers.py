"""
Handler classes for Excel sync operations to reduce conditional complexity.
"""
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import re

from app.models import Job, SyncOperation, SyncStatus, db
from app.sync_config import sync_config
from app.sync_exceptions import SyncException, SyncDuplicateUpdateError
from app.trello.api import get_list_by_name, update_trello_card
from app.onedrive.utils import parse_excel_datetime
from app.sync_utils import safe_log_sync_event, update_sync_operation
from app.logging_config import get_logger

logger = get_logger(__name__)


class FieldUpdateStrategy:
    """Base class for field update strategies."""
    
    def should_update_db(self, excel_val: Any, db_val: Any, row: pd.Series) -> bool:
        """Determine if database should be updated."""
        raise NotImplementedError
    
    def should_update_trello(self, excel_val: Any, db_val: Any, row: pd.Series) -> bool:
        """Determine if Trello should be updated."""
        raise NotImplementedError
    
    def update_job_fields(self, job: Job, excel_val: Any, row: pd.Series, field_name: str):
        """Update job fields based on strategy."""
        raise NotImplementedError


class TextFieldUpdateStrategy(FieldUpdateStrategy):
    """Strategy for text field updates."""
    
    def should_update_db(self, excel_val: Any, db_val: Any, row: pd.Series) -> bool:
        return excel_val != db_val
    
    def should_update_trello(self, excel_val: Any, db_val: Any, row: pd.Series) -> bool:
        return True  # Text fields can always update Trello
    
    def update_job_fields(self, job: Job, excel_val: Any, row: pd.Series, field_name: str):
        setattr(job, field_name, excel_val)


class DateFieldUpdateStrategy(FieldUpdateStrategy):
    """Strategy for date field updates with formula handling."""
    
    def should_update_db(self, excel_val: Any, db_val: Any, row: pd.Series) -> bool:
        return excel_val != db_val
    
    def should_update_trello(self, excel_val: Any, db_val: Any, row: pd.Series) -> bool:
        return not self._is_formula_cell(row)
    
    def update_job_fields(self, job: Job, excel_val: Any, row: pd.Series, field_name: str):
        setattr(job, field_name, excel_val)
        
        if self._is_formula_cell(row):
            setattr(job, "start_install_formula", row.get("start_install_formula") or "")
            setattr(job, "start_install_formulaTF", bool(row.get("start_install_formulaTF")))
        else:
            setattr(job, "start_install_formula", "")
            setattr(job, "start_install_formulaTF", False)
    
    def _is_formula_cell(self, row: pd.Series) -> bool:
        """Check if the cell is formula-driven."""
        formula_val = row.get("start_install_formula")
        formulaTF_val = row.get("start_install_formulaTF")
        return bool(formulaTF_val) or (
            isinstance(formula_val, str) and formula_val.startswith("=")
        )


class FieldUpdateStrategyFactory:
    """Factory for creating field update strategies."""
    
    _strategies = {
        "text": TextFieldUpdateStrategy(),
        "date": DateFieldUpdateStrategy(),
    }
    
    @classmethod
    def get_strategy(cls, field_type: str) -> FieldUpdateStrategy:
        """Get strategy for field type."""
        return cls._strategies.get(field_type, TextFieldUpdateStrategy())


class ExcelRowProcessor:
    """Processes individual Excel rows for updates."""
    
    def __init__(self, operation_id: str, excel_last_updated: datetime):
        self.operation_id = operation_id
        self.excel_last_updated = excel_last_updated
    
    def process_row(self, row: pd.Series) -> Optional[Tuple[Job, bool]]:
        """Process a single Excel row and return updated job and formula status."""
        try:
            job_num, release_str, identifier = self._extract_identifiers(row)
            if not job_num or not release_str:
                return None
            
            job = Job.query.filter_by(job=job_num, release=release_str).one_or_none()
            if not job:
                logger.warning(f"No record found for {identifier}")
                return None
            
            if not self._should_process_job(job, identifier):
                return None
            
            formula_status = self._update_job_from_row(job, row, identifier)
            if job in [j for j, _ in self._get_updated_records()]:
                return job, formula_status
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing row {row.get('Job #', 'unknown')}: {str(e)}")
            return None
    
    def _extract_identifiers(self, row: pd.Series) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Extract job number, release, and identifier from row."""
        job = row.get("Job #")
        release = row.get("Release #")
        
        if pd.isna(job) or pd.isna(release):
            return None, None, None
        
        job_num = self._normalize_int_like(job)
        release_str = str(release) if not pd.isna(release) else None
        identifier = f"{job}-{release}"
        
        return job_num, release_str, identifier
    
    def _normalize_int_like(self, value: Any) -> Optional[int]:
        """Normalize integer-like values."""
        if pd.isna(value) or value is None:
            return None
        if isinstance(value, int):
            return value
        try:
            if isinstance(value, str):
                digits = re.findall(r"\d+", value)
                if digits:
                    return int("".join(digits))
                return None
            import numpy as np
            if isinstance(value, (np.integer,)):
                return int(value)
        except Exception:
            return None
        return None
    
    def _should_process_job(self, job: Job, identifier: str) -> bool:
        """Check if job should be processed for updates."""
        # Check for duplicate updates from Excel
        if (job.source_of_update == "Excel" and 
            self.excel_last_updated <= job.last_updated_at):
            
            safe_log_sync_event(
                self.operation_id,
                "INFO",
                "Skipping Excel update (same origin/timestamp)",
                id=job.id,
                job=job.job,
                release=job.release,
                excel_identifier=identifier,
                excel_last_updated=str(self.excel_last_updated),
                db_last_updated=str(job.last_updated_at),
            )
            return False
        
        # Check if Excel is newer
        if self.excel_last_updated <= job.last_updated_at:
            safe_log_sync_event(
                self.operation_id,
                "INFO",
                "Skipping: Excel older than DB",
                id=job.id,
                job=job.job,
                release=job.release,
                excel_identifier=identifier,
                excel_last_updated=str(self.excel_last_updated),
                db_last_updated=str(job.last_updated_at),
            )
            return False
        
        return True
    
    def _update_job_from_row(self, job: Job, row: pd.Series, identifier: str) -> Optional[bool]:
        """Update job from Excel row and return formula status."""
        record_updated = False
        formula_status = None
        
        for field_mapping in sync_config.excel_field_mappings:
            excel_val = row.get(field_mapping.excel_column)
            db_val = getattr(job, field_mapping.db_field, None)
            
            # Normalize values based on field type
            if field_mapping.field_type == "date":
                excel_val = self._as_date(excel_val)
                db_val = self._as_date(db_val)
            
            # Skip if values are equivalent (including NaN/None)
            if (pd.isna(excel_val) or excel_val is None) and db_val is None:
                continue
            
            strategy = FieldUpdateStrategyFactory.get_strategy(field_mapping.field_type)
            
            if strategy.should_update_db(excel_val, db_val, row):
                logger.info(
                    f"{identifier} Updating DB {field_mapping.db_field}: {db_val!r} -> {excel_val!r}"
                )
                safe_log_sync_event(
                    self.operation_id,
                    "INFO",
                    f"DB field update ({field_mapping.field_type})",
                    id=job.id,
                    job=job.job,
                    release=job.release,
                    excel_identifier=identifier,
                    field=field_mapping.db_field,
                    old_value=str(db_val),
                    new_value=str(excel_val),
                )
                
                strategy.update_job_fields(job, excel_val, row, field_mapping.db_field)
                record_updated = True
                
                if field_mapping.field_type == "date":
                    formula_status = not strategy.should_update_trello(excel_val, db_val, row)
        
        if record_updated:
            job.last_updated_at = self.excel_last_updated
            job.source_of_update = "Excel"
            return formula_status
        
        return None
    
    def _as_date(self, val: Any) -> Optional[date]:
        """Convert value to date."""
        if pd.isna(val) or val is None:
            return None
        if isinstance(val, pd.Timestamp):
            return val.date()
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        try:
            return pd.to_datetime(val).date()
        except Exception:
            return None
    
    def _get_updated_records(self) -> List[Tuple[Job, Optional[bool]]]:
        """Get list of updated records (placeholder for batch processing)."""
        return []


class TrelloUpdateHandler:
    """Handles Trello updates from Excel changes."""
    
    def __init__(self, operation_id: str):
        self.operation_id = operation_id
    
    def update_trello_cards(self, updated_jobs: List[Tuple[Job, Optional[bool]]]):
        """Update Trello cards for updated jobs."""
        for job, is_formula in updated_jobs:
            if job.source_of_update != "Trello" and job.trello_card_id:
                try:
                    self._update_single_trello_card(job, is_formula)
                except Exception as e:
                    logger.error(f"Error updating Trello card {job.trello_card_id}: {e}")
                    safe_log_sync_event(
                        self.operation_id,
                        "ERROR",
                        "Error updating Trello card",
                        id=job.id,
                        job=job.job,
                        release=job.release,
                        trello_card_id=job.trello_card_id,
                        error=str(e),
                    )
    
    def _update_single_trello_card(self, job: Job, is_formula: Optional[bool]):
        """Update a single Trello card."""
        # Determine new due date and list ID
        new_due_date = None
        if not is_formula and job.start_install:
            new_due_date = job.start_install
        
        new_list_name = self._determine_trello_list_from_db(job)
        new_list_id = None
        if new_list_name:
            new_list = get_list_by_name(new_list_name)
            if new_list:
                new_list_id = new_list["id"]
        
        # Check if update is needed
        current_list_id = getattr(job, "trello_list_id", None)
        if (new_due_date != job.trello_card_date or new_list_id != current_list_id):
            
            logger.info(
                f"Updating Trello card {job.trello_card_id}: "
                f"Due Date={new_due_date} (was {job.trello_card_date}), "
                f"List={new_list_name} (was {job.trello_list_name})"
            )
            
            safe_log_sync_event(
                self.operation_id,
                "INFO",
                "Updating Trello card",
                id=job.id,
                job=job.job,
                release=job.release,
                trello_card_id=job.trello_card_id,
                current_list_name=job.trello_list_name,
                new_list_name=new_list_name,
                new_due_date=str(new_due_date) if new_due_date else None,
            )
            
            clear_due_date = (new_due_date is None and job.trello_card_date is not None)
            update_trello_card(job.trello_card_id, new_list_id, new_due_date, clear_due_date)
            
            # Update job record with new Trello info
            job.trello_card_date = new_due_date
            job.trello_list_id = new_list_id
            job.trello_list_name = new_list_name
            job.last_updated_at = datetime.now()
            job.source_of_update = "Excel"
            
            db.session.add(job)
            db.session.commit()
            
            safe_log_sync_event(
                self.operation_id,
                "INFO",
                "Trello card updated",
                id=job.id,
                job=job.job,
                release=job.release,
                trello_card_id=job.trello_card_id,
                list_name=new_list_name,
            )
    
    def _determine_trello_list_from_db(self, job: Job) -> Optional[str]:
        """Determine Trello list from database status."""
        from app.sync_handlers import TrelloListMapper
        return TrelloListMapper.determine_trello_list_from_db(job)
