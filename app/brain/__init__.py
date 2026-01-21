"""
MHMW Brain Module
Flask Blueprint for all services and routes related to MHMW Operations.

This module provides routes for data collection and display of information related to 
the Job Log, Job History Changelog, as well as other operations related to the
combination and distillation of MHMW Ops data.
"""
from flask import Blueprint
from app.logging_config import get_logger


# Logging
# logger = get_logger()

brain_bp = Blueprint("brain", __name__)

from app.brain.job_log import routes as job_log_routes
from app.brain.drafting_work_load import routes as dwl_routes
