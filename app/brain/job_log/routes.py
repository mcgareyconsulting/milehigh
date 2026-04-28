"""
@milehigh-header
schema_version: 1
purpose: Serve all job-log API endpoints (CRUD, stage updates, fab ordering, scheduling, CSV import) under the brain blueprint.
exports:
  get_list_id_by_stage: Resolve a DB stage to a Trello list ID via TrelloListMapper
  update_job_stage_fields: Apply stage and stage_group to a job record
  create_trello_card_for_job: Create a Trello card for a job from Excel data
imports_from: [app.brain, app.models, app.trello.api, app.services.outbox_service, app.auth.utils, app.api.helpers, app.brain.job_log.utils, app.brain.job_log.scheduling]
imported_by: [app/brain/__init__.py, app/services/outbox_service.py]
invariants:
  - All mutating routes require @login_required; admin routes require @admin_required
  - get_list_id_by_stage returns None (not an error) for unmapped stages
  - CSV import validates expected columns before processing rows
  - fab_order updates trigger scheduling recalculation for FABRICATION stage group
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Job Log route handlers for the brain Blueprint.

Provides API endpoints for job data queries and CSV release data handling.
"""
from app.brain import brain_bp
from flask import jsonify, request, g
from app.brain.job_log.utils import serialize_value
from app.trello.api import get_list_by_name, update_trello_card
from app.services.outbox_service import OutboxService
from app.logging_config import get_logger
from app.models import Releases, db, ReleaseEvents, Submittals, User
from app.auth.utils import login_required, get_current_user, admin_required
from app.route_utils import handle_errors, require_json, get_or_404
from app.api.helpers import DEFAULT_FAB_ORDER
from datetime import datetime
import json
import hashlib
import csv
import io
import string
import pandas as pd
import math

logger = get_logger(__name__)

# ==============================================================================
# Helper Functions
# ==============================================================================

def get_list_id_by_stage(stage):
    """
    Get Trello list ID for a database stage.

    Uses TrelloListMapper.DB_STAGE_TO_TRELLO_LIST to resolve many-to-one
    mappings (e.g. 'Welded QC' → 'Fit Up Complete.' list).

    Args:
        stage: Database stage name

    Returns:
        str: Trello list ID, or None if the stage has no mapping or the API call fails
    """
    from app.trello.list_mapper import TrelloListMapper

    trello_list_name = TrelloListMapper.get_trello_list_for_stage(stage)
    if trello_list_name is None:
        logger.info(f"Stage '{stage}' has no Trello list mapping, skipping outbox creation")
        return None

    try:
        list_info = get_list_by_name(trello_list_name)
        if list_info and 'id' in list_info:
            return list_info['id']
        else:
            logger.warning(f"Could not get list ID for stage '{stage}' → list '{trello_list_name}' (list_info: {list_info})")
            return None
    except Exception as e:
        logger.error(f"Error getting list ID for stage '{stage}': {e}", exc_info=True)
        return None

def update_job_stage_fields(job_record, stage):
    """Apply stage update to job record - sets the stage field directly and updates stage_group."""
    from app.api.helpers import get_stage_group_from_stage
    
    logger.info(f"Updating job {job_record.job}-{job_record.release} stage to: {stage}")
    job_record.stage = stage
    job_record.stage_group = get_stage_group_from_stage(stage)
    logger.debug(f"Job stage updated to: {stage}, stage_group updated to: {job_record.stage_group}")

def create_trello_card_for_job(job, excel_data_dict):
    """
    Create a Trello card for an existing job.
    
    Args:
        job: Job database object (may be newly created)
        excel_data_dict: Dictionary with job data in Excel format
    
    Returns:
        Dictionary with success status and card info, or None if card already exists
    """
    try:
        # Skip if job already has a Trello card
        if job.trello_card_id:
            logger.info(f"Job {job.job}-{job.release} already has Trello card {job.trello_card_id}, skipping creation")
            return None
        
        # Import Trello functions
        from app.trello.api import get_list_by_name, update_job_record_with_trello_data
        from app.trello.card_creation import (
            build_card_title,
            build_card_description,
            create_trello_card_core,
            apply_card_post_creation_features
        )
        from app.config import Config as cfg
        
        # jl_routes always uses "Released" list
        list_name = "Released"
        target_list = get_list_by_name(list_name)
        if not target_list:
            # Fall back to configured new-card list
            list_id = cfg.NEW_TRELLO_CARD_LIST_ID
            logger.warning(f"List '{list_name}' not found, using default list")
        else:
            list_id = target_list["id"]
        
        # Get values from excel_data_dict with fallback to job
        job_number = excel_data_dict.get('Job #', job.job)
        release_number = excel_data_dict.get('Release #', job.release)
        job_name = excel_data_dict.get('Job', job.job_name or 'Unknown Job')
        job_description = excel_data_dict.get('Description', job.description or 'Unknown Description')
        
        # Build card title and description using shared functions
        card_title = build_card_title(
            job_number,
            release_number,
            job_name,
            job_description
        )
        
        install_hrs = excel_data_dict.get('Install HRS') or job.install_hrs
        paint_color = excel_data_dict.get('Paint color') or job.paint_color
        pm = excel_data_dict.get('PM') or job.pm
        by = excel_data_dict.get('BY') or job.by
        released = excel_data_dict.get('Released') or job.released
        
        # Handle released date conversion
        if released and isinstance(released, str):
            released_date = to_date(released)
        else:
            released_date = released
        
        card_description = build_card_description(
            description=job_description,
            install_hrs=install_hrs,
            paint_color=paint_color,
            pm=pm,
            by=by,
            released=released_date
        )
        
        # Create the card using shared core function
        create_result = create_trello_card_core(
            card_title=card_title,
            card_description=card_description,
            list_id=list_id,
            position="top"
        )
        
        if not create_result["success"]:
            return {
                "success": False,
                "error": create_result.get("error", "Failed to create card")
            }
        
        card_data = create_result["card_data"]
        card_id = create_result["card_id"]
        
        # Update the job record with Trello card data
        success = update_job_record_with_trello_data(job, card_data)
        
        if success:
            logger.info(f"Successfully updated database record with Trello data")
        else:
            logger.error(f"Failed to update database record with Trello data")
        
        # Get values for post-creation features
        fab_order_value = excel_data_dict.get('Fab Order') or job.fab_order
        notes_value = excel_data_dict.get('Notes') or job.notes
        
        # Apply post-creation features (Fab Order, FC Drawing, notes, mirror card)
        # jl_routes now works identically to scanner - creates mirror cards
        post_creation_results = apply_card_post_creation_features(
            card_id=card_id,
            list_id=list_id,
            job_record=job,
            fab_order=fab_order_value if fab_order_value is not None and not pd.isna(fab_order_value) else None,
            notes=notes_value,
            create_mirror=True,  # jl_routes now creates mirror cards like scanner
            operation_id=None
        )
        
        return {
            "success": True,
            "card_id": card_data["id"],
            "card_name": card_data["name"],
            "card_url": card_data["url"],
            "list_name": list_name,
            "mirror_card_id": post_creation_results.get("mirror_card_id")
        }
        
    except Exception as e:
        logger.error(f"Error creating Trello card for job {job.job}-{job.release}: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }

def to_date(val):
    """Convert a value to a date, returning None if conversion fails or value is null."""
    if pd.isnull(val) or val is None or str(val).strip() == '':
        return None
    try:
        dt = pd.to_datetime(val)
        return dt.date() if not pd.isnull(dt) else None
    except:
        return None

def safe_float(val):
    """Safely convert a value to float, returning None if conversion fails."""
    try:
        return float(val) if val is not None and str(val).strip() != '' else None
    except (TypeError, ValueError):
        return None

def safe_string(val, max_length=None):
    """Safely convert a value to string, optionally truncating."""
    if val is None or pd.isna(val):
        return None
    string_val = str(val)
    if max_length and len(string_val) > max_length:
        return string_val[:max_length-3] + "..."
    return string_val

def _detect_delimiter(csv_data):
    """Detect delimiter (tab vs comma) from CSV data."""
    first_line = csv_data.split('\n')[0] if '\n' in csv_data else csv_data
    return '\t' if '\t' in first_line else ','

def _is_header_row(row, expected_columns):
    """Check if a row looks like a header row."""
    if len(row) != len(expected_columns):
        return False
    return any(col.lower() in str(row[i]).lower() for i, col in enumerate(expected_columns))

def _extract_row_values(row, expected_columns):
    """Extract values from a row, padding with empty strings if needed."""
    # Pad row to expected length
    padded_row = row + [''] * (len(expected_columns) - len(row))
    return {
        'job': padded_row[0] if len(padded_row) > 0 else '',
        'release': padded_row[1] if len(padded_row) > 1 else '',
        'job_name': padded_row[2] if len(padded_row) > 2 else '',
        'description': padded_row[3] if len(padded_row) > 3 else '',
        'fab_hrs': padded_row[4] if len(padded_row) > 4 else '',
        'install_hrs': padded_row[5] if len(padded_row) > 5 else '',
        'paint_color': padded_row[6] if len(padded_row) > 6 else '',
        'pm': padded_row[7] if len(padded_row) > 7 else '',
        'by': padded_row[8] if len(padded_row) > 8 else '',
        'released': padded_row[9] if len(padded_row) > 9 else '',
        'fab_order': padded_row[10] if len(padded_row) > 10 else ''
    }

def _validate_row(row_values, row_idx, row):
    """Validate row values and return (is_valid, error_dict)."""
    if not row_values['job'] or str(row_values['job']).strip() == '':
        return False, {'row': row_idx, 'error': 'Job # is required', 'data': row}
    
    if not row_values['release'] or str(row_values['release']).strip() == '':
        return False, {'row': row_idx, 'error': 'Release # is required', 'data': row}
    
    try:
        int(row_values['job'])
    except (ValueError, TypeError):
        return False, {'row': row_idx, 'error': f'Invalid Job # value: {row_values["job"]}', 'data': row}
    
    return True, None

def _create_payload_hash(action, job_number, release_number, excel_data_dict):
    """Create a hash for the payload."""
    payload = {"data": excel_data_dict}
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    hash_string = f"{action}:{job_number}:{release_number}:{payload_json}"
    return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()

# ==============================================================================
# Job Data Routes
# ==============================================================================

@brain_bp.route("/jobs")
@login_required
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
    from app.models import Releases
    from datetime import datetime
    
    try:
        # Set limit
        limit = 1000  # Higher limit since we're filtering by timestamp

        # Get since parameter from query string
        since_param = request.args.get('since')

        # Get archived parameter from query string
        archived = request.args.get('archived', 'false').lower() == 'true'

        # Base query
        query = Releases.query

        # Apply timestamp filter if provided
        if since_param:
            try:
                since_timestamp = datetime.fromisoformat(since_param.replace('Z', '+00:00'))
                query = query.filter(Releases.last_updated_at > since_timestamp)
                logger.info(f"[CURSOR] Filtering jobs updated after: {since_timestamp}")
                # Cursor polls skip the archive filter so soft-deleted rows always propagate
            except (ValueError, TypeError) as e:
                logger.warning(f"[CURSOR] Invalid since parameter: {since_param}, error: {e}. Fetching all jobs.")
                since_param = None  # fall through to full-load path

        if not since_param:
            logger.info(f"[CURSOR] No since parameter provided - fetching all jobs (initial load)")
            # Apply archive filter only on full loads
            if archived:
                query = query.filter(Releases.is_archived == True)
                logger.info("[ARCHIVE] Filtering to archived jobs (is_archived=True)")
            else:
                query = query.filter(db.or_(Releases.is_archived == False, Releases.is_archived == None))
                logger.info("[ARCHIVE] Excluding archived jobs")
            # Exclude soft-deleted rows on full loads
            query = query.filter(db.or_(Releases.is_active == True, Releases.is_active == None))

        # Order by last_updated_at, id for deterministic results
        query = query.order_by(Releases.last_updated_at.asc(), Releases.id.asc())
        jobs = query.limit(limit).all()
        logger.info(f"[CURSOR] Query returned {len(jobs)} jobs (limit={limit})")

        job_list = []
        warnings = []

        for idx, job in enumerate(jobs):
            try:
                # Get stage from database field (default to 'Released' if None)
                stage = job.stage if job.stage else 'Released'
                
                # Recalculate stage_group from current stage to ensure it's always correct
                # This ensures consistency even if database has stale values
                from app.api.helpers import get_stage_group_from_stage
                calculated_stage_group = get_stage_group_from_stage(stage)
                
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
                    'Stage Group': serialize_value(calculated_stage_group),  # Recalculated from current stage
                    'Banana Color': serialize_value(job.banana_color),  # Urgency indicator: 'red', 'yellow', 'green', or None
                    'Start install': serialize_value(job.start_install),
                    'start_install_formula': serialize_value(job.start_install_formula),
                    'start_install_formulaTF': serialize_value(job.start_install_formulaTF),
                    'Comp. ETA': serialize_value(job.comp_eta),
                    'Job Comp': serialize_value(job.job_comp),
                    'Invoiced': serialize_value(job.invoiced),
                    'Notes': serialize_value(job.notes),
                    'last_updated_at': serialize_value(job.last_updated_at),
                    'source_of_update': serialize_value(job.source_of_update),
                    'viewer_url': serialize_value(job.viewer_url),
                    'trello_card_id': serialize_value(job.trello_card_id),
                    'is_active': serialize_value(job.is_active),
                    'is_archived': serialize_value(job.is_archived),
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

        # Add scheduling fields to all jobs
        # Note: hours_in_front requires ALL jobs in database for accurate queue calculation
        from app.api.helpers import add_scheduling_fields_to_jobs
        try:
            # Fetch all jobs for queue calculation (regardless of filter/pagination)
            all_jobs_for_queue = Releases.query.all()
            all_jobs_dicts = []
            for j in all_jobs_for_queue:
                all_jobs_dicts.append({
                    'Fab Hrs': serialize_value(j.fab_hrs),
                    'Install HRS': serialize_value(j.install_hrs),
                    'Fab Order': serialize_value(j.fab_order),
                    'Stage': j.stage if j.stage else 'Released',
                    'is_hard_date': j.start_install_formulaTF is False,
                })
            job_list = add_scheduling_fields_to_jobs(job_list, all_jobs_dicts)
            # Override displayed Start install with calculated value for jobs still
            # in FABRICATION that don't have a hard (red) date. Once a release
            # leaves fabrication, its start_install freezes at the DB-stored value.
            for job in job_list:
                if (job.get('Banana Color') != 'red'
                        and job.get('install_start_date')
                        and job.get('Stage Group') == 'FABRICATION'):
                    job['Start install'] = job['install_start_date']
        except Exception as scheduling_error:
            logger.warning(
                f"Error calculating scheduling fields: {scheduling_error}",
                exc_info=True
            )
            # Continue without scheduling fields if calculation fails

        # Build response with latest timestamp for client to store
        latest_timestamp = None
        if jobs:
            latest_job = jobs[-1]
            latest_timestamp = latest_job.last_updated_at.isoformat() if latest_job.last_updated_at else None
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


def _validate_job_prefix(job_param):
    """Return (job_param or None, error_response). job_param must be 1–3 digits."""
    job_param = (job_param or '').strip().replace(' ', '')
    if not job_param or len(job_param) > 3 or not job_param.isdigit():
        return None, (jsonify({
            'error': 'Enter 1–3 digits (e.g. 4, 40, 400)',
            'releases': [],
            'submittals': []
        }), 400)
    return job_param, None


def _job_prefix_range(job_param):
    """Return (min_job, max_job_exclusive) for prefix search. job_param is 1–3 digits."""
    n = len(job_param)
    base = int(job_param)
    if n == 1:
        return (base * 100, (base + 1) * 100)   # "4" -> 400–499
    if n == 2:
        return (base * 10, base * 10 + 10)      # "40" -> 400–409
    return (base, base + 1)                      # "400" -> exact 400


@brain_bp.route("/job-search")
@login_required
def job_search():
    """
    Search releases and submittals by job number prefix (1–3 digits).
    GET ?job=4 returns jobs 4xx (400–499).
    GET ?job=40 returns jobs 40x (400–409).
    GET ?job=400 returns exact job 400.
    """
    job_param, err_resp = _validate_job_prefix(request.args.get('job', ''))
    if err_resp:
        return err_resp[0], err_resp[1]

    try:
        min_job, max_job = _job_prefix_range(job_param)
        releases = (
            Releases.query
            .filter(Releases.job >= min_job, Releases.job < max_job)
            .order_by(Releases.job, Releases.release)
            .all()
        )
        submittals = Submittals.query.filter(
            Submittals.project_number.like(f"{job_param}%"),
            Submittals.status == 'Open'
        ).all()

        release_list = [
            {
                'job_release': f"{r.job}-{r.release}",
                'job': r.job,
                'release': r.release,
                'job_name': serialize_value(r.job_name),
                'stage': serialize_value(r.stage or 'Released'),
                'start_install': serialize_value(r.start_install),
            }
            for r in releases
        ]

        submittal_list = []
        for s in submittals:
            d = s.to_dict()
            submittal_list.append({
                'submittal_id': d.get('submittal_id'),
                'title': d.get('title'),
                'status': d.get('status'),
                'ball_in_court': d.get('ball_in_court'),
                'submittal_drafting_status': d.get('submittal_drafting_status') or '',
                'due_date': d.get('due_date'),
                'days_since_ball_in_court_update': d.get('days_since_ball_in_court_update'),
            })

        return jsonify({
            'releases': release_list,
            'submittals': submittal_list,
            'job': job_param,
        }), 200

    except Exception as e:
        logger.error("Error in /job-search endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500


@brain_bp.route("/get-all-jobs")
@login_required
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
    from app.models import Releases
    
    try:
        # Get page parameter from request (default to 1)
        page = request.args.get('page', 1, type=int)
        if page < 1:
            page = 1

        # Get archived parameter from query string
        archived = request.args.get('archived', 'false').lower() == 'true'

        # Set limit
        limit = 100

        # Calculate offset
        offset = (page - 1) * limit

        # Base query - order by id for consistent pagination
        query = Releases.query

        # Apply archive filter
        if archived:
            query = query.filter(Releases.is_archived == True)
            logger.info("[ARCHIVE] Filtering to archived jobs (is_archived=True)")
        else:
            query = query.filter(db.or_(Releases.is_archived == False, Releases.is_archived == None))
            logger.info("[ARCHIVE] Excluding archived jobs")

        # Exclude soft-deleted rows
        query = query.filter(db.or_(Releases.is_active == True, Releases.is_active == None))

        query = query.order_by(Releases.id.asc())

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
                
                # Recalculate stage_group from current stage to ensure it's always correct
                # This ensures consistency even if database has stale values
                from app.api.helpers import get_stage_group_from_stage
                calculated_stage_group = get_stage_group_from_stage(stage)
                
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
                    'Stage Group': serialize_value(calculated_stage_group),  # Recalculated from current stage
                    'Banana Color': serialize_value(job.banana_color),  # Urgency indicator: 'red', 'yellow', 'green', or None
                    'Start install': serialize_value(job.start_install),
                    'start_install_formula': serialize_value(job.start_install_formula),
                    'start_install_formulaTF': serialize_value(job.start_install_formulaTF),
                    'Comp. ETA': serialize_value(job.comp_eta),
                    'Job Comp': serialize_value(job.job_comp),
                    'Invoiced': serialize_value(job.invoiced),
                    'Notes': serialize_value(job.notes),
                    'last_updated_at': serialize_value(job.last_updated_at),
                    'source_of_update': serialize_value(job.source_of_update),
                    'viewer_url': serialize_value(job.viewer_url),
                    'trello_card_id': serialize_value(job.trello_card_id),
                    'is_archived': serialize_value(job.is_archived),
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

        # Add scheduling fields to all jobs
        # Note: hours_in_front requires ALL jobs in database for accurate queue calculation
        from app.api.helpers import add_scheduling_fields_to_jobs
        try:
            # Fetch all jobs for queue calculation (regardless of pagination)
            all_jobs_for_queue = Releases.query.all()
            all_jobs_dicts = []
            for j in all_jobs_for_queue:
                all_jobs_dicts.append({
                    'Fab Hrs': serialize_value(j.fab_hrs),
                    'Install HRS': serialize_value(j.install_hrs),
                    'Fab Order': serialize_value(j.fab_order),
                    'Stage': j.stage if j.stage else 'Released',
                    'is_hard_date': j.start_install_formulaTF is False,
                })
            job_list = add_scheduling_fields_to_jobs(job_list, all_jobs_dicts)
            # Override displayed Start install with calculated value for jobs still
            # in FABRICATION that don't have a hard (red) date. Once a release
            # leaves fabrication, its start_install freezes at the DB-stored value.
            for job in job_list:
                if (job.get('Banana Color') != 'red'
                        and job.get('install_start_date')
                        and job.get('Stage Group') == 'FABRICATION'):
                    job['Start install'] = job['install_start_date']
        except Exception as scheduling_error:
            logger.warning(
                f"Error calculating scheduling fields: {scheduling_error}",
                exc_info=True
            )
            # Continue without scheduling fields if calculation fails
        
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

@brain_bp.route("/gantt-data")
@login_required
def get_gantt_data():
    """
    Get Gantt chart data grouped by project (job number).
    
    Returns:
        JSON object with projects array, each containing:
        - project: job number
        - projectName: job name (from first release)
        - startDate: earliest start_install across all releases
        - endDate: latest comp_eta across all releases (or calculated)
        - releases: array of release bars with start/end dates
        - color: assigned color for this project
        
    Status Codes:
        - 200: Success
        - 500: Server error
    """
    from app.models import Releases
    from app.trello.utils import add_business_days
    from datetime import date
    from collections import defaultdict
    
    try:
        # Get all jobs that have start_install dates and are in FABRICATION or READY_TO_SHIP stage_group
        jobs = Releases.query.filter(
            Releases.start_install.isnot(None),
            Releases.stage_group.in_(['FABRICATION', 'READY_TO_SHIP'])
        ).all()
        
        # Group jobs by project (job number)
        projects_dict = defaultdict(lambda: {
            'releases': [],
            'start_dates': [],
            'end_dates': []
        })
        
        for job in jobs:
            project_key = job.job
            start_install = job.start_install
            
            # Calculate comp_eta: use existing if present, otherwise add 2 business days
            if job.comp_eta:
                comp_eta = job.comp_eta
            else:
                comp_eta = add_business_days(start_install, 2)
            
            # Store release data
            release_data = {
                'job': job.job,
                'release': job.release,
                'jobName': job.job_name,
                'description': job.description or '',
                'startDate': start_install.isoformat() if start_install else None,
                'endDate': comp_eta.isoformat() if comp_eta else None,
                'pm': job.pm or '',
                'by': job.by or ''
            }
            
            projects_dict[project_key]['releases'].append(release_data)
            projects_dict[project_key]['start_dates'].append(start_install)
            projects_dict[project_key]['end_dates'].append(comp_eta)
        
        # Convert to list format and calculate project-level dates
        projects = []
        # Color palette for projects (distinct colors)
        colors = [
            '#3B82F6',  # blue
            '#10B981',  # green
            '#F59E0B',  # amber
            '#EF4444',  # red
            '#8B5CF6',  # purple
            '#EC4899',  # pink
            '#06B6D4',  # cyan
            '#F97316',  # orange
            '#84CC16',  # lime
            '#6366F1',  # indigo
            '#14B8A6',  # teal
            '#F43F5E',  # rose
        ]
        
        for idx, (project_key, project_data) in enumerate(sorted(projects_dict.items())):
            # Get project name from first release
            first_release = project_data['releases'][0]
            project_name = first_release['jobName']
            
            # Calculate project-level dates
            project_start = min(project_data['start_dates'])
            project_end = max(project_data['end_dates'])
            
            # Sort releases by start date
            sorted_releases = sorted(project_data['releases'], 
                                   key=lambda r: r['startDate'] or '')
            
            projects.append({
                'project': project_key,
                'projectName': project_name,
                'startDate': project_start.isoformat() if project_start else None,
                'endDate': project_end.isoformat() if project_end else None,
                'releases': sorted_releases,
                'color': colors[idx % len(colors)]  # Cycle through colors
            })
        
        # Sort projects by start date
        projects.sort(key=lambda p: p['startDate'] or '')
        
        return jsonify({
            'projects': projects
        }), 200
        
    except Exception as e:
        logger.error("Error in /gantt-data endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500

@brain_bp.route("/update-stage/<int:job>/<release>", methods=["PATCH"])
@login_required
def update_stage(job, release):
    """
    Update the stage for a specific job-release combination.
    Thin wrapper over UpdateStageCommand — see
    app/brain/job_log/features/stage/command.py for the full workflow.

    Request Body:
        {"stage": "Released" | "Cut start" | "Fit Up Complete." | ...}
    """
    from app.brain.job_log.features.stage.command import UpdateStageCommand

    logger.info("update_stage called", extra={
        'job': job, 'release': release, 'stage': request.json.get('stage'),
    })

    try:
        stage = request.json.get('stage')
        if not stage:
            return jsonify({'error': 'Stage is required'}), 400

        result = UpdateStageCommand(job_id=job, release=release, stage=stage).execute()

        return jsonify({
            'status': 'success',
            'event_id': result.event_id,
            **result.extras,
        }), 200

    except ValueError as e:
        msg = str(e)
        if 'not found' in msg.lower():
            return jsonify({'error': msg}), 404
        if 'already exists' in msg.lower():
            return jsonify({'error': 'Event already exists'}), 400
        return jsonify({'error': msg}), 400

    except Exception as e:
        logger.error("update_stage failed catastrophically", exc_info=True, extra={
            'job': job, 'release': release,
            'error': str(e), 'error_type': type(e).__name__,
        })
        try:
            from app.services.system_log_service import SystemLogService
            SystemLogService.log_error(
                category='operation_failure',
                operation='update_stage',
                error=e,
                context={'job': job, 'release': release, 'stage': request.json.get('stage')},
            )
        except Exception:
            pass
        db.session.rollback()
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500

@brain_bp.route("/update-fab-order/<int:job>/<release>", methods=["PATCH"])
@login_required
def update_fab_order(job, release):
    """
    Update the fab_order for a specific job-release combination.
    Updates the fab_order field in the database and pushes to Trello.

    Parameters:
        job: int
        release: str

    Request Body:
        {
            "fab_order": float or int (optional, can be null to clear)
        }

    Returns:
        JSON object with 'status': 'success' or 'error'
    """
    from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
    from app.services.system_log_service import SystemLogService
    from app.models import db
    
    logger.info(f"update_fab_order called", extra={
        'job': job,
        'release': release,
        'fab_order': request.json.get('fab_order')
    })

    try:
        # Extract and validate fab_order from request
        fab_order = request.json.get('fab_order')
        # Allow None/null to clear the value
        if fab_order is not None:
            try:
                fab_order = float(fab_order)
                if math.isnan(fab_order):
                    fab_order = None  # Treat NaN as clearing the value
            except (ValueError, TypeError):
                return jsonify({'error': 'fab_order must be a number'}), 400

        # Execute command using the feature module
        command = UpdateFabOrderCommand(
            job_id=job,
            release=release,
            fab_order=fab_order
            # source defaults to "user" and source_of_update defaults to "Brain"
        )
        
        result = command.execute()
        
        # Return response in the same format as before
        return jsonify({
            'status': 'success',
            'event_id': result.event_id
        }), 200
        
    except ValueError as e:
        # Handle business logic errors (job not found, event already exists, etc.)
        error_msg = str(e)
        status_code = 404 if 'not found' in error_msg.lower() else 400
        
        logger.warning(f"update_fab_order validation error: {error_msg}", extra={
            'job': job,
            'release': release
        })
        
        return jsonify({
            'error': error_msg,
            'error_type': 'ValueError'
        }), status_code
        
    except Exception as e:
        logger.error(f"update_fab_order failed", exc_info=True, extra={
            'job': job,
            'release': release,
            'error': str(e),
            'error_type': type(e).__name__
        })
        
        try:
            SystemLogService.log_error(
                category='operation_failure',
                operation='update_fab_order',
                error=e,
                context={
                    'job': job,
                    'release': release,
                    'fab_order': request.json.get('fab_order')
                }
            )
        except:
            pass
        
        db.session.rollback()
        return jsonify({
            'error': str(e),
            'error_type': type(e).__name__
        }), 500

@brain_bp.route("/update-notes/<int:job>/<release>", methods=["PATCH"])
@login_required
def update_notes(job, release):
    """
    Update the notes for a specific job-release combination.
    Updates the notes field in the database (overwrites) and pushes to Trello as comment.

    Parameters:
        job: int
        release: str

    Request Body:
        {
            "notes": str (optional, can be empty string to clear)
        }

    Returns:
        JSON object with 'status': 'success' or 'error'
    """
    from app.models import db
    from app.brain.job_log.features.notes.command import UpdateNotesCommand

    logger.info(f"update_notes called", extra={
        'job': job,
        'release': release,
        'has_notes': bool(request.json.get('notes'))
    })

    try:
        notes = request.json.get('notes', '')

        # Pre-flight: 404 vs 400 distinction matches the original route contract.
        from app.models import Releases
        if not Releases.query.filter_by(job=job, release=release).first():
            logger.warning(f"Job not found: {job}-{release}")
            return jsonify({'error': 'Job not found'}), 404

        try:
            result = UpdateNotesCommand(
                job_id=job, release=release, notes=notes,
            ).execute()
        except ValueError as ve:
            if str(ve) == "Event already exists":
                return jsonify({'error': 'Event already exists'}), 400
            raise

        return jsonify({
            'status': 'success',
            'event_id': result.event_id,
        }), 200
    except Exception as e:
        logger.error(f"update_notes failed", exc_info=True, extra={
            'job': job,
            'release': release,
            'error': str(e),
            'error_type': type(e).__name__
        })

        try:
            from app.services.system_log_service import SystemLogService
            SystemLogService.log_error(
                category='operation_failure',
                operation='update_notes',
                error=e,
                context={
                    'job': job,
                    'release': release,
                    'has_notes': bool(request.json.get('notes'))
                }
            )
        except:
            pass

        db.session.rollback()
        return jsonify({
            'error': str(e),
            'error_type': type(e).__name__
        }), 500


def _normalize_short_field(value, max_len=8):
    """Normalize job_comp/invoiced to a string (max 8 chars) or None."""
    if value is None:
        return None
    s = str(value).strip()
    return s[:max_len] if s else None


@brain_bp.route("/update-job-comp/<int:job>/<release>", methods=["PATCH"])
@login_required
@handle_errors("update_job_comp", raw_error=True)
def update_job_comp(job, release):
    """
    Update the job_comp field for a specific job-release.
    Accepts any string (e.g. 'X', 'MFP', '0.9'); stores up to 8 chars.

    Request Body: { "job_comp": str (optional, empty to clear) }
    Returns: JSON with status or error.
    """
    raw = request.json.get("job_comp")
    job_comp_str = _normalize_short_field(raw)
    if job_comp_str and job_comp_str.upper() != 'X':
        try:
            num = float(job_comp_str.rstrip('%'))
            job_comp_str = f"{num:g}%"
        except ValueError:
            pass

    job_record, err = get_or_404(Releases, "Job not found", job=job, release=release)
    if err:
        return err

    old_job_comp = job_record.job_comp
    job_record.job_comp = job_comp_str
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = "Brain"

    from app.services.job_event_service import JobEventService
    JobEventService.create_and_close(
        job=job,
        release=release,
        action='updated',
        source='Brain',
        payload={'field': 'job_comp', 'old_value': old_job_comp, 'new_value': job_comp_str},
    )

    # If job_comp cleared from 'X', revert stage to what it was before Complete
    response_extras = {}
    old_was_x = old_job_comp and old_job_comp.strip().upper() == 'X'
    new_is_x = job_comp_str and job_comp_str.upper() == 'X'
    if old_was_x and not new_is_x:
        current_stage = job_record.stage or 'Released'
        if current_stage == 'Complete':
            from app.models import ReleaseEvents
            recent_stage_events = ReleaseEvents.query.filter_by(
                job=job, release=release, action='update_stage'
            ).order_by(ReleaseEvents.created_at.desc()).limit(20).all()

            revert_stage = 'Released'
            for evt in recent_stage_events:
                if evt.payload.get('to') == 'Complete' and evt.payload.get('from'):
                    revert_stage = evt.payload['from']
                    break

            update_job_stage_fields(job_record, revert_stage)
            JobEventService.create_and_close(
                job=job, release=release,
                action='update_stage', source='Brain',
                payload={'from': 'Complete', 'to': revert_stage, 'reason': 'job_comp_cleared'},
            )
            response_extras['stage'] = revert_stage
            from app.api.helpers import get_stage_group_from_stage
            response_extras['stage_group'] = get_stage_group_from_stage(revert_stage)

    if new_is_x:
        current_stage = job_record.stage or 'Released'
        if current_stage != 'Complete':
            update_job_stage_fields(job_record, 'Complete')
            JobEventService.create_and_close(
                job=job, release=release,
                action='update_stage', source='Brain',
                payload={'from': current_stage, 'to': 'Complete', 'reason': 'job_comp_set_to_x'},
            )
            response_extras['stage'] = 'Complete'
            from app.api.helpers import get_stage_group_from_stage
            response_extras['stage_group'] = get_stage_group_from_stage('Complete')

        if job_record.fab_order is not None:
            old_fab = job_record.fab_order
            job_record.fab_order = None
            fab_event = JobEventService.create(
                job=job, release=release,
                action='update_fab_order', source='Brain',
                payload={'from': old_fab, 'to': None, 'reason': 'job_comp_complete'},
            )
            if fab_event:
                JobEventService.close(fab_event.id)
            response_extras['fab_order'] = None

    db.session.commit()

    return jsonify({"status": "success", **response_extras}), 200


@brain_bp.route("/update-invoiced/<int:job>/<release>", methods=["PATCH"])
@login_required
@handle_errors("update_invoiced", raw_error=True)
def update_invoiced(job, release):
    """
    Update the invoiced field for a specific job-release.
    Accepts any string (e.g. 'X', 'MFP', '0.9'); stores up to 8 chars.

    Request Body: { "invoiced": str (optional, empty to clear) }
    Returns: JSON with status or error.
    """
    raw = request.json.get("invoiced")
    invoiced_str = _normalize_short_field(raw)
    if invoiced_str and invoiced_str.upper() != 'X':
        try:
            num = float(invoiced_str.rstrip('%'))
            invoiced_str = f"{num:g}%"
        except ValueError:
            pass

    job_record, err = get_or_404(Releases, "Job not found", job=job, release=release)
    if err:
        return err

    old_invoiced = job_record.invoiced
    job_record.invoiced = invoiced_str
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = "Brain"

    from app.services.job_event_service import JobEventService
    JobEventService.create_and_close(
        job=job,
        release=release,
        action='updated',
        source='Brain',
        payload={'field': 'invoiced', 'old_value': old_invoiced, 'new_value': invoiced_str},
    )

    db.session.commit()

    return jsonify({"status": "success"}), 200


@brain_bp.route("/update-start-install/<int:job>/<release>", methods=["PATCH"])
@login_required
def update_start_install(job, release):
    """
    Update the start_install for a specific job-release combination.
    Updates the start_install field in the database and updates Trello card due date.

    Parameters:
        job: int
        release: str

    Request Body:
        {
            "start_install": str (optional, YYYY-MM-DD format, can be null to clear),
            "is_hard_date": bool (optional, default True - if True, clears formula fields)
        }

    Returns:
        JSON object with 'status': 'success' or 'error'
    """
    from app.models import Releases, db
    from app.services.job_event_service import JobEventService
    from datetime import datetime, date
    
    logger.info(f"update_start_install called", extra={
        'job': job,
        'release': release,
        'start_install': request.json.get('start_install')
    })

    try:
        start_install_str = request.json.get('start_install')
        is_hard_date = request.json.get('is_hard_date', True)  # Default to True for backward compatibility
        clear_hard_date = request.json.get('clear_hard_date', False)
        start_install_date = None

        # Handle clearing a hard date (revert to formula-driven)
        if clear_hard_date:
            job_record = Releases.query.filter_by(job=job, release=release).first()
            if not job_record:
                return jsonify({'error': 'Job not found'}), 404

            old_start_install = job_record.start_install

            event = JobEventService.create(
                job=job,
                release=release,
                action='clear_hard_date',
                source='Brain',
                payload={
                    'from': old_start_install.isoformat() if old_start_install else None,
                    'to': None,
                    'cleared_hard_date': True
                }
            )

            if event is None:
                # Clearing is idempotent — a duplicate within the 30s dedup window means
                # a prior clear already applied the state change, so report success.
                logger.info(f"Duplicate clear_hard_date for job {job}-{release}; returning success")
                return jsonify({'status': 'success', 'deduplicated': True}), 200

            job_record.start_install_formulaTF = True
            job_record.start_install_formula = None
            job_record.last_updated_at = datetime.utcnow()
            job_record.source_of_update = 'Brain'

            # Clear Trello card due date
            if job_record.trello_card_id:
                try:
                    update_trello_card(
                        card_id=job_record.trello_card_id,
                        new_due_date=None,
                        clear_due_date=True
                    )
                except Exception as trello_error:
                    logger.error(f"Failed to clear Trello due date for job {job}-{release}: {trello_error}", exc_info=True)

            JobEventService.close(event.id)
            db.session.commit()

            # Recalculate so the formula date gets set
            try:
                from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling
                recalculate_all_jobs_scheduling(stage_group='FABRICATION')
            except Exception as cascade_error:
                logger.error(f"Scheduling cascade failed after clear hard date: {cascade_error}", exc_info=True)

            logger.info(f"Cleared hard date for job {job}-{release}", extra={'event_id': event.id})
            return jsonify({'status': 'success', 'event_id': event.id}), 200

        # Parse date string if provided
        if start_install_str and start_install_str.strip():
            try:
                # Parse YYYY-MM-DD format
                start_install_date = datetime.strptime(start_install_str.strip(), '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid date format. Expected YYYY-MM-DD'}), 400

        # Only proceed if it's a hard date
        if not is_hard_date:
            logger.info(f"Skipping update for job {job}-{release} - not a hard date")
            return jsonify({
                'status': 'skipped',
                'message': 'Not a hard date - formula-driven dates are not updated manually'
            }), 200

        # Pre-flight 404 check — preserves the route's original 404 vs 400 distinction
        # before we delegate to the command.
        if not Releases.query.filter_by(job=job, release=release).first():
            logger.warning(f"Job not found: {job}-{release}")
            return jsonify({'error': 'Job not found'}), 404

        from app.brain.job_log.features.start_install.command import UpdateStartInstallCommand
        try:
            result = UpdateStartInstallCommand(
                job_id=job,
                release=release,
                start_install=start_install_date,
                is_hard_date=is_hard_date,
            ).execute()
        except ValueError as ve:
            if str(ve) == "Event already exists":
                return jsonify({'error': 'Event already exists'}), 400
            raise

        return jsonify({
            'status': 'success',
            'event_id': result.event_id,
        }), 200
        
    except Exception as e:
        logger.error(f"update_start_install failed", exc_info=True, extra={
            'job': job,
            'release': release,
            'error': str(e),
            'error_type': type(e).__name__
        })
        
        try:
            from app.services.system_log_service import SystemLogService
            SystemLogService.log_error(
                category='operation_failure',
                operation='update_start_install',
                error=e,
                context={
                    'job': job,
                    'release': release,
                    'start_install': request.json.get('start_install')
                }
            )
        except:
            pass
        
        db.session.rollback()
        return jsonify({
            'error': str(e),
            'error_type': type(e).__name__
        }), 500

# ==============================================================================
# CSV Release Route
# ==============================================================================

@brain_bp.route("/job-log/release", methods=["POST"])
@login_required
def release_job_data():
    """
    Release job data from clipboard data (CSV or tab-separated from Google Sheets).
    
    Expected format (in order):
    1. Job #
    2. Release #
    3. Job
    4. Description
    5. Fab Hrs
    6. Install HRS
    7. Paint color
    8. PM
    9. BY
    10. Released
    11. Fab Order
    
    Supports both comma-separated (CSV) and tab-separated (TSV) formats.
    Automatically detects the delimiter based on the data.
    
    Request Body:
        {
            "csv_data": "Job #,Release #,Job,Description,...\n123,1,Job Name,..."
            or
            "csv_data": "Job #\tRelease #\tJob\tDescription\t...\n123\t1\tJob Name\t..."
        }
    
    Returns:
        JSON object with success status and processed records
    """
    try:
        data = request.json
        if not data or 'csv_data' not in data:
            return jsonify({'error': 'csv_data is required'}), 400
        
        csv_data = data.get('csv_data')
        if not csv_data or not csv_data.strip():
            return jsonify({'error': 'csv_data cannot be empty'}), 400
        
        # Detect delimiter and parse CSV data
        delimiter = _detect_delimiter(csv_data)
        csv_reader = csv.reader(io.StringIO(csv_data), delimiter=delimiter)
        rows = list(csv_reader)
        
        if not rows:
            return jsonify({'error': 'CSV data is empty'}), 400
        
        # Expected column order
        expected_columns = [
            'Job #', 'Release #', 'Job', 'Description', 'Fab Hrs',
            'Install HRS', 'Paint color', 'PM', 'BY', 'Released', 'Fab Order'
        ]
        
        # Check if first row is headers and determine start index
        start_idx = 1 if _is_header_row(rows[0], expected_columns) else 0
        
        processed = []
        errors = []
        collisions = []
        created_count = 0

        
        for row_idx, row in enumerate(rows[start_idx:], start=start_idx + 1):
            try:
                # Skip empty rows
                if not row or all(not cell or str(cell).strip() == '' for cell in row):
                    continue
                
                # Extract and validate row values
                row_values = _extract_row_values(row, expected_columns)
                is_valid, validation_error = _validate_row(row_values, row_idx, row)
                if not is_valid:
                    errors.append(validation_error)
                    continue
                
                # Parse validated values
                job_number = int(row_values['job'])
                release_number = str(row_values['release']).strip()
                
                # Check if job-release already exists
                existing_job = Releases.query.filter_by(job=job_number, release=release_number).first()
                if existing_job:
                    job_name_value = str(row_values['job_name']).strip()

                    # Suggest the next free release for this job, starting from
                    # the colliding number + 1 (matches client's "rolling release" workflow).
                    suggested = None
                    try:
                        attempted_int = int(release_number)
                        # Get all numeric releases for this job to check availability
                        taken = set()
                        for r in Releases.query.filter_by(job=job_number).all():
                            try:
                                taken.add(int(r.release))
                            except (ValueError, TypeError):
                                pass
                        candidate = attempted_int + 1
                        while candidate in taken:
                            candidate += 1
                        suggested = str(candidate)
                    except (ValueError, TypeError):
                        # Non-numeric release identifier; can't auto-increment
                        pass

                    collisions.append({
                        'row': row_idx,
                        'job': job_number,
                        'release': release_number,
                        'job_name': job_name_value,
                        'suggested_next': suggested
                    })
                    continue
                
                # Prepare Excel format dictionary for Trello card creation
                excel_data_dict = {
                    'Job #': job_number,
                    'Release #': release_number,
                    'Job': row_values['job_name'],
                    'Description': row_values['description'],
                    'Fab Hrs': row_values['fab_hrs'],
                    'Install HRS': row_values['install_hrs'],
                    'Paint color': row_values['paint_color'],
                    'PM': row_values['pm'],
                    'BY': row_values['by'],
                    'Released': row_values['released'],
                    'Fab Order': row_values['fab_order']
                }
                
                # Create payload hash
                action = "create"
                payload_hash = _create_payload_hash(action, job_number, release_number, excel_data_dict)
                
                user = get_current_user()
                event = ReleaseEvents(
                    job=job_number,
                    release=release_number,
                    action='created',
                    payload=excel_data_dict,
                    payload_hash=payload_hash,
                    source='Brain',
                    internal_user_id=user.id if user else None
                )
                db.session.add(event)
                
                # Create new job
                new_job = Releases(
                    job=job_number,
                    release=release_number,
                    job_name=safe_string(row_values['job_name'], 128) or '',
                    description=safe_string(row_values['description'], 256),
                    fab_hrs=safe_float(row_values['fab_hrs']),
                    install_hrs=safe_float(row_values['install_hrs']),
                    paint_color=safe_string(row_values['paint_color'], 64),
                    pm=safe_string(row_values['pm'], 16),
                    by=safe_string(row_values['by'], 16),
                    released=to_date(row_values['released']),
                    fab_order=safe_float(row_values['fab_order']) or DEFAULT_FAB_ORDER,
                    stage='Released',
                    stage_group='FABRICATION',
                    last_updated_at=datetime.utcnow(),
                    source_of_update='Brain'
                )
                db.session.add(new_job)
                db.session.commit()

                # Queue Trello card creation via outbox for async processing
                OutboxService.add(
                    destination='trello',
                    action='create_card',
                    event_id=event.id
                )
                db.session.commit()

                processed_record = {
                    'job': job_number,
                    'release': release_number,
                    'action': 'created'
                }
                
                created_count += 1
                processed.append(processed_record)
                
            except Exception as e:
                logger.error(f"Error processing row {row_idx}: {str(e)}", exc_info=True)
                errors.append({
                    'row': row_idx,
                    'error': f'Unexpected error: {str(e)}',
                    'data': row
                })
                db.session.rollback()
        
        return jsonify({
            'success': True,
            'processed_count': len(processed),
            'created_count': created_count,
            'error_count': len(errors),
            'collision_count': len(collisions),
            'processed': processed,
            'errors': errors if errors else None,
            'collisions': collisions if collisions else None
        }), 200
        
    except Exception as e:
        logger.error("Error in /job-log/release endpoint", error=str(e), exc_info=True)
        db.session.rollback()
        return jsonify({
            'error': str(e),
            'error_type': type(e).__name__
        }), 500

# ==============================================================================
# Operation Routes
# ==============================================================================

@brain_bp.route("/operations/filters")
@login_required
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
@login_required
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
@login_required
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
@login_required
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

# ==============================================================================
# Job Events Routes
# ==============================================================================

@brain_bp.route("/events/filters")
@login_required
def get_event_filters():
    """
    Get all distinct event dates and sources from ReleaseEvents and SubmittalEvents.
    Dates are computed in Mountain Time to match the display timezone.
    """
    from app.models import ReleaseEvents, SubmittalEvents, db
    from zoneinfo import ZoneInfo
    MT = ZoneInfo("America/Denver")
    UTC = ZoneInfo("UTC")
    try:
        # Dates from job (release) events — convert to Mountain Time before extracting date
        job_ts_rows = (
            db.session.query(ReleaseEvents.created_at)
            .filter(ReleaseEvents.created_at.isnot(None))
            .all()
        )
        job_dates = {
            r[0].replace(tzinfo=UTC).astimezone(MT).date().isoformat()
            for r in job_ts_rows if r[0] is not None
        }
        # Dates from submittal events — convert to Mountain Time before extracting date
        submittal_ts_rows = (
            db.session.query(SubmittalEvents.created_at)
            .filter(SubmittalEvents.created_at.isnot(None))
            .all()
        )
        submittal_dates = {
            r[0].replace(tzinfo=UTC).astimezone(MT).date().isoformat()
            for r in submittal_ts_rows if r[0] is not None
        }
        dates = sorted(job_dates | submittal_dates, reverse=True)

        # Sources from job events (Trello, Excel, System, etc.)
        job_source_rows = (
            db.session.query(ReleaseEvents.source)
            .distinct()
            .filter(ReleaseEvents.source.isnot(None))
            .all()
        )
        sources_set = {r[0] for r in job_source_rows}
        # Sources from submittal events (Brain, Procore) so Brain-originated DWL updates show in filters
        submittal_source_rows = (
            db.session.query(SubmittalEvents.source)
            .distinct()
            .filter(SubmittalEvents.source.isnot(None))
            .all()
        )
        sources_set.update(r[0] for r in submittal_source_rows)
        sources = sorted(sources_set)

        from app.models import User
        user_id_rows = (
            db.session.query(ReleaseEvents.internal_user_id)
            .distinct()
            .filter(ReleaseEvents.internal_user_id.isnot(None))
            .all()
        )
        user_id_rows += (
            db.session.query(SubmittalEvents.internal_user_id)
            .distinct()
            .filter(SubmittalEvents.internal_user_id.isnot(None))
            .all()
        )
        internal_ids = {r[0] for r in user_id_rows if r[0] is not None}
        users = []
        if internal_ids:
            for u in User.query.filter(User.id.in_(internal_ids)).all():
                full_name = f"{u.first_name or ''} {u.last_name or ''}".strip()
                display = full_name or u.username or f"User {u.id}"
                users.append({'id': u.id, 'name': display})
            users.sort(key=lambda x: x['name'])

        return jsonify({'dates': dates, 'sources': sources, 'users': users, 'total': len(dates)}), 200
    except Exception as e:
        logger.error("Error in /events/filters endpoint", error=str(e), exc_info=True)
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500

def _resolve_event_user_names(all_events):
    """
    Resolve internal_user_id (SubmittalEvents) and user_id (ReleaseEvents) to plaintext names
    via the users table.
    Returns dict: event_key -> user_display (e.g. "John Smith" or None).
    """
    from app.models import User

    # Collect all internal user IDs
    internal_ids = set()
    for event in all_events:
        iid = getattr(event, 'internal_user_id', None) or getattr(event, 'user_id', None)
        if iid is not None:
            internal_ids.add(iid)

    user_by_id = {}
    if internal_ids:
        for u in User.query.filter(User.id.in_(internal_ids)).all():
            full_name = f"{u.first_name or ''} {u.last_name or ''}".strip()
            user_by_id[u.id] = (full_name or u.username or f"User {u.id}").strip()

    result = {}
    for event in all_events:
        key = (event.id, 'job' if hasattr(event, 'job') else 'submittal')
        iid = getattr(event, 'internal_user_id', None) or getattr(event, 'user_id', None)
        result[key] = user_by_id.get(iid) if iid is not None else None
    return result


@brain_bp.route("/events")
@login_required
def get_events():
    """Get events filtered by date range and source."""
    from app.models import ReleaseEvents, SubmittalEvents
    from app.datetime_utils import format_datetime_mountain
    try:
        # Query parameters
        limit = request.args.get('limit', 50, type=int)
        start_date = request.args.get('start')  # YYYY-MM-DD
        end_date = request.args.get('end')      # YYYY-MM-DD
        source = request.args.get('source')      # Filter by source
        submittal_id = request.args.get('submittal_id')  # Filter by submittal_id
        job = request.args.get('job', type=int)  # Filter by job number
        release = request.args.get('release')  # Filter by release
        user_id = request.args.get('user_id', type=int)

        job_query = ReleaseEvents.query
        submittal_query = SubmittalEvents.query

        # Apply date range on created_at (inclusive).
        # Interpret start/end as Mountain Time day boundaries, convert to UTC for DB comparison.
        from zoneinfo import ZoneInfo
        MT = ZoneInfo("America/Denver")
        UTC = ZoneInfo("UTC")
        if start_date:
            start_dt = datetime.fromisoformat(start_date + "T00:00:00").replace(tzinfo=MT).astimezone(UTC).replace(tzinfo=None)
            job_query = job_query.filter(ReleaseEvents.created_at >= start_dt)
            submittal_query = submittal_query.filter(SubmittalEvents.created_at >= start_dt)
        if end_date:
            end_dt = datetime.fromisoformat(end_date + "T23:59:59.999999").replace(tzinfo=MT).astimezone(UTC).replace(tzinfo=None)
            job_query = job_query.filter(ReleaseEvents.created_at <= end_dt)
            submittal_query = submittal_query.filter(SubmittalEvents.created_at <= end_dt)
        
        # Apply source filter
        if source:
            job_query = job_query.filter(ReleaseEvents.source == source)
            submittal_query = submittal_query.filter(SubmittalEvents.source == source)

        # Apply user filter
        if user_id is not None:
            job_query = job_query.filter(ReleaseEvents.internal_user_id == user_id)
            submittal_query = submittal_query.filter(SubmittalEvents.internal_user_id == user_id)
        
        # Apply submittal_id filter (only applies to submittal events)
        # When filtering by submittal_id, exclude job events entirely
        if submittal_id:
            # Normalize submittal_id to string and strip whitespace
            submittal_id_normalized = str(submittal_id).strip()
            submittal_query = submittal_query.filter(SubmittalEvents.submittal_id == submittal_id_normalized)
            # Don't include job events when filtering by submittal_id
            job_events = []
            submittal_events = submittal_query.order_by(SubmittalEvents.created_at.desc()).limit(limit).all()
        # Apply job and release filters (only applies to job events)
        # When filtering by job/release, exclude submittal events entirely
        elif job is not None or release:
            if job is not None:
                job_query = job_query.filter(ReleaseEvents.job == job)
            if release:
                job_query = job_query.filter(ReleaseEvents.release == str(release).strip())
            # Don't include submittal events when filtering by job/release
            job_events = job_query.order_by(ReleaseEvents.created_at.desc()).limit(limit).all()
            submittal_events = []
        else:
            job_events = job_query.order_by(ReleaseEvents.created_at.desc()).limit(limit).all()
            submittal_events = submittal_query.order_by(SubmittalEvents.created_at.desc()).limit(limit).all()
        
        # Combine and sort events
        all_events = list(job_events) + list(submittal_events)
        all_events.sort(key=lambda x: x.created_at, reverse=True)
        all_events = all_events[:limit]

        user_names = _resolve_event_user_names(all_events)

        def event_key(ev):
            return (ev.id, 'job' if hasattr(ev, 'job') else 'submittal')

        # Eligibility precompute: bulk-fetch current values from both
        # Releases (for job events) and Submittals (for DWL events). The
        # frontend uses `current_value` to determine if the Undo button
        # should be enabled — equality with the event's `to`/`new` value
        # means the event hasn't been superseded by a later edit.
        from app.models import Releases
        UNDO_WHITELIST = {
            'update_stage', 'update_notes', 'update_fab_order', 'update_start_install',
        }
        UNDO_FIELD = {
            'update_stage': 'stage',
            'update_notes': 'notes',
            'update_fab_order': 'fab_order',
            'update_start_install': 'start_install',
        }
        # DWL whitelist: submittal events with action='updated' whose payload
        # targets one of these fields. Mirrors _DWL_UNDO_FIELDS in the undo
        # endpoint below; kept as a local dict here to avoid forward-import
        # awkwardness within this same module.
        DWL_PAYLOAD_TO_COLUMN = {
            'order_number': 'order_number',
            'notes': 'notes',
            'submittal_drafting_status': 'submittal_drafting_status',
        }

        release_pairs = {
            (ev.job, ev.release)
            for ev in all_events
            if hasattr(ev, 'job') and ev.action in UNDO_WHITELIST and ev.job is not None and ev.release
        }
        release_lookup = {}
        if release_pairs:
            from sqlalchemy import and_, or_
            # SQLAlchemy `tuple_().in_()` is awkward across dialects; emit an OR of equality pairs.
            conditions = [
                and_(Releases.job == j, Releases.release == r)
                for (j, r) in release_pairs
            ]
            rows = Releases.query.filter(or_(*conditions)).all()
            for row in rows:
                release_lookup[(row.job, row.release)] = row

        # Submittal lookup for DWL events.
        submittal_ids = {
            str(ev.submittal_id)
            for ev in all_events
            if not hasattr(ev, 'job')
            and ev.action == 'updated'
            and isinstance(ev.payload, dict)
            and ev.submittal_id
            and any(k in DWL_PAYLOAD_TO_COLUMN for k in ev.payload)
        }
        submittal_lookup = {}
        if submittal_ids:
            for s in Submittals.query.filter(Submittals.submittal_id.in_(submittal_ids)).all():
                submittal_lookup[str(s.submittal_id)] = s

        def _current_value(ev):
            if hasattr(ev, 'job'):
                if ev.action not in UNDO_WHITELIST:
                    return None
                row = release_lookup.get((ev.job, ev.release))
                if row is None:
                    return None
                field = UNDO_FIELD[ev.action]
                val = getattr(row, field, None)
                # Normalize start_install to ISO string for parity with payload encoding.
                if field == 'start_install' and val is not None:
                    return val.isoformat()
                return val
            # SubmittalEvents — DWL undo eligibility.
            if ev.action != 'updated' or not isinstance(ev.payload, dict):
                return None
            matches = [k for k in ev.payload if k in DWL_PAYLOAD_TO_COLUMN
                       and isinstance(ev.payload[k], dict)
                       and 'old' in ev.payload[k] and 'new' in ev.payload[k]]
            if len(matches) != 1:
                return None
            row = submittal_lookup.get(str(ev.submittal_id))
            if row is None:
                return None
            return getattr(row, DWL_PAYLOAD_TO_COLUMN[matches[0]], None)

        # Build a parent->children index from events in this batch. The undo
        # endpoint bundles children by `payload.parent_event_id`; surfacing
        # them here lets the confirm dialog enumerate "this will also revert
        # X". Children outside the current batch are missed by this view, but
        # the backend bundle still applies them correctly.
        event_by_id = {ev.id: ev for ev in all_events if hasattr(ev, 'job')}
        children_by_parent = {}
        for ev in all_events:
            if not hasattr(ev, 'job'):
                continue
            ev_payload = ev.payload if isinstance(ev.payload, dict) else None
            if ev_payload is None:
                continue
            pid = ev_payload.get('parent_event_id')
            if pid is not None and pid in event_by_id and ev.action in UNDO_WHITELIST:
                children_by_parent.setdefault(pid, []).append(ev)

        def _linked_children(ev):
            if not hasattr(ev, 'job'):
                return []
            return [
                {
                    'id': c.id,
                    'action': c.action,
                    'from': (c.payload or {}).get('from'),
                    'to': (c.payload or {}).get('to'),
                }
                for c in children_by_parent.get(ev.id, [])
            ]

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
                'internal_user_id': getattr(event, 'internal_user_id', None),
                'external_user_id': getattr(event, 'external_user_id', None),
                'user_name': user_names.get(event_key(event)),
                'created_at': format_datetime_mountain(event.created_at),
                'applied_at': format_datetime_mountain(event.applied_at) if event.applied_at else None,
                'current_value': _current_value(event),
                'linked_children': _linked_children(event),
            } for event in all_events],
            'total': len(all_events),
            'filters': {
                'limit': limit,
                'start': start_date,
                'end': end_date,
                'source': source,
                'submittal_id': submittal_id,
                'job': job,
                'release': release,
                'user_id': user_id,
            }
        }), 200
    except Exception as e:
        logger.error("Error getting job events", error=str(e))
        return jsonify({"error": str(e)}), 500


# ==============================================================================
# Undo
# ==============================================================================

# Whitelist of actions that can be undone via the Events tab. Each maps to the
# Releases column whose value is reverted, so the staleness check can compare
# `payload.to` to the live value before applying the undo.
_UNDO_WHITELIST_FIELD = {
    'update_stage': 'stage',
    'update_notes': 'notes',
    'update_fab_order': 'fab_order',
    'update_start_install': 'start_install',
}


def _staleness_check(event, job_record):
    """Return None if the event is still revertible against the current row, or
    a (current, expected) tuple if stale. Only meaningful for whitelist actions."""
    field = _UNDO_WHITELIST_FIELD[event.action]
    current = getattr(job_record, field, None)
    if field == 'start_install' and current is not None:
        current_for_compare = current.isoformat()
    else:
        current_for_compare = current
    expected = (event.payload or {}).get('to')
    if current_for_compare != expected:
        return (current_for_compare, expected)
    return None


def _dispatch_undo(event, *, source, defer_cascade):
    """Run the appropriate update command to revert `event`. Returns the new
    result object (with .event_id). Caller is responsible for the staleness
    check; this function assumes it's already passed."""
    payload = event.payload or {}
    action = event.action
    if action == 'update_stage':
        from app.brain.job_log.features.stage.command import UpdateStageCommand
        return UpdateStageCommand(
            job_id=event.job, release=event.release,
            stage=payload['from'],
            source=source,
            undone_event_id=event.id,
            defer_cascade=defer_cascade,
        ).execute()
    if action == 'update_notes':
        from app.brain.job_log.features.notes.command import UpdateNotesCommand
        return UpdateNotesCommand(
            job_id=event.job, release=event.release,
            notes=payload['from'] or '',
            source=source,
            undone_event_id=event.id,
        ).execute()
    if action == 'update_fab_order':
        from app.brain.job_log.features.fab_order.command import UpdateFabOrderCommand
        return UpdateFabOrderCommand(
            job_id=event.job, release=event.release,
            fab_order=payload['from'],
            source=source,
            undone_event_id=event.id,
            defer_cascade=defer_cascade,
        ).execute()
    if action == 'update_start_install':
        from app.brain.job_log.features.start_install.command import UpdateStartInstallCommand
        from datetime import datetime as _dt
        from_str = payload['from']
        from_date = _dt.strptime(from_str, '%Y-%m-%d').date() if from_str else None
        return UpdateStartInstallCommand(
            job_id=event.job, release=event.release,
            start_install=from_date,
            is_hard_date=payload.get('is_hard_date', True),
            source=source,
            undone_event_id=event.id,
        ).execute()
    raise ValueError(f"Unsupported undo action: {action}")


@brain_bp.route("/events/<int:event_id>/undo", methods=["POST"])
@admin_required
def undo_event(event_id):
    """
    Revert a ReleaseEvents row by re-applying its `payload.from` through the
    standard update pipeline for that action. The new event(s) carry
    `payload.undone_event_id` linking back to the source event(s).

    **Linked-event bundling.** Some commands (notably `UpdateStageCommand`)
    write follow-on `update_fab_order` or `updated`(job_comp) events whose
    payload includes `parent_event_id: <stage_event.id>`. When undoing the
    parent, we revert each whitelist child too — running the children with
    `defer_cascade=True` and the parent last so the scheduling cascade
    fires once at the end.

    Validates parent + all whitelist children:
      - action is in the whitelist
      - payload has both `from` and `to` keys
      - `payload.from != payload.to`
      - current Releases value for the field matches `payload.to` (staleness)

    Returns 409 with a structured body when *anything* in the bundle is stale.
    """
    from app.models import Releases

    event = ReleaseEvents.query.get(event_id)
    if event is None:
        return jsonify({'error': 'Event not found'}), 404

    if event.action not in _UNDO_WHITELIST_FIELD:
        return jsonify({'error': f"Action '{event.action}' is not undoable"}), 400

    payload = event.payload or {}
    if 'from' not in payload or 'to' not in payload:
        return jsonify({'error': "Event payload missing 'from' or 'to'"}), 400
    if payload['from'] == payload['to']:
        return jsonify({'error': 'No-op event (from == to) cannot be undone'}), 400
    # Undo events are not themselves undoable. To reverse one, edit the value
    # directly in the Job Log — undo-the-undo via this endpoint would obscure
    # the audit trail and confuse the bundling logic (a cascade-aware undo of
    # a non-cascade-aware undo).
    if payload.get('undone_event_id') is not None:
        return jsonify({
            'error': "Undo events are not undoable. Edit the value in the Job Log directly."
        }), 400

    job_record = Releases.query.filter_by(job=event.job, release=event.release).first()
    if job_record is None:
        return jsonify({'error': 'Release not found'}), 404

    # Find children (events that were emitted as side-effects of this one).
    # Cross-DB JSON path queries are awkward; the per-(job, release) event
    # volume is small, so just filter in Python.
    siblings = ReleaseEvents.query.filter_by(
        job=event.job, release=event.release
    ).all()
    children = [
        c for c in siblings
        if isinstance(c.payload, dict)
        and c.payload.get('parent_event_id') == event.id
        and c.action in _UNDO_WHITELIST_FIELD
        and c.payload.get('from') != c.payload.get('to')
    ]

    # Staleness check: parent + every whitelist child must still match
    # `payload.to` against the live Releases row. If anything is stale, fail
    # the whole bundle so partial reverts can't corrupt state.
    parent_stale = _staleness_check(event, job_record)
    child_stale = [(c, _staleness_check(c, job_record)) for c in children]
    child_stale = [(c, s) for c, s in child_stale if s is not None]
    if parent_stale or child_stale:
        return jsonify({
            'error': 'stale',
            'current': parent_stale[0] if parent_stale else None,
            'expected': parent_stale[1] if parent_stale else None,
            'stale_children': [
                {'event_id': c.id, 'action': c.action,
                 'current': s[0], 'expected': s[1]}
                for c, s in child_stale
            ],
            'message': (
                "Stale — the release was edited after this event. Undo would "
                "overwrite a later change. Refresh and try again."
            ),
        }), 409

    source = "Brain"

    # Apply parent FIRST so any fixed-tier / state-driven constraints in the
    # children's commands clear before we touch fab_order. Concretely: if the
    # parent is `Welded QC → Shipping planning` with a child fab_order
    # auto-assign to 2, undoing the child first would re-enter
    # UpdateFabOrderCommand while stage is still 'Shipping planning' (fixed
    # tier 2), and the command's own override would force fab_order back to 2
    # — a silent no-op revert.
    #
    # When there are children, defer the cascade across the bundle and run
    # it once at the end. With no children, let the parent's command run its
    # own cascade as it normally would.
    has_children = bool(children)
    linked_event_ids = []
    try:
        result = _dispatch_undo(event, source=source, defer_cascade=has_children)
        for child in children:
            child_result = _dispatch_undo(child, source=source, defer_cascade=True)
            linked_event_ids.append(child_result.event_id)
    except ValueError as ve:
        logger.warning(f"Undo failed for event {event_id}: {ve}")
        return jsonify({'error': str(ve)}), 400

    if has_children:
        try:
            from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling
            recalculate_all_jobs_scheduling(stage_group='FABRICATION')
        except Exception as cascade_err:
            logger.error(
                f"Scheduling cascade failed after bundled undo of event {event_id}: {cascade_err}",
                exc_info=True,
            )

    return jsonify({
        'status': 'success',
        'event_id': result.event_id,
        'linked_event_ids': linked_event_ids,
    }), 200


# ------------------------------------------------------------------------------
# DWL (SubmittalEvents) undo
# ------------------------------------------------------------------------------
#
# Three Submittals fields are undoable on the Events tab. None of them call
# Procore — undo writes the DB column directly and emits a new SubmittalEvents
# row, mirroring the "silent revert" intent. The Procore-bound `status` field
# stays out of the whitelist, so a user clicking Undo on a Procore status
# event will get a 400 (or a disabled button on the frontend).
#
# All three operations come through DWL routes that emit SubmittalEvents with
# `action='updated'` and a payload shaped like `{<field>: {old, new}}`. We key
# eligibility on the payload key, not on a per-field action.
_DWL_UNDO_FIELDS = {
    'order_number': 'order_number',
    'notes': 'notes',
    'submittal_drafting_status': 'submittal_drafting_status',
}


def _dwl_payload_field(payload):
    """Identify which whitelist field this submittal-event payload targets.
    Returns the field name (e.g. 'order_number') or None if the payload
    doesn't match a single in-scope field."""
    if not isinstance(payload, dict):
        return None
    matches = [
        k for k in payload
        if k in _DWL_UNDO_FIELDS and isinstance(payload[k], dict)
        and 'old' in payload[k] and 'new' in payload[k]
    ]
    if len(matches) != 1:
        # 0 → no in-scope field in this payload
        # 2+ → ambiguous; rare in practice, refuse rather than guess
        return None
    return matches[0]


def _validate_swap_partner(payload):
    """If the event's payload encodes a swap partner (from a step operation),
    return (partner_submittal_id, partner_old, partner_new). Otherwise None.

    Step events look like:
      { order_number: {old, new}, order_step: 'up'|'down',
        swapped_with: { submittal_id, order_number: {old, new} } }
    """
    swap = payload.get('swapped_with')
    if not isinstance(swap, dict):
        return None
    sid = swap.get('submittal_id')
    inner = swap.get('order_number')
    if sid is None or not isinstance(inner, dict):
        return None
    if 'old' not in inner or 'new' not in inner:
        return None
    return (str(sid), inner['old'], inner['new'])


@brain_bp.route("/submittal-events/<int:event_id>/undo", methods=["POST"])
@admin_required
def undo_submittal_event(event_id):
    """
    Revert a single SubmittalEvents row by writing the DB column back to
    `payload[field].old` and emitting a new SubmittalEvents row with
    `payload.undone_event_id` linking back. Does NOT call Procore.

    **Step / swap handling.** If the original event came from `step_submittal_order`,
    its payload embeds the neighbor's change in `payload.swapped_with` (the
    DWL step route doesn't emit a separate event for the neighbor). When that
    field is present, undo also reverts the neighbor's order_number and emits
    a second SubmittalEvents row tagged with `parent_event_id` so the audit
    trail shows the linked side-effect.
    """
    from app.models import SubmittalEvents
    from app.procore.helpers import create_submittal_payload_hash
    from sqlalchemy.exc import IntegrityError

    event = SubmittalEvents.query.get(event_id)
    if event is None:
        return jsonify({'error': 'Event not found'}), 404

    if event.action != 'updated':
        return jsonify({'error': f"Action '{event.action}' is not undoable"}), 400

    payload = event.payload or {}
    if payload.get('undone_event_id') is not None:
        return jsonify({
            'error': "Undo events are not undoable. Edit the value in the Drafting Work Load directly."
        }), 400

    field = _dwl_payload_field(payload)
    if field is None:
        return jsonify({
            'error': "Payload does not target an undoable field "
                     "(order_number, notes, submittal_drafting_status)."
        }), 400

    inner = payload[field]
    if inner['old'] == inner['new']:
        return jsonify({'error': 'No-op event (old == new) cannot be undone'}), 400

    submittal = Submittals.query.filter_by(submittal_id=str(event.submittal_id)).first()
    if submittal is None:
        return jsonify({'error': 'Submittal not found'}), 404

    column = _DWL_UNDO_FIELDS[field]
    current = getattr(submittal, column, None)
    if current != inner['new']:
        return jsonify({
            'error': 'stale',
            'current': current,
            'expected': inner['new'],
            'message': (
                f"Stale — current value is {current!r}, expected {inner['new']!r}. "
                "Undo would overwrite a later change."
            ),
        }), 409

    # Detect a swap partner. Only meaningful for order_number reverts.
    partner = _validate_swap_partner(payload) if field == 'order_number' else None
    partner_submittal = None
    if partner is not None:
        partner_sid, partner_old, partner_new = partner
        partner_submittal = Submittals.query.filter_by(submittal_id=partner_sid).first()
        if partner_submittal is None:
            # Loud failure: don't silently lose the linked revert.
            return jsonify({
                'error': f"Swap partner submittal {partner_sid} not found — "
                         "manually fix order in the Drafting Work Load."
            }), 400
        if partner_submittal.order_number != partner_new:
            return jsonify({
                'error': 'stale',
                'current': partner_submittal.order_number,
                'expected': partner_new,
                'partner_submittal_id': partner_sid,
                'message': (
                    f"Stale — swap partner {partner_sid} order is "
                    f"{partner_submittal.order_number!r}, expected {partner_new!r}. "
                    "Undo would overwrite a later change."
                ),
            }), 409

    # Apply primary revert. The DWL routes don't run cascade or outbox logic
    # for these fields, so we mirror that — write the column, bump
    # last_updated, emit a new SubmittalEvents row.
    setattr(submittal, column, inner['old'])
    submittal.last_updated = datetime.utcnow()

    user = get_current_user()
    user_id = user.id if user else None

    new_payload = {
        field: {'old': inner['new'], 'new': inner['old']},
        'undone_event_id': event.id,
    }
    new_hash = create_submittal_payload_hash('updated', str(submittal.submittal_id), new_payload)
    new_event = SubmittalEvents(
        submittal_id=str(submittal.submittal_id),
        action='updated',
        payload=new_payload,
        payload_hash=new_hash,
        source='Brain',
        internal_user_id=user_id,
    )
    db.session.add(new_event)

    linked_event_ids = []
    try:
        # Flush so new_event.id is populated before we link the partner event.
        db.session.flush()

        if partner is not None:
            partner_sid, partner_old, partner_new = partner
            partner_submittal.order_number = partner_old
            partner_submittal.last_updated = datetime.utcnow()
            partner_payload = {
                'order_number': {'old': partner_new, 'new': partner_old},
                'undone_event_id': event.id,
                'parent_event_id': new_event.id,
            }
            partner_hash = create_submittal_payload_hash(
                'updated', str(partner_submittal.submittal_id), partner_payload
            )
            partner_event = SubmittalEvents(
                submittal_id=str(partner_submittal.submittal_id),
                action='updated',
                payload=partner_payload,
                payload_hash=partner_hash,
                source='Brain',
                internal_user_id=user_id,
            )
            db.session.add(partner_event)
            db.session.flush()
            linked_event_ids.append(partner_event.id)

        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Duplicate event — undo already applied?'}), 400

    return jsonify({
        'status': 'success',
        'event_id': new_event.id,
        'linked_event_ids': linked_event_ids,
    }), 200


# ==============================================================================
# Trello Routes
# ==============================================================================

@brain_bp.route("/trello-scanner")
@login_required
def trello_scanner():
    """
    Scan and compare database jobs with Trello cards.
    
    Returns JSON with comparison results:
    - summary: Counts of jobs in both, DB only, Trello only, and list mismatches
    - in_both: Jobs that exist in both DB and Trello
    - db_only: Jobs that exist in DB but not in Trello
    - trello_only: Cards that exist in Trello but not in DB
    - list_mismatches: Jobs where DB stage doesn't match Trello list
    
    This is a preview/scanning endpoint - no database or Trello updates are made.
    
    Returns:
        JSON object with scan results
        
    Status Codes:
        - 200: Success
        - 500: Server error
    """
    try:
        from app.trello.scanner import scan_trello_db_comparison
        
        logger.info("Trello scanner endpoint called")
        results = scan_trello_db_comparison()
        
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error in Trello scanner: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@brain_bp.route("/preview-scheduling", methods=["GET"])
@login_required
def preview_scheduling():
    """
    Preview scheduling changes without updating the database.
    
    This endpoint shows what changes would be made to start_install and comp_eta
    fields if scheduling were recalculated, without actually making any changes.
    
    Query Parameters:
        reference_date (string, optional): ISO date string for reference date (defaults to today)
        show_all (bool, optional): Show all jobs, not just those with changes (default: false)
        
    Returns:
        JSON object with:
        - total_jobs: Total number of jobs
        - jobs_with_changes: Number of jobs that would have changes
        - jobs: List of jobs with current vs computed values
        - summary: Summary statistics
        
    Status Codes:
        - 200: Success
        - 500: Server error
    """
    from datetime import datetime
    from app.brain.job_log.scheduling.preview import preview_scheduling_changes
    
    try:
        # Get optional parameters
        reference_date_str = request.args.get('reference_date')
        show_all = request.args.get('show_all', 'false').lower() == 'true'
        
        reference_date = None
        if reference_date_str:
            try:
                reference_date = datetime.fromisoformat(reference_date_str.replace('Z', '+00:00')).date()
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid reference_date parameter: {reference_date_str}, using today")
        
        logger.info(f"Preview scheduling endpoint called (reference_date={reference_date}, show_all={show_all})")
        
        preview_results = preview_scheduling_changes(
            reference_date=reference_date,
            show_all=show_all,
            show_summary=True
        )
        
        # Format dates for JSON serialization
        for job_data in preview_results.get('jobs', []):
            # Convert date objects to ISO strings
            for key in ['current_start_install', 'computed_start_install', 
                       'current_comp_eta', 'computed_comp_eta', 
                       'projected_fab_complete_date']:
                if job_data.get(key) is not None:
                    job_data[key] = job_data[key].isoformat()
        
        return jsonify(preview_results), 200
        
    except Exception as e:
        logger.error(f"Error in preview scheduling: {e}", exc_info=True)
        return jsonify({"error": str(e), "error_type": type(e).__name__}), 500

@brain_bp.route("/trello-sync", methods=["POST"])
@login_required
def trello_sync():
    """
    Sync Trello board with database:
    1. Delete Trello-only cards
    2. Move cards to correct lists based on DB stage
    3. Create cards for DB-only jobs
    
    Query Parameters:
        dry_run (bool): If true, only report what would be done without making changes (default: false)
    
    Returns:
        JSON object with sync results
        
    Status Codes:
        - 200: Success
        - 500: Server error
    """
    try:
        from app.trello.scanner import sync_trello_with_db
        
        # Check for dry_run parameter
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'
        
        logger.info(f"Trello sync endpoint called (dry_run={dry_run})")
        results = sync_trello_with_db(dry_run=dry_run)
        
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error in Trello sync: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@brain_bp.route("/renumber-fab-orders", methods=["POST"])
@login_required
def renumber_fab_orders_route():
    """
    One-time migration to renumber fab_orders for the unified ordering scheme.

    Query Parameters:
        dry_run (bool): If true, only report what would change (default: false)

    Returns:
        JSON object with migration stats
    """
    try:
        from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders

        dry_run = request.args.get('dry_run', 'false').lower() == 'true'
        logger.info(f"Renumber fab_orders endpoint called (dry_run={dry_run})")

        stats = renumber_fab_orders(dry_run=dry_run)
        return jsonify({"status": "success", "stats": stats, "dry_run": dry_run}), 200
    except Exception as e:
        logger.error(f"Error in renumber fab_orders: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@brain_bp.route("/trello-scan-create", methods=["POST"])
@login_required
def trello_scan_create():
    """
    Scan all jobs in the database and create Trello cards for jobs that don't have them.
    
    This endpoint:
    - Queries all jobs from the database
    - Filters out jobs that already have trello_card_id (duplicates)
    - Determines the appropriate list for each job based on stage
    - Creates cards with all standard features (notes, fab order, FC drawing, num guys, etc.)
    - Works across all tracked lists (Released, Fit Up Complete., Paint complete, etc.)
    
    Query Parameters:
        dry_run (bool): If true, only report what would be created without making changes (default: false)
        limit (int): Maximum number of jobs to process (optional, processes all if not provided)
    
    Returns:
        JSON object with scan and creation results
        
    Status Codes:
        - 200: Success
        - 500: Server error
    """
    try:
        from app.trello.scanner import scan_and_create_cards_for_all_jobs
        
        # Check for dry_run parameter
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'
        
        # Check for limit parameter
        limit = request.args.get('limit', type=int)
        
        logger.info(f"Trello scan and create endpoint called (dry_run={dry_run}, limit={limit})")
        results = scan_and_create_cards_for_all_jobs(dry_run=dry_run, limit=limit)
        
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error in Trello scan and create: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ==============================================================================
# Admin Job Log Editing Endpoints
# ==============================================================================

# Editable field mapping: display name -> (db_field, type_converter)
EDITABLE_FIELDS = {
    "job": ("job", int),
    "release": ("release", str),
    "job_name": ("job_name", str),
    "description": ("description", str),
    "fab_hrs": ("fab_hrs", float),
    "install_hrs": ("install_hrs", float),
    "paint_color": ("paint_color", str),
    "pm": ("pm", str),
    "by": ("by", str),
    "released": ("released", "date"),
}


@brain_bp.route("/jobs/<int:job>/<release>", methods=["DELETE"])
@login_required
@admin_required
@handle_errors("delete job", raw_error=True)
def delete_job(job, release):
    """
    Delete a job record by job number and release.

    Parameters:
        job: int - Job number
        release: str - Release number

    Returns:
        JSON object with success status (200) or error (404)
    """
    job_record, err = get_or_404(Releases, "Job not found", job=job, release=release)
    if err:
        return err

    logger.info(f"Soft-deleting job {job}-{release}")
    job_record.is_active = False
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = 'Admin'

    from app.services.job_event_service import JobEventService
    JobEventService.create_and_close(
        job=job,
        release=release,
        action='deleted',
        source='Brain',
        payload={'job': job, 'release': release},
    )

    db.session.commit()

    return jsonify({"message": "deleted"}), 200


@brain_bp.route("/jobs/<int:job>/<release>", methods=["PATCH"])
@login_required
@admin_required
@handle_errors("update job column", raw_error=True)
@require_json("field")
def update_job_column(job, release):
    """
    Update a specific column for a job record.

    Parameters:
        job: int - Job number
        release: str - Release number

    Request Body:
        {
            "field": "<field_name>",
            "value": "<new_value>"
        }

    Returns:
        JSON object with updated job data (200) or error (400, 404, 500)
    """
    field = g.json_data['field']
    value = g.json_data.get("value")

    if field not in EDITABLE_FIELDS:
        return jsonify({"error": f"field '{field}' is not editable"}), 400

    db_field, type_converter = EDITABLE_FIELDS[field]

    job_record, err = get_or_404(Releases, "Job not found", job=job, release=release)
    if err:
        return err

    # Coerce value to proper type
    try:
        if type_converter == "date":
            if value:
                converted_value = datetime.strptime(value, "%Y-%m-%d").date()
            else:
                converted_value = None
        elif type_converter == int:
            converted_value = int(value) if value is not None else None
        elif type_converter == float:
            converted_value = float(value) if value is not None else None
        else:
            converted_value = str(value) if value is not None else None
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid value for field '{field}': {str(e)}"}), 400

    old_value = serialize_value(getattr(job_record, db_field, None))
    setattr(job_record, db_field, converted_value)
    job_record.last_updated_at = datetime.utcnow()
    job_record.source_of_update = 'Admin'

    from app.services.job_event_service import JobEventService
    JobEventService.create_and_close(
        job=job,
        release=release,
        action='updated',
        source='Brain',
        payload={'field': field, 'old_value': old_value, 'new_value': serialize_value(converted_value)},
    )

    db.session.commit()

    logger.info(f"Updated job {job}-{release} field {field} to {converted_value}")

    job_data = {
        'id': serialize_value(job_record.id),
        'Job #': serialize_value(job_record.job),
        'Release #': serialize_value(job_record.release),
        'Job': serialize_value(job_record.job_name),
        'Description': serialize_value(job_record.description),
        'Fab Hrs': serialize_value(job_record.fab_hrs),
        'Install HRS': serialize_value(job_record.install_hrs),
        'Paint color': serialize_value(job_record.paint_color),
        'PM': serialize_value(job_record.pm),
        'BY': serialize_value(job_record.by),
        'Released': serialize_value(job_record.released),
    }

    return jsonify(job_data), 200


# ==============================================================================
# Archive Management
# ==============================================================================

def _archivable_query():
    """Return query for active, non-archived releases where both job_comp='X' and invoiced='X'."""
    return Releases.query.filter(
        db.func.upper(db.func.trim(db.func.coalesce(Releases.job_comp, ''))) == 'X',
        db.func.upper(db.func.trim(db.func.coalesce(Releases.invoiced, ''))) == 'X',
        db.or_(Releases.is_archived == False, Releases.is_archived == None),
        db.or_(Releases.is_active == True, Releases.is_active == None),
    )


@brain_bp.route("/archive-preview", methods=["GET"])
@admin_required
def archive_preview():
    """Preview releases eligible for archival (both job_comp and invoiced = 'X', not yet archived)."""
    try:
        releases = _archivable_query().order_by(Releases.job, Releases.release).all()
        items = []
        for r in releases:
            items.append({
                'job': r.job,
                'release': r.release,
                'job_name': r.job_name,
                'description': r.description,
                'stage': r.stage or 'Released',
                'job_comp': r.job_comp,
                'invoiced': r.invoiced,
            })
        return jsonify({'count': len(items), 'releases': items}), 200
    except Exception as e:
        logger.error("archive_preview failed", exc_info=True)
        return jsonify({'error': str(e)}), 500


@brain_bp.route("/unarchive/<int:job>/<release>", methods=["POST"])
@admin_required
@handle_errors("unarchive release", raw_error=True)
def unarchive_release(job, release):
    """Unarchive a single release (set is_archived=False)."""
    from app.services.job_event_service import JobEventService

    r, err = get_or_404(Releases, f'Release {job}-{release} not found', job=job, release=str(release))
    if err:
        return err
    if not r.is_archived:
        return jsonify({'error': f'Release {job}-{release} is not archived'}), 400

    r.is_archived = False
    r.last_updated_at = datetime.utcnow()
    r.source_of_update = 'Brain'
    JobEventService.create_and_close(
        job=r.job,
        release=r.release,
        action='unarchived',
        source='Brain',
        payload={'reason': 'admin_unarchive'},
    )
    db.session.commit()
    logger.info(f"Unarchived release {job}-{release} via admin action")
    return jsonify({'status': 'success'}), 200


@brain_bp.route("/archive-confirm", methods=["POST"])
@admin_required
@handle_errors("archive releases", raw_error=True)
def archive_confirm():
    """Archive all eligible releases (both job_comp and invoiced = 'X', not yet archived)."""
    from app.services.job_event_service import JobEventService

    releases = _archivable_query().all()
    count = 0
    now = datetime.utcnow()
    for r in releases:
        r.is_archived = True
        r.fab_order = None
        r.last_updated_at = now
        r.source_of_update = 'Brain'
        JobEventService.create_and_close(
            job=r.job,
            release=r.release,
            action='archived',
            source='Brain',
            payload={'reason': 'admin_send_to_archive'},
        )
        count += 1
    db.session.commit()
    logger.info(f"Archived {count} releases via admin action")
    return jsonify({'status': 'success', 'count': count}), 200


# ==============================================================================
# Sync Health
# ==============================================================================

@brain_bp.route("/sync-health", methods=["GET"])
@login_required
@admin_required
def sync_health():
    """
    Report the health of the Job Log ↔ Trello sync.

    Returns JSON with:
      - mismatches: active records where the expected Trello list
        (derived from DB stage) differs from the stored trello_list_name
      - unclosed_events: events with applied_at IS NULL older than 1 hour
      - outbox: counts of failed / pending / stuck-processing outbox items
    """
    from app.trello.list_mapper import TrelloListMapper
    from app.models import Releases, ReleaseEvents, TrelloOutbox
    from sqlalchemy import func
    from datetime import timedelta

    try:
        now = datetime.utcnow()

        # --- Mismatches ---------------------------------------------------
        active_with_trello = Releases.query.filter(
            Releases.trello_card_id.isnot(None),
            Releases.is_archived != True,  # noqa: E712
            Releases.is_active == True,    # noqa: E712
        ).all()

        mismatch_details = []
        pattern_counts = {}
        for r in active_with_trello:
            expected = TrelloListMapper.get_trello_list_for_stage(r.stage)
            actual = r.trello_list_name
            if expected and actual and expected != actual:
                pattern = f"{actual} (trello) != {r.stage} (db)"
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
                if len(mismatch_details) < 50:
                    mismatch_details.append({
                        'job': r.job,
                        'release': r.release,
                        'db_stage': r.stage,
                        'trello_list': actual,
                        'expected_list': expected,
                    })

        # --- Unclosed events ----------------------------------------------
        stale_cutoff = now - timedelta(hours=1)
        unclosed_total = ReleaseEvents.query.filter(
            ReleaseEvents.applied_at == None  # noqa: E711
        ).count()
        unclosed_stale = ReleaseEvents.query.filter(
            ReleaseEvents.applied_at == None,  # noqa: E711
            ReleaseEvents.created_at < stale_cutoff,
        ).count()

        # --- Outbox -------------------------------------------------------
        outbox_failed = TrelloOutbox.query.filter_by(status='failed').count()
        outbox_pending = TrelloOutbox.query.filter_by(status='pending').count()
        outbox_processing = TrelloOutbox.query.filter_by(status='processing').count()

        return jsonify({
            'mismatches': {
                'total': sum(pattern_counts.values()),
                'by_pattern': dict(sorted(pattern_counts.items(), key=lambda x: -x[1])),
                'sample': mismatch_details,
            },
            'unclosed_events': {
                'total': unclosed_total,
                'older_than_1h': unclosed_stale,
            },
            'outbox': {
                'failed': outbox_failed,
                'pending': outbox_pending,
                'processing': outbox_processing,
            },
        }), 200
    except Exception as e:
        logger.error("sync_health failed", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# Stash Sessions — Thursday review-meeting "stash" flow
# ==============================================================================

_STASH_ALLOWED_FIELDS = {
    'stage', 'fab_order', 'notes', 'job_comp', 'invoiced', 'start_install',
}


def _format_source(user):
    """Return 'Brain:username' for attribution, falling back to 'Brain'."""
    if user and getattr(user, 'username', None):
        return f"Brain:{user.username}"
    return "Brain"


@brain_bp.route("/stash-sessions/active", methods=["GET"])
@admin_required
def stash_session_active():
    """Return the currently active StashSession (+ its changes) or null."""
    from app.brain.job_log.features.stash.service import StashSessionService

    session = StashSessionService.get_active()
    if session is None:
        return jsonify({'session': None}), 200

    return jsonify({
        'session': session.to_dict(include_changes=True),
    }), 200


@brain_bp.route("/stash-sessions", methods=["POST"])
@admin_required
def stash_session_start():
    """Start a new StashSession. 409 if one is already active."""
    from app.brain.job_log.features.stash.service import (
        StashSessionService, SessionAlreadyActiveError,
    )

    user = get_current_user()
    try:
        session = StashSessionService.start(user)
    except SessionAlreadyActiveError as e:
        return jsonify({'error': str(e)}), 409
    return jsonify({'session': session.to_dict()}), 201


@brain_bp.route("/stash-sessions/<int:session_id>/changes", methods=["POST"])
@admin_required
def stash_session_upsert_change(session_id):
    """Upsert a queued change. Body: {job, release, field, new_value}."""
    from app.brain.job_log.features.stash.service import (
        StashSessionService, SessionNotActiveError, SessionNotFoundError,
    )

    body = request.json or {}
    job = body.get('job')
    release = body.get('release')
    field = body.get('field')
    new_value = body.get('new_value')

    if job is None or release is None or not field:
        return jsonify({'error': 'job, release, and field are required'}), 400
    if field not in _STASH_ALLOWED_FIELDS:
        return jsonify({'error': f'Unsupported field: {field}'}), 400
    try:
        job = int(job)
    except (TypeError, ValueError):
        return jsonify({'error': 'job must be an integer'}), 400

    try:
        change = StashSessionService.stash_change(
            session_id=session_id,
            job=job,
            release=str(release),
            field=field,
            new_value=new_value,
        )
    except SessionNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except SessionNotActiveError as e:
        return jsonify({'error': str(e)}), 409
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({'change': change.to_dict()}), 200


@brain_bp.route(
    "/stash-sessions/<int:session_id>/changes/<int:change_id>",
    methods=["DELETE"],
)
@admin_required
def stash_session_remove_change(session_id, change_id):
    """Remove a single queued change from a session."""
    from app.brain.job_log.features.stash.service import (
        StashSessionService, SessionNotActiveError, SessionNotFoundError,
    )

    try:
        StashSessionService.remove_change(session_id=session_id, change_id=change_id)
    except SessionNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except SessionNotActiveError as e:
        return jsonify({'error': str(e)}), 409
    except ValueError as e:
        return jsonify({'error': str(e)}), 404

    return jsonify({'status': 'success'}), 200


@brain_bp.route("/stash-sessions/<int:session_id>/preview", methods=["GET"])
@admin_required
def stash_session_preview(session_id):
    """Preview the session — each change with baseline, current, new, and conflict flag."""
    from app.brain.job_log.features.stash.service import (
        StashSessionService, SessionNotFoundError,
    )

    try:
        data = StashSessionService.preview(session_id)
    except SessionNotFoundError as e:
        return jsonify({'error': str(e)}), 404

    return jsonify(data), 200


@brain_bp.route("/stash-sessions/<int:session_id>/apply", methods=["POST"])
@admin_required
def stash_session_apply(session_id):
    """Apply all queued changes; runs scheduling cascade once at the end."""
    from app.brain.job_log.features.stash.service import (
        StashSessionService, SessionNotActiveError, SessionNotFoundError,
    )

    user = get_current_user()
    source = _format_source(user)

    try:
        data = StashSessionService.apply(session_id, source=source)
    except SessionNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except SessionNotActiveError as e:
        return jsonify({'error': str(e)}), 409

    return jsonify(data), 200


@brain_bp.route("/stash-sessions/<int:session_id>/discard", methods=["POST"])
@admin_required
def stash_session_discard(session_id):
    """Discard the session — no DB mutations replayed; session marked 'discarded'."""
    from app.brain.job_log.features.stash.service import (
        StashSessionService, SessionNotActiveError, SessionNotFoundError,
    )

    try:
        session = StashSessionService.discard(session_id)
    except SessionNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except SessionNotActiveError as e:
        return jsonify({'error': str(e)}), 409

    return jsonify({'session': session.to_dict()}), 200
