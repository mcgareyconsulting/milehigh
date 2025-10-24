"""
Change tracking utilities for job modifications.

This module provides functions to track and query changes to job records
with detailed timestamps and context information.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
from app.models import db, Job, JobChange, SyncOperation
from app.logging_config import get_logger

logger = get_logger(__name__)


def track_job_change(
    job_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
    source_system: str,
    operation_id: Optional[str] = None,
    change_type: str = "update",
    user_context: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    job: Optional[int] = None,
    release: Optional[str] = None
) -> JobChange:
    """
    Track a change to a job field.
    
    Args:
        job_id: ID of the job being modified
        field_name: Name of the field that changed
        old_value: Previous value of the field
        new_value: New value of the field
        source_system: System that made the change ('trello', 'excel', 'system')
        operation_id: Optional sync operation ID
        change_type: Type of change ('create', 'update', 'delete')
        user_context: Optional user context information
        metadata: Optional additional metadata
    
    Returns:
        JobChange: The created change record
    """
    try:
        # Convert values to strings for storage
        old_str = str(old_value) if old_value is not None else None
        new_str = str(new_value) if new_value is not None else None
        
        # Skip tracking if values are the same
        if old_str == new_str:
            logger.debug("Skipping change tracking - values are identical", 
                        job_id=job_id, field_name=field_name)
            return None
        
        # Get job and release from Job record if not provided
        if job is None or release is None:
            job_record = Job.query.get(job_id)
            if job_record:
                job = job_record.job
                release = job_record.release
            else:
                logger.warning("Could not find job record for job_id", job_id=job_id)
                job = 0
                release = "unknown"
        
        job_release = f"{job}-{release}"
        
        change = JobChange(
            job_id=job_id,
            job=job,
            release=release,
            job_release=job_release,
            operation_id=operation_id,
            field_name=field_name,
            old_value=old_str,
            new_value=new_str,
            changed_at=datetime.utcnow(),
            source_system=source_system,
            change_type=change_type,
            user_context=user_context,
            change_metadata=metadata
        )
        
        db.session.add(change)
        db.session.commit()
        
        logger.info("Job change tracked", 
                   job_id=job_id, 
                   field_name=field_name,
                   change_type=change_type,
                   source_system=source_system)
        
        return change
        
    except Exception as e:
        logger.error("Failed to track job change", 
                    error=str(e),
                    job_id=job_id,
                    field_name=field_name)
        db.session.rollback()
        raise


def track_multiple_changes(
    job_id: int,
    changes: List[Dict[str, Any]],
    source_system: str,
    operation_id: Optional[str] = None,
    user_context: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    job: Optional[int] = None,
    release: Optional[str] = None
) -> List[JobChange]:
    """
    Track multiple changes to a job in a single transaction.
    
    Args:
        job_id: ID of the job being modified
        changes: List of change dictionaries with keys: field_name, old_value, new_value
        source_system: System that made the changes
        operation_id: Optional sync operation ID
        user_context: Optional user context information
        metadata: Optional additional metadata
    
    Returns:
        List[JobChange]: List of created change records
    """
    try:
        change_records = []
        
        # Get job and release from Job record if not provided
        if job is None or release is None:
            job_record = Job.query.get(job_id)
            if job_record:
                job = job_record.job
                release = job_record.release
            else:
                logger.warning("Could not find job record for job_id", job_id=job_id)
                job = 0
                release = "unknown"
        
        job_release = f"{job}-{release}"
        
        for change_data in changes:
            field_name = change_data['field_name']
            old_value = change_data.get('old_value')
            new_value = change_data.get('new_value')
            change_type = change_data.get('change_type', 'update')
            
            # Convert values to strings for storage
            old_str = str(old_value) if old_value is not None else None
            new_str = str(new_value) if new_value is not None else None
            
            # Skip tracking if values are the same
            if old_str == new_str:
                continue
            
            change = JobChange(
                job_id=job_id,
                job=job,
                release=release,
                job_release=job_release,
                operation_id=operation_id,
                field_name=field_name,
                old_value=old_str,
                new_value=new_str,
                changed_at=datetime.utcnow(),
                source_system=source_system,
                change_type=change_type,
                user_context=user_context,
                change_metadata=metadata
            )
            
            db.session.add(change)
            change_records.append(change)
        
        if change_records:
            db.session.commit()
            logger.info("Multiple job changes tracked", 
                       job_id=job_id, 
                       change_count=len(change_records),
                       source_system=source_system)
        
        return change_records
        
    except Exception as e:
        logger.error("Failed to track multiple job changes", 
                    error=str(e),
                    job_id=job_id,
                    change_count=len(changes))
        db.session.rollback()
        raise


def get_job_changes(
    job_id: Optional[int] = None,
    job_release: Optional[str] = None,
    field_name: Optional[str] = None,
    source_system: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0
) -> List[JobChange]:
    """
    Query job changes with various filters.
    
    Args:
        job_id: Filter by specific job ID
        job_release: Filter by job-release identifier (e.g., "170-451")
        field_name: Filter by specific field name
        source_system: Filter by source system
        start_date: Filter changes after this date
        end_date: Filter changes before this date
        limit: Maximum number of results
        offset: Number of results to skip
    
    Returns:
        List[JobChange]: List of matching change records
    """
    try:
        query = JobChange.query
        
        if job_id is not None:
            query = query.filter(JobChange.job_id == job_id)
        
        if job_release is not None:
            query = query.filter(JobChange.job_release == job_release)
        
        if field_name is not None:
            query = query.filter(JobChange.field_name == field_name)
        
        if source_system is not None:
            query = query.filter(JobChange.source_system == source_system)
        
        if start_date is not None:
            query = query.filter(JobChange.changed_at >= start_date)
        
        if end_date is not None:
            query = query.filter(JobChange.changed_at <= end_date)
        
        changes = query.order_by(JobChange.changed_at.desc())\
                      .offset(offset)\
                      .limit(limit)\
                      .all()
        
        return changes
        
    except Exception as e:
        logger.error("Failed to query job changes", error=str(e))
        raise


def get_job_changes_by_release(
    job_release: str,
    field_name: Optional[str] = None,
    source_system: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0
) -> List[JobChange]:
    """
    Query job changes by job-release identifier.
    
    Args:
        job_release: Job-release identifier (e.g., "170-451")
        field_name: Filter by specific field name
        source_system: Filter by source system
        start_date: Filter changes after this date
        end_date: Filter changes before this date
        limit: Maximum number of results
        offset: Number of results to skip
    
    Returns:
        List[JobChange]: List of matching change records
    """
    return get_job_changes(
        job_release=job_release,
        field_name=field_name,
        source_system=source_system,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )


def get_job_change_summary(job_id: int) -> Dict[str, Any]:
    """
    Get a summary of all changes for a specific job.
    
    Args:
        job_id: ID of the job
    
    Returns:
        Dict containing change summary information
    """
    try:
        # Get all changes for the job
        changes = JobChange.query.filter(JobChange.job_id == job_id)\
                                .order_by(JobChange.changed_at.asc())\
                                .all()
        
        if not changes:
            return {
                'job_id': job_id,
                'total_changes': 0,
                'fields_changed': [],
                'first_change': None,
                'last_change': None,
                'changes_by_source': {},
                'changes_by_field': {}
            }
        
        # Analyze changes
        fields_changed = set()
        changes_by_source = {}
        changes_by_field = {}
        
        for change in changes:
            fields_changed.add(change.field_name)
            
            # Count by source system
            source = change.source_system
            changes_by_source[source] = changes_by_source.get(source, 0) + 1
            
            # Count by field
            field = change.field_name
            changes_by_field[field] = changes_by_field.get(field, 0) + 1
        
        return {
            'job_id': job_id,
            'total_changes': len(changes),
            'fields_changed': sorted(list(fields_changed)),
            'first_change': changes[0].changed_at,
            'last_change': changes[-1].changed_at,
            'changes_by_source': changes_by_source,
            'changes_by_field': changes_by_field,
            'recent_changes': [change.to_dict() for change in changes[-10:]]  # Last 10 changes
        }
        
    except Exception as e:
        logger.error("Failed to get job change summary", error=str(e), job_id=job_id)
        raise


def get_job_change_summary_by_release(job_release: str) -> Dict[str, Any]:
    """
    Get a summary of all changes for a specific job-release.
    
    Args:
        job_release: Job-release identifier (e.g., "170-451")
    
    Returns:
        Dict containing change summary information
    """
    try:
        # Get all changes for the job-release
        changes = JobChange.query.filter(JobChange.job_release == job_release)\
                                .order_by(JobChange.changed_at.asc())\
                                .all()
        
        if not changes:
            return {
                'job_release': job_release,
                'total_changes': 0,
                'fields_changed': [],
                'first_change': None,
                'last_change': None,
                'changes_by_source': {},
                'changes_by_field': {}
            }
        
        # Analyze changes
        fields_changed = set()
        changes_by_source = {}
        changes_by_field = {}
        
        for change in changes:
            fields_changed.add(change.field_name)
            
            # Count by source system
            source = change.source_system
            changes_by_source[source] = changes_by_source.get(source, 0) + 1
            
            # Count by field
            field = change.field_name
            changes_by_field[field] = changes_by_field.get(field, 0) + 1
        
        return {
            'job_release': job_release,
            'total_changes': len(changes),
            'fields_changed': sorted(list(fields_changed)),
            'first_change': changes[0].changed_at,
            'last_change': changes[-1].changed_at,
            'changes_by_source': changes_by_source,
            'changes_by_field': changes_by_field,
            'recent_changes': [change.to_dict() for change in changes[-10:]]  # Last 10 changes
        }
        
    except Exception as e:
        logger.error("Failed to get job change summary by release", error=str(e), job_release=job_release)
        raise


def get_field_change_history(
    job_id: int, 
    field_name: str, 
    limit: int = 50
) -> List[JobChange]:
    """
    Get the complete change history for a specific field of a job.
    
    Args:
        job_id: ID of the job
        field_name: Name of the field
        limit: Maximum number of changes to return
    
    Returns:
        List[JobChange]: List of changes for the field
    """
    try:
        changes = JobChange.query.filter(
            JobChange.job_id == job_id,
            JobChange.field_name == field_name
        ).order_by(JobChange.changed_at.desc())\
         .limit(limit)\
         .all()
        
        return changes
        
    except Exception as e:
        logger.error("Failed to get field change history", 
                    error=str(e), 
                    job_id=job_id, 
                    field_name=field_name)
        raise


def get_field_change_history_by_release(
    job_release: str, 
    field_name: str, 
    limit: int = 50
) -> List[JobChange]:
    """
    Get the complete change history for a specific field of a job-release.
    
    Args:
        job_release: Job-release identifier (e.g., "170-451")
        field_name: Name of the field
        limit: Maximum number of changes to return
    
    Returns:
        List[JobChange]: List of changes for the field
    """
    try:
        changes = JobChange.query.filter(
            JobChange.job_release == job_release,
            JobChange.field_name == field_name
        ).order_by(JobChange.changed_at.desc())\
         .limit(limit)\
         .all()
        
        return changes
        
    except Exception as e:
        logger.error("Failed to get field change history by release", 
                    error=str(e), 
                    job_release=job_release, 
                    field_name=field_name)
        raise


def get_recent_changes(
    hours: int = 24,
    limit: int = 100
) -> List[JobChange]:
    """
    Get recent changes across all jobs.
    
    Args:
        hours: Number of hours to look back
        limit: Maximum number of changes to return
    
    Returns:
        List[JobChange]: List of recent changes
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        changes = JobChange.query.filter(JobChange.changed_at >= cutoff_time)\
                                .order_by(JobChange.changed_at.desc())\
                                .limit(limit)\
                                .all()
        
        return changes
        
    except Exception as e:
        logger.error("Failed to get recent changes", error=str(e))
        raise


def cleanup_old_changes(days_to_keep: int = 90) -> int:
    """
    Clean up old change records to prevent database bloat.
    
    Args:
        days_to_keep: Number of days of changes to keep
    
    Returns:
        int: Number of records deleted
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Count records to be deleted
        count_query = JobChange.query.filter(JobChange.changed_at < cutoff_time)
        count = count_query.count()
        
        if count > 0:
            # Delete old records
            count_query.delete()
            db.session.commit()
            
            logger.info("Cleaned up old change records", 
                       deleted_count=count, 
                       cutoff_date=cutoff_time)
        
        return count
        
    except Exception as e:
        logger.error("Failed to cleanup old changes", error=str(e))
        db.session.rollback()
        raise
