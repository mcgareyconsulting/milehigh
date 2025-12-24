"""
Route handlers for the brain Blueprint.

Provides API endpoints for job data queries.
"""
from app.brain import brain_bp
from flask import jsonify, request
from app.brain.utils import determine_stage_from_db_fields, serialize_value
from app.logging_config import get_logger
import json
from datetime import datetime
import sys

logger = get_logger(__name__)


@brain_bp.route("/jobs")
def get_jobs():
    """
    List all jobs from the database as JSON.
    
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
    from app.models import Job, SyncCursor, db
    from sqlalchemy import or_, and_
    
    try:        
        # Set limit
        limit = 100

        # Collect SyncCursor
        cursor = SyncCursor.query.filter_by(name='jobs').first()
        if cursor:
            last_updated_at = cursor.last_updated_at
            last_id = cursor.last_id
        else:
            last_updated_at = None
            last_id = 0  # default to 0 for first load

        # Base query
        query = Job.query

        # Apply cursor filter if cursor exists
        if last_updated_at:
            query = query.filter(
                or_(
                    Job.last_updated_at > last_updated_at,
                    and_(
                        Job.last_updated_at == last_updated_at,
                        Job.id > last_id
                    )
                )
            )

        # Always order by last_updated_at, id for deterministic pagination, set limit
        query = query.order_by(Job.last_updated_at.asc(), Job.id.asc())
        jobs = query.limit(limit).all()

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

        # Update cursor to the last row in this batch
        if jobs:
            last_job = jobs[-1]
            if cursor:
                cursor.last_updated_at = last_job.last_updated_at
                cursor.last_id = last_job.id
            else:
                cursor = SyncCursor(
                    name="jobs",
                    last_updated_at=last_job.last_updated_at,
                    last_id=last_job.id
                )
                db.session.add(cursor)
            db.session.commit()

        # Build response
        response_data = {
            "jobs": job_list,
            "returned_count": len(job_list),
            "batch_limit": limit,
            "has_more": len(jobs) == limit  # if batch is full, assume more rows exist
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


@brain_bp.route("/update-stage/<int:job>/<release>")
def update_stage(job, release):
    """
    Update the stage for a specific job-release combination.

    Parameters:
        job: int
        release: str

    Returns:
        JSON object with 'status': 'success' or 'error'
    """
    from app.models import Job, db
    try:
        job = Job.query.filter_by(job=job, release=release).first()
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        stage = request.json.get('stage')
        if not stage:
            return jsonify({'error': 'Stage is required'}), 400

        job.stage = stage
        # TODO: pass this stage change to Trello
        print(f"Updating stage for job {job.job} {job.release} to {stage}. Need to update Trello card.")
        job.last_updated_at = datetime.now()
        job.source_of_update = 'Brain'
        db.session.commit()
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error("Error in /update-stage endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500