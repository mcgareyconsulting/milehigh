"""
Route handlers for the brain Blueprint.

Provides API endpoints for job data queries.
"""
from app.brain import brain_bp
from flask import jsonify, request
from app.brain.utils import serialize_value
from app.trello.api import get_list_by_name, update_trello_card
from app.services.outbox_service import OutboxService
from app.logging_config import get_logger
import json
import hashlib
from datetime import datetime
import sys

logger = get_logger(__name__)

def get_list_id_by_stage(stage):
    """
    Get Trello list ID by stage name.
    
    Args:
        stage: Stage name (e.g., 'Released', 'Cut start', 'Fit Up Complete.', etc.)
    
    Returns:
        str: Trello list ID, or None if not found or on error
        Returns None for stages that Trello doesn't track ('Complete' and 'Cut start')
    """
    # Stages that Trello does not track - return None to prevent outbox creation
    stages_not_tracked_by_trello = ['Complete', 'Cut start']
    if stage in stages_not_tracked_by_trello:
        logger.info(f"Stage '{stage}' is not tracked by Trello, skipping outbox creation")
        return None
    
    try:
        list_info = get_list_by_name(stage)
        if list_info and 'id' in list_info:
            return list_info['id']
        else:
            logger.warning(f"Could not get list ID for stage: {stage} (list_info: {list_info})")
            return None
    except Exception as e:
        logger.error(f"Error getting list ID for stage {stage}: {e}", exc_info=True)
        return None

def update_job_stage_fields(job_record, stage):
    """Apply stage update to job record - sets the stage field directly."""
    logger.info(f"Updating job {job_record.job}-{job_record.release} stage to: {stage}")
    job_record.stage = stage
    logger.debug(f"Job stage updated to: {stage}")

@brain_bp.route("/jobs")
def get_jobs():
    """
    List jobs updated since a specific timestamp.
    
    Query Parameters:
        since (string): ISO timestamp - only return jobs updated after this time
        If not provided, returns all jobs (for initial load)
    
    Returns a JSON object with all jobs, including:
    - All Excel fields (Job #, Release #, Description, etc.)
    - A computed 'Stage' field determined from the 5 status columns
    - ISO-formatted date fields
    
    Returns:
        JSON object with 'jobs' array containing job data
        
    Status Codes:
        - 200: Success
        - 500: Server error
    """
    from app.models import Job
    from datetime import datetime
    
    try:        
        # Set limit
        limit = 1000  # Higher limit since we're filtering by timestamp

        # Get since parameter from query string
        since_param = request.args.get('since')
        
        # Base query
        query = Job.query

        # Apply timestamp filter if provided
        if since_param:
            try:
                since_timestamp = datetime.fromisoformat(since_param.replace('Z', '+00:00'))
                query = query.filter(Job.last_updated_at > since_timestamp)
                logger.info(f"[CURSOR] Filtering jobs updated after: {since_timestamp}")
            except (ValueError, TypeError) as e:
                logger.warning(f"[CURSOR] Invalid since parameter: {since_param}, error: {e}. Fetching all jobs.")
        else:
            logger.info(f"[CURSOR] No since parameter provided - fetching all jobs (initial load)")

        # Order by last_updated_at, id for deterministic results
        query = query.order_by(Job.last_updated_at.asc(), Job.id.asc())
        jobs = query.limit(limit).all()
        logger.info(f"[CURSOR] Query returned {len(jobs)} jobs (limit={limit})")

        job_list = []
        warnings = []

        for idx, job in enumerate(jobs):
            try:
                # Get stage from database field (default to 'Released' if None)
                stage = job.stage if job.stage else 'Released'
                
                # Return all Excel fields (excluding Trello fields)
                job_data = {
                    'id': serialize_value(job.id),
                    'Job #': serialize_value(job.job),
                    'Release #': serialize_value(job.release),
                    'Job': serialize_value(job.job_name),
                    'Description': serialize_value(job.description),
                    'Fab Hrs': serialize_value(job.fab_hrs),
                    'Install HRS': serialize_value(job.install_hrs),
                    'Paint color': serialize_value(job.paint_color),
                    'PM': serialize_value(job.pm),
                    'BY': serialize_value(job.by),
                    'Released': serialize_value(job.released),
                    'Fab Order': serialize_value(job.fab_order),
                    'Stage': stage,  # Stage field from database
                    'Start install': serialize_value(job.start_install),
                    'Comp. ETA': serialize_value(job.comp_eta),
                    'Job Comp': serialize_value(job.job_comp),
                    'Invoiced': serialize_value(job.invoiced),
                    'Notes': serialize_value(job.notes),
                }
                # Validate the job data
                json.dumps(job_data)
                job_list.append(job_data)

            except Exception as record_error:
                # Log the problematic record but continue processing
                job_id = f"{job.job}-{job.release}" if hasattr(job, 'job') else f"id:{job.id}"
                error_msg = f"Error serializing record {idx} ({job_id}): {str(record_error)}"
                warnings.append({
                    'record_index': idx,
                    'job_id': job_id,
                    'error': str(record_error),
                    'error_type': type(record_error).__name__
                })
                logger.warning(error_msg, exc_info=True)
                continue

        # Build response with latest timestamp for client to store
        latest_timestamp = None
        if jobs:
            latest_job = jobs[-1]
            latest_timestamp = latest_job.last_updated_at.isoformat()
            logger.info(f"[CURSOR] Latest job timestamp: {latest_timestamp}")

        # Build response
        response_data = {
            "jobs": job_list,
            "returned_count": len(job_list),
            "latest_timestamp": latest_timestamp,  # For client to store in localStorage
        }
        if warnings:
            response_data['warnings'] = warnings

        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error("Error in /jobs endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500

@brain_bp.route("/get-all-jobs")
def get_all_jobs():
    """
    Get all jobs from the database using simple offset-based pagination.
    
    Query Parameters:
        page (int): Page number (defaults to 1). Each page contains up to 100 jobs.
    
    Returns a JSON object with:
    - All Excel fields (Job #, Release #, Description, etc.)
    - A computed 'Stage' field determined from the 5 status columns
    - ISO-formatted date fields
    - Pagination metadata (page, limit, total_count, has_more)
    
    Returns:
        JSON object with 'jobs' array containing job data
        
    Status Codes:
        - 200: Success
        - 500: Server error
    """
    from app.models import Job
    
    try:
        # Get page parameter from request (default to 1)
        page = request.args.get('page', 1, type=int)
        if page < 1:
            page = 1
        
        # Set limit
        limit = 100
        
        # Calculate offset
        offset = (page - 1) * limit
        
        # Base query - order by id for consistent pagination
        query = Job.query.order_by(Job.id.asc())
        
        # Get total count for pagination info
        total_count = query.count()
        
        # Apply pagination
        jobs = query.limit(limit).offset(offset).all()
        
        job_list = []
        warnings = []
        
        for idx, job in enumerate(jobs):
            try:
                # Get stage from database field (default to 'Released' if None)
                stage = job.stage if job.stage else 'Released'
                
                # Return all Excel fields (excluding Trello fields)
                job_data = {
                    'id': serialize_value(job.id),
                    'Job #': serialize_value(job.job),
                    'Release #': serialize_value(job.release),
                    'Job': serialize_value(job.job_name),
                    'Description': serialize_value(job.description),
                    'Fab Hrs': serialize_value(job.fab_hrs),
                    'Install HRS': serialize_value(job.install_hrs),
                    'Paint color': serialize_value(job.paint_color),
                    'PM': serialize_value(job.pm),
                    'BY': serialize_value(job.by),
                    'Released': serialize_value(job.released),
                    'Fab Order': serialize_value(job.fab_order),
                    'Stage': stage,  # Stage field from database
                    'Start install': serialize_value(job.start_install),
                    'Comp. ETA': serialize_value(job.comp_eta),
                    'Job Comp': serialize_value(job.job_comp),
                    'Invoiced': serialize_value(job.invoiced),
                    'Notes': serialize_value(job.notes),
                }
                # Validate the job data
                json.dumps(job_data)
                job_list.append(job_data)
                
            except Exception as record_error:
                # Log the problematic record but continue processing
                job_id = f"{job.job}-{job.release}" if hasattr(job, 'job') else f"id:{job.id}"
                error_msg = f"Error serializing record {idx} ({job_id}): {str(record_error)}"
                warnings.append({
                    'record_index': idx,
                    'job_id': job_id,
                    'error': str(record_error),
                    'error_type': type(record_error).__name__
                })
                logger.warning(error_msg, exc_info=True)
                continue
        
        # Build response
        response_data = {
            "jobs": job_list,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "returned_count": len(job_list),
                "has_more": offset + len(job_list) < total_count
            }
        }
        if warnings:
            response_data['warnings'] = warnings
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error("Error in /get-all-jobs endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500


@brain_bp.route("/update-stage/<int:job>/<release>", methods=["PATCH"])
def update_stage(job, release):
    """
    Update the stage for a specific job-release combination.
    Updates the stage field directly in the database.

    Parameters:
        job: int
        release: str

    Request Body:
        {
            "stage": "Released" | "Cut start" | "Fit Up Complete." | "Paint complete" | etc.
        }

    Returns:
        JSON object with 'status': 'success' or 'error'
    """
    from app.models import Job, db, JobEvents
    from app.services.job_event_service import JobEventService
    from datetime import datetime
    
    # Log operation entry
    logger.info(f"update_stage called", extra={
        'job': job,
        'release': release,
        'stage': request.json.get('stage')
    })

    try:
        stage = request.json.get('stage')
        if not stage:
            return jsonify({'error': 'Stage is required'}), 400

        # Fetch job record
        job_record = Job.query.filter_by(job=job, release=release).first()
        if not job_record:
            logger.warning(f"Job not found: {job}-{release}")
            return jsonify({'error': 'Job not found'}), 404

        # Capture old state for payload
        # Use stage field directly from database (default to 'Released' if None)
        old_stage = job_record.stage if job_record.stage else 'Released'

        # Create event (handles deduplication, logging internally)
        event = JobEventService.create(
            job=job,
            release=release,
            action='update_stage',
            source='user',  # Lowercase for consistency
            payload={
                'from': old_stage,
                'to': stage
            }
        )

        # Check if event was deduplicated
        if event is None:
            logger.info(f"Event already exists for job {job}-{release} to stage {stage}")
            return jsonify({'error': 'Event already exists'}), 400
        
        # Update job fields
        update_job_stage_fields(job_record, stage)

        # Update job metadata
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = 'Brain'

        # Add Trello update to outbox and process immediately (hybrid approach)
        # This provides live updates while still having retry capability if the API call fails
        # The event will be closed when the outbox item is successfully processed
        outbox_item_created = False
        outbox_processed_immediately = False
        new_list_id = get_list_id_by_stage(stage)
        
        if new_list_id and job_record.trello_card_id:
            try:
                # Create outbox item
                outbox_item = OutboxService.add(
                    destination='trello',
                    action='move_card',
                    event_id=event.id
                )
                outbox_item_created = True
                
                # Try to process immediately for live updates
                # If it fails, the retry logic will handle it
                try:
                    if OutboxService.process_item(outbox_item):
                        outbox_processed_immediately = True
                        logger.info(f"Trello update processed immediately for job {job}-{release}")
                except Exception as process_error:
                    # Unexpected error during immediate processing - retry logic will handle it
                    logger.error(f"Error during immediate processing of outbox {outbox_item.id}: {process_error}", exc_info=True)
                    
            except Exception as outbox_error:
                # Failed to create outbox item - log the error but don't fail the whole operation
                logger.error(f"Failed to create outbox for event {event.id}: {outbox_error}", exc_info=True)
        else:
            # Log why outbox item wasn't created
            if not new_list_id:
                logger.warning(
                    f"Could not get list ID for stage '{stage}', skipping Trello update",
                    extra={'job': job, 'release': release, 'stage': stage}
                )
            if not job_record.trello_card_id:
                logger.warning(
                    f"Job {job}-{release} has no trello_card_id, skipping Trello update",
                    extra={'job': job, 'release': release}
                )
        
        # Close event only if no outbox item was created (no external API call needed)
        # If an outbox item exists, it will be closed when processing succeeds (immediate or retry)
        if not outbox_item_created:
            JobEventService.close(event.id)
        
        # Commit all changes (event, job update, outbox item if created)
        db.session.commit()
        
        logger.info(f"update_stage completed successfully", extra={
            'job': job,
            'release': release,
            'event_id': event.id
        })
        
        return jsonify({
            'status': 'success',
            'event_id': event.id
        }), 200
    except Exception as e:
        # Log critical failure
        logger.error(f"update_stage failed catastrophically", exc_info=True, extra={
            'job': job,
            'release': release,
            'error': str(e),
            'error_type': type(e).__name__
        })
        
        # Try to log to system_logs
        try:
            from app.services.system_log_service import SystemLogService
            SystemLogService.log_error(
                category='operation_failure',
                operation='update_stage',
                error=e,
                context={
                    'job': job,
                    'release': release,
                    'stage': request.json.get('stage')
                }
            )
        except:
            pass  # DB might be down, console logs are our fallback
        
        db.session.rollback()
        return jsonify({
            'error': str(e),
            'error_type': type(e).__name__
        }), 500

#######################
## Operation Routes ##
#######################
@brain_bp.route("/operations/filters")
def get_operation_filters():
    """
    Get all distinct operation dates and types from the database.
    """
    from app.models import SyncOperation, db
    from sqlalchemy import func
    try:
        # build dates list
        date_rows = (
            db.session.query(func.date(SyncOperation.started_at))
            .distinct()
            .order_by(func.date(SyncOperation.started_at).desc())
            .all()
        )
        dates = [str(r[0]) for r in date_rows if r[0] is not None]

        # build types list
        type_rows = (
            db.session.query(SyncOperation.operation_type)
            .distinct()
            .filter(SyncOperation.operation_type.isnot(None))
            .order_by(SyncOperation.operation_type)
            .all()
        )
        types = [r[0] for r in type_rows]

        return jsonify({'dates': dates, 'types': types, 'total': len(dates)}), 200
    except Exception as e:
        logger.error("Error in /operations/filters endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500

@brain_bp.route("/operations/types")
def get_operation_types():
    """
    Get all distinct operation types from the database.
    """
    from app.models import SyncOperation, db
    try:
        type_rows = (
            db.session.query(SyncOperation.operation_type)
            .distinct()
            .filter(SyncOperation.operation_type.isnot(None))
            .order_by(SyncOperation.operation_type)
            .all()
        )
        types = [r[0] for r in type_rows]
        
        return jsonify({'types': types, 'total': len(types)}), 200
    except Exception as e:
        logger.error("Error in /operations/types endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500

@brain_bp.route("/operations")
def sync_operations():
        """Get sync operations filtered by date range, operation_type, and source_id."""
        from app.models import SyncOperation
        try:
            # Query parameters
            limit = request.args.get('limit', 50, type=int)
            start_date = request.args.get('start')  # YYYY-MM-DD
            end_date = request.args.get('end')      # YYYY-MM-DD
            operation_type = request.args.get('operation_type')  # Filter by operation type
            source_id = request.args.get('source_id')  # Filter by source_id (e.g., submittal_id)

            query = SyncOperation.query

            # Apply date range on started_at (inclusive)
            if start_date:
                start_dt = datetime.fromisoformat(start_date + "T00:00:00")
                query = query.filter(SyncOperation.started_at >= start_dt)
            if end_date:
                end_dt = datetime.fromisoformat(end_date + "T23:59:59.999999")
                query = query.filter(SyncOperation.started_at <= end_dt)
            
            # Apply operation_type filter
            if operation_type:
                query = query.filter(SyncOperation.operation_type == operation_type)
            
            # Apply source_id filter
            if source_id:
                query = query.filter(SyncOperation.source_id == str(source_id))

            operations = query.order_by(SyncOperation.started_at.desc()).limit(limit).all()

            return jsonify({
                'operations': [op.to_dict() for op in operations],
                'total': len(operations),
                'filters': {
                    'limit': limit,
                    'start': start_date,
                    'end': end_date,
                    'operation_type': operation_type,
                    'source_id': source_id,
                }
            }), 200
        except Exception as e:
            logger.error("Error getting sync operations", error=str(e))
            return jsonify({"error": str(e)}), 500

@brain_bp.route("/operations/<operation_id>/logs")
def sync_operation_logs(operation_id):
        """Get detailed logs for a specific sync operation."""
        from app.models import SyncLog
        from app.datetime_utils import format_datetime_mountain
        try:
            logs = SyncLog.query.filter_by(operation_id=operation_id)\
                              .order_by(SyncLog.timestamp.asc()).all()
            
            return jsonify({
                'operation_id': operation_id,
                'logs': [{
                    'timestamp': format_datetime_mountain(log.timestamp),
                    'level': log.level,
                    'message': log.message,
                    'data': log.data
                } for log in logs]
            }), 200
            
        except Exception as e:
            logger.error("Error getting sync operation logs", operation_id=operation_id, error=str(e))
            return jsonify({"error": str(e)}), 500

#######################
## Job Events Routes ##
#######################
@brain_bp.route("/events/filters")
def get_event_filters():
    """
    Get all distinct event dates and sources from the database.
    """
    from app.models import JobEvents, db
    from sqlalchemy import func
    try:
        # build dates list
        date_rows = (
            db.session.query(func.date(JobEvents.created_at))
            .distinct()
            .order_by(func.date(JobEvents.created_at).desc())
            .all()
        )
        dates = [str(r[0]) for r in date_rows if r[0] is not None]

        # build sources list
        source_rows = (
            db.session.query(JobEvents.source)
            .distinct()
            .filter(JobEvents.source.isnot(None))
            .order_by(JobEvents.source)
            .all()
        )
        sources = [r[0] for r in source_rows]

        return jsonify({'dates': dates, 'sources': sources, 'total': len(dates)}), 200
    except Exception as e:
        logger.error("Error in /events/filters endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500

@brain_bp.route("/events")
def get_events():
    """Get events filtered by date range and source."""
    from app.models import JobEvents, SubmittalEvents
    from app.datetime_utils import format_datetime_mountain
    try:
        # Query parameters
        limit = request.args.get('limit', 50, type=int)
        start_date = request.args.get('start')  # YYYY-MM-DD
        end_date = request.args.get('end')      # YYYY-MM-DD
        source = request.args.get('source')      # Filter by source
        submittal_id = request.args.get('submittal_id')  # Filter by submittal_id

        job_query = JobEvents.query
        submittal_query = SubmittalEvents.query

        # Apply date range on created_at (inclusive)
        if start_date:
            start_dt = datetime.fromisoformat(start_date + "T00:00:00")
            job_query = job_query.filter(JobEvents.created_at >= start_dt)
            submittal_query = submittal_query.filter(SubmittalEvents.created_at >= start_dt)
        if end_date:
            end_dt = datetime.fromisoformat(end_date + "T23:59:59.999999")
            job_query = job_query.filter(JobEvents.created_at <= end_dt)
            submittal_query = submittal_query.filter(SubmittalEvents.created_at <= end_dt)
        
        # Apply source filter
        if source:
            job_query = job_query.filter(JobEvents.source == source)
            submittal_query = submittal_query.filter(SubmittalEvents.source == source)
        
        # Apply submittal_id filter (only applies to submittal events)
        # When filtering by submittal_id, exclude job events entirely
        if submittal_id:
            # Normalize submittal_id to string and strip whitespace
            submittal_id_normalized = str(submittal_id).strip()
            submittal_query = submittal_query.filter(SubmittalEvents.submittal_id == submittal_id_normalized)
            # Don't include job events when filtering by submittal_id
            job_events = []
        else:
            job_events = job_query.order_by(JobEvents.created_at.desc()).limit(limit).all()
        
        submittal_events = submittal_query.order_by(SubmittalEvents.created_at.desc()).limit(limit).all()
        
        # Combine and sort events
        all_events = list(job_events) + list(submittal_events)
        all_events.sort(key=lambda x: x.created_at, reverse=True)
        all_events = all_events[:limit]

        return jsonify({
            'events': [{
                'id': event.id,
                'job': event.job if hasattr(event, 'job') else None,
                'release': event.release if hasattr(event, 'release') else None,
                'submittal_id': event.submittal_id if hasattr(event, 'submittal_id') else None,
                'type': 'job' if hasattr(event, 'job') else 'submittal',
                'action': event.action,
                'payload': event.payload,
                'source': event.source,
                'created_at': format_datetime_mountain(event.created_at),
                'applied_at': format_datetime_mountain(event.applied_at) if event.applied_at else None
            } for event in all_events],
            'total': len(all_events),
            'filters': {
                'limit': limit,
                'start': start_date,
                'end': end_date,
                'source': source,
                'submittal_id': submittal_id,
            }
        }), 200
    except Exception as e:
        logger.error("Error getting job events", error=str(e))
        return jsonify({"error": str(e)}), 500
