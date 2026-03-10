"""
Database mapping service for cross-database job synchronization.

This module provides functions to map and synchronize job data between
production and sandbox databases using (job, release) tuple matching.
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine
import pandas as pd


@dataclass
class FieldMapping:
    """Configuration for mapping a single field from source to target."""
    source_field: str
    target_field: str
    transform: Optional[callable] = None  # Optional transformation function


@dataclass
class JobMappingResult:
    """Result of mapping a single job."""
    job_id: int
    release: str
    matched: bool
    fields_updated: Dict[str, Tuple[Any, Any]] = None  # {field: (old, new)}
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.fields_updated is None:
            self.fields_updated = {}


@dataclass
class MappingStatistics:
    """Statistics about a mapping operation."""
    total_source: int
    total_target: int
    matched: int
    not_found: int
    updated: int
    errors: int
    field_updates: Dict[str, int] = None  # {field: count}
    
    def __post_init__(self):
        if self.field_updates is None:
            self.field_updates = {}


class DatabaseMappingService:
    """Service for mapping jobs between databases."""
    
    @staticmethod
    def fetch_jobs(
        engine: Engine,
        columns: Optional[List[str]] = None,
        where_clause: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Fetch jobs from a database.
        
        Args:
            engine: SQLAlchemy engine
            columns: List of columns to fetch (defaults to all)
            where_clause: Optional WHERE clause condition
        
        Returns:
            DataFrame with job data
        """
        if columns is None:
            columns = ["id", "job", "release", "fab_order"]
        
        column_str = ", ".join(columns)
        query = f"SELECT {column_str} FROM jobs"
        
        if where_clause:
            query += f" WHERE {where_clause}"
        
        query += " ORDER BY job, release"
        
        return pd.read_sql_query(query, engine)
    
    @staticmethod
    def create_job_lookup(
        df: pd.DataFrame,
        key_columns: Tuple[str, str] = ("job", "release")
    ) -> Dict[Tuple, Dict[str, Any]]:
        """
        Create a lookup dictionary for jobs indexed by (job, release).
        
        Args:
            df: DataFrame with job data
            key_columns: Tuple of (job_col, release_col)
        
        Returns:
            Dictionary mapping (job, release) to row data
        """
        lookup = {}
        for _, row in df.iterrows():
            key = (row[key_columns[0]], row[key_columns[1]])
            lookup[key] = row.to_dict()
        return lookup
    
    @staticmethod
    def map_jobs_by_key(
        source_df: pd.DataFrame,
        target_df: pd.DataFrame,
        key_columns: Tuple[str, str] = ("job", "release"),
        field_mappings: Optional[List[FieldMapping]] = None
    ) -> Tuple[List[JobMappingResult], MappingStatistics]:
        """
        Map jobs from source to target by (job, release) key.
        
        Args:
            source_df: DataFrame from source database
            target_df: DataFrame from target database
            key_columns: Tuple of (job_col, release_col)
            field_mappings: Optional list of field mappings to apply
        
        Returns:
            Tuple of (list of mapping results, statistics)
        """
        results = []
        stats = MappingStatistics(
            total_source=len(source_df),
            total_target=len(target_df),
            matched=0,
            not_found=0,
            updated=0,
            errors=0
        )
        
        # Create target lookup
        target_lookup = DatabaseMappingService.create_job_lookup(
            target_df,
            key_columns
        )
        
        # Initialize field update counts
        if field_mappings:
            for mapping in field_mappings:
                stats.field_updates[mapping.target_field] = 0
        
        job_col, release_col = key_columns
        
        # Match each source job to target
        for _, source_row in source_df.iterrows():
            job_key = (source_row[job_col], source_row[release_col])
            
            if job_key in target_lookup:
                target_row = target_lookup[job_key]
                fields_updated = {}
                
                # Check field mappings
                if field_mappings:
                    for mapping in field_mappings:
                        source_val = source_row.get(mapping.source_field)
                        target_val = target_row.get(mapping.target_field)
                        
                        # Apply transformation if provided
                        if mapping.transform and source_val is not None:
                            source_val = mapping.transform(source_val)
                        
                        # Record if different
                        if source_val != target_val:
                            fields_updated[mapping.target_field] = (target_val, source_val)
                            stats.field_updates[mapping.target_field] += 1
                
                result = JobMappingResult(
                    job_id=source_row[job_col],
                    release=source_row[release_col],
                    matched=True,
                    fields_updated=fields_updated
                )
                stats.matched += 1
                
                if fields_updated:
                    stats.updated += 1
            else:
                result = JobMappingResult(
                    job_id=source_row[job_col],
                    release=source_row[release_col],
                    matched=False,
                    error=f"Job not found in target database"
                )
                stats.not_found += 1
            
            results.append(result)
        
        return results, stats
    
    @staticmethod
    def apply_field_updates(
        engine: Engine,
        results: List[JobMappingResult],
        dry_run: bool = False,
        log_callback: Optional[callable] = None
    ) -> int:
        """
        Apply field updates to target database.
        
        Args:
            engine: SQLAlchemy engine for target database
            results: List of mapping results with updates
            dry_run: If True, don't make actual changes
            log_callback: Optional callback function for logging (receives log_level, message)
        
        Returns:
            Number of successful updates
        """
        def log(level: str, msg: str):
            if log_callback:
                log_callback(level, msg)
        
        updates_count = 0
        failed_count = 0
        
        # Filter for jobs that need updates
        jobs_to_update = [r for r in results if r.matched and r.fields_updated]
        
        if not jobs_to_update:
            log("info", "No field updates needed.")
            return 0
        
        log("info", f"Total updates to apply: {len(jobs_to_update)}")
        
        if dry_run:
            for result in jobs_to_update:
                for field, (old_val, new_val) in result.fields_updated.items():
                    log(
                        "debug",
                        f"[DRY RUN] Job {result.job_id}-{result.release}: "
                        f"{field} {old_val} → {new_val}"
                    )
            return len(jobs_to_update)
        
        # Apply updates in a transaction
        try:
            with engine.begin() as conn:
                for result in jobs_to_update:
                    try:
                        # Build SET clause from fields_updated
                        set_clauses = []
                        params = {
                            "job": result.job_id,
                            "release": result.release
                        }
                        
                        for field, (old_val, new_val) in result.fields_updated.items():
                            set_clauses.append(f"{field} = :{field}")
                            params[field] = new_val
                        
                        set_str = ", ".join(set_clauses)
                        
                        conn.execute(
                            text(
                                f"UPDATE jobs SET {set_str} "
                                "WHERE job = :job AND release = :release"
                            ),
                            params
                        )
                        updates_count += 1
                        
                        # Log each update
                        for field, (old_val, new_val) in result.fields_updated.items():
                            log(
                                "debug",
                                f"Job {result.job_id}-{result.release}: "
                                f"{field} {old_val} → {new_val}"
                            )
                    except Exception as e:
                        failed_count += 1
                        log(
                            "error",
                            f"Job {result.job_id}-{result.release}: {e}"
                        )
            
            log("info", f"Successfully updated {updates_count} jobs")
            if failed_count > 0:
                log("warning", f"Failed to update {failed_count} jobs")
            
            return updates_count
            
        except Exception as e:
            log("error", f"Error applying updates: {e}")
            return 0
    
    @staticmethod
    def get_job_by_key(
        engine: Engine,
        job_id: int,
        release: str,
        columns: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single job by (job, release) key.
        
        Args:
            engine: SQLAlchemy engine
            job_id: Job number
            release: Release number
            columns: Columns to fetch (defaults to all)
        
        Returns:
            Dictionary with job data, or None if not found
        """
        if columns is None:
            columns = ["*"]
        
        column_str = ", ".join(columns)
        
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT {column_str} FROM jobs "
                    "WHERE job = :job AND release = :release"
                ),
                {"job": job_id, "release": release}
            )
            row = result.first()
            
            if row:
                return dict(row._mapping)
            return None
    
    @staticmethod
    def update_job_fields(
        engine: Engine,
        job_id: int,
        release: str,
        fields: Dict[str, Any],
        dry_run: bool = False
    ) -> bool:
        """
        Update specific fields for a job.
        
        Args:
            engine: SQLAlchemy engine
            job_id: Job number
            release: Release number
            fields: Dictionary of field names to new values
            dry_run: If True, don't make changes
        
        Returns:
            True if successful, False otherwise
        """
        if not fields:
            return True
        
        if dry_run:
            return True
        
        try:
            set_clauses = []
            params = {"job": job_id, "release": release}
            
            for field, value in fields.items():
                set_clauses.append(f"{field} = :{field}")
                params[field] = value
            
            set_str = ", ".join(set_clauses)
            
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"UPDATE jobs SET {set_str} "
                        "WHERE job = :job AND release = :release"
                    ),
                    params
                )
            
            return True
        except Exception as e:
            print(f"Error updating job {job_id}-{release}: {e}")
            return False


# Convenience functions

def map_production_fab_order_to_sandbox(
    production_engine: Engine,
    sandbox_engine: Engine,
    dry_run: bool = False,
    log_callback: Optional[callable] = None
) -> MappingStatistics:
    """
    Map fab_order field from production to sandbox database.
    
    Args:
        production_engine: Production database engine
        sandbox_engine: Sandbox database engine
        dry_run: If True, don't make changes
        log_callback: Optional logging callback
    
    Returns:
        MappingStatistics object
    """
    # Fetch jobs
    production_df = DatabaseMappingService.fetch_jobs(
        production_engine,
        ["job", "release", "fab_order"]
    )
    sandbox_df = DatabaseMappingService.fetch_jobs(
        sandbox_engine,
        ["job", "release", "fab_order"]
    )
    
    # Define field mapping
    field_mappings = [
        FieldMapping(
            source_field="fab_order",
            target_field="fab_order"
        )
    ]
    
    # Map jobs
    results, stats = DatabaseMappingService.map_jobs_by_key(
        production_df,
        sandbox_df,
        field_mappings=field_mappings
    )
    
    # Apply updates
    DatabaseMappingService.apply_field_updates(
        sandbox_engine,
        results,
        dry_run=dry_run,
        log_callback=log_callback
    )
    
    return stats

