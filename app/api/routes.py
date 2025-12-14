"""
API routes for internal database queries.
"""
from flask import jsonify, request
from app.api import api_bp
from app.models import Job, db
from app.api.helpers import transform_job_for_display
from app.logging_config import get_logger

logger = get_logger(__name__)


@api_bp.route("/jobs", methods=["GET"])
def get_jobs():
    """
    Return all jobs from the database.
    Returns raw job data using to_dict() method.
    Use transform_job_for_display() helper if display format is needed.
    """
    try:
        jobs = Job.query.all()

        # transform data for display - convert Job objects to dicts first
        # jobs = [transform_job_for_display(job.to_dict()) for job in jobs]
        jobs = [job.to_dict() for job in jobs]
        return jsonify({
            "jobs": jobs
        }), 200
    except Exception as e:
        logger.error("Error in /api/jobs", error=str(e), exc_info=True)
        return jsonify({'error': str(e)}), 500

