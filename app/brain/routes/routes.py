"""
Route handlers for the brain Blueprint.

Provides API endpoints for job data queries.
"""
from app.brain import brain_bp
from flask import jsonify, request
from app.brain.utils import determine_stage_from_db_fields, serialize_value
from app.logging_config import get_logger
import json
import hashlib
from datetime import datetime
import sys

logger = get_logger(__name__)


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
                # Determine stage from the 5 columns
                stage = determine_stage_from_db_fields(job)
                
                # Return all Excel fields (excluding Trello fields and the 5 stage columns)
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
                    'Stage': stage,  # Single Stage column computed from 5 status columns
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
                # Determine stage from the 5 columns
                stage = determine_stage_from_db_fields(job)
                
                # Return all Excel fields (excluding Trello fields and the 5 stage columns)
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
                    'Stage': stage,  # Single Stage column computed from 5 status columns
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
    Maps the stage name to the appropriate database status fields.

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
    from app.sync.services.trello_list_mapper import TrelloListMapper
    from datetime import datetime
    
    try:
        stage = request.json.get('stage')
        if not stage:
            return jsonify({'error': 'Stage is required'}), 400

        # Create payload for hashing
        action = "update_stage"
        payload = {"to": stage}

        # Normalize the payload by sorting keys and converting to JSON
        # This ensures consistent hashing regardless of key order
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        
        # Create hash string from action + job identifier + payload
        hash_string = f"{action}:{job}:{release}:{payload_json}"

        # Generate SHA-256 hash
        payload_hash = hashlib.sha256(hash_string.encode('utf-8')).hexdigest()

        # Check if event already exists
        event = JobEvents.query.filter_by(payload_hash=payload_hash).first()
        if event:
            return jsonify({'error': 'Event already exists'}), 400

        # Create event
        event = JobEvents(
            job=job,
            release=release,
            action=action,
            payload=payload,
            payload_hash=payload_hash,
            source='Brain',
        )
        db.session.add(event)

        # Update job
        job_record = Job.query.filter_by(job=job, release=release).first()
        if not job_record:
            return jsonify({'error': 'Job not found'}), 404

        logger.info(f"Updating stage for job {job}-{release} to {stage}")

        # Map stage name to database fields using TrelloListMapper
        # Handle "Cut start" separately as it's not in the standard mapper
        if stage == "Cut start":
            # Cut start: set cut_start=X, clear other fields
            job_record.cut_start = "X"
            job_record.fitup_comp = ""
            job_record.welded = ""
            job_record.paint_comp = ""
            job_record.ship = ""
        else:
            # Use TrelloListMapper for other stages
            # This will update fitup_comp, welded, paint_comp, ship appropriately
            TrelloListMapper.apply_trello_list_to_db(job_record, stage, "brain_stage_update")

        # Update job and job_eventsmetadata
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = 'Brain'
        event.applied_at = datetime.utcnow()
        
        db.session.commit()
        
        logger.info(f"Successfully updated stage for job {job}-{release} to {stage}")
        
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error("Error in /update-stage endpoint", error=str(e), exc_info=True)
        db.session.rollback()
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500

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
