"""
Route handlers for the brain Blueprint.

Provides API endpoints for job data queries.
"""
from app.brain import brain_bp
from flask import jsonify
from app.brain.utils import determine_stage_from_db_fields
from app.logging_config import get_logger

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
    from app.models import Job
    try:
        jobs = Job.query.all()
        job_list = []
        for job in jobs:
            # Determine stage from the 5 columns
            stage = determine_stage_from_db_fields(job)
            
            # Return all Excel fields (excluding Trello fields and the 5 stage columns)
            job_data = {
                'id': job.id,
                'Job #': job.job,
                'Release #': job.release,
                'Job': job.job_name,
                'Description': job.description,
                'Fab Hrs': job.fab_hrs,
                'Install HRS': job.install_hrs,
                'Paint color': job.paint_color,
                'PM': job.pm,
                'BY': job.by,
                'Released': job.released.isoformat() if job.released else None,
                'Fab Order': job.fab_order,
                'Stage': stage,  # Single Stage column computed from 5 status columns
                'Start install': job.start_install.isoformat() if job.start_install else None,
                'Comp. ETA': job.comp_eta.isoformat() if job.comp_eta else None,
                'Job Comp': job.job_comp,
                'Invoiced': job.invoiced,
                'Notes': job.notes,
            }
            job_list.append(job_data)
        
        return jsonify({
            "jobs": job_list
        }), 200
    except Exception as e:
        logger.error("Error in /jobs endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e)}), 500