"""
Route handlers for the brain Blueprint.

Provides API endpoints for job data queries.
"""
from app.brain import brain_bp
from flask import jsonify, request
from app.brain.utils import determine_stage_from_db_fields, serialize_value
from app.logging_config import get_logger
import json
import sys

logger = get_logger(__name__)


@brain_bp.route("/jobs")
def get_jobs():
    """
    List all jobs from the database as JSON.
    
    Supports optional pagination via query parameters:
    - limit: number of records to return (default: all)
    - offset: number of records to skip (default: 0)
    
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
    
    # Get pagination parameters
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', type=int, default=0)
    
    try:
        # Build query
        query = Job.query
        total_count = query.count()
        
        # Apply pagination if requested
        if limit:
            query = query.limit(limit).offset(offset)
        
        jobs = query.all()
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
        
        response_data = {
            "jobs": job_list,
            "returned_count": len(job_list),
            "total_count": total_count,
        }
        
        if limit or offset:
            response_data['limit'] = limit
            response_data['offset'] = offset
            response_data['has_more'] = (offset + len(job_list)) < total_count
        
        if warnings:
            response_data['warnings'] = warnings
            logger.warning(f"Serialized {len(job_list)} jobs, skipped {len(warnings)} problematic records")
        
        # Log response size for debugging
        json_str = json.dumps(response_data)
        response_size = len(json_str.encode('utf-8'))
        logger.info(f"Jobs endpoint: returning {len(job_list)} jobs, total_count={total_count}, response_size={response_size} bytes")
        
        # If response is very large, log a warning
        if response_size > 1024 * 1024:  # > 1MB
            logger.warning(f"Large response size: {response_size} bytes ({response_size / 1024 / 1024:.2f} MB)")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error("Error in /jobs endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500