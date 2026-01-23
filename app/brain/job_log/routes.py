"""
Job Log route handlers for the brain Blueprint.

Provides API endpoints for job data queries and CSV release data handling.
"""
from app.brain import brain_bp
from flask import jsonify, request
from app.brain.job_log.utils import serialize_value
from app.trello.api import get_list_by_name, update_trello_card
from app.services.outbox_service import OutboxService
from app.logging_config import get_logger
from app.models import Job, db, JobEvents
from app.auth.utils import login_required, format_source_with_user, get_current_user
from datetime import datetime
import json
import hashlib
import csv
import io
import pandas as pd

logger = get_logger(__name__)

# ==============================================================================
# Helper Functions
# ==============================================================================

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
                    'last_updated_at': serialize_value(job.last_updated_at),
                    'source_of_update': serialize_value(job.source_of_update),
                    'viewer_url': serialize_value(job.viewer_url),
                    'trello_card_id': serialize_value(job.trello_card_id),
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
            all_jobs_for_queue = Job.query.all()
            all_jobs_dicts = []
            for j in all_jobs_for_queue:
                all_jobs_dicts.append({
                    'Fab Hrs': serialize_value(j.fab_hrs),
                    'Install HRS': serialize_value(j.install_hrs),
                    'Fab Order': serialize_value(j.fab_order),
                    'Stage': j.stage if j.stage else 'Released',
                })
            job_list = add_scheduling_fields_to_jobs(job_list, all_jobs_dicts)
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
                    'last_updated_at': serialize_value(job.last_updated_at),
                    'source_of_update': serialize_value(job.source_of_update),
                    'viewer_url': serialize_value(job.viewer_url),
                    'trello_card_id': serialize_value(job.trello_card_id),
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
            all_jobs_for_queue = Job.query.all()
            all_jobs_dicts = []
            for j in all_jobs_for_queue:
                all_jobs_dicts.append({
                    'Fab Hrs': serialize_value(j.fab_hrs),
                    'Install HRS': serialize_value(j.install_hrs),
                    'Fab Order': serialize_value(j.fab_order),
                    'Stage': j.stage if j.stage else 'Released',
                })
            job_list = add_scheduling_fields_to_jobs(job_list, all_jobs_dicts)
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
    from app.models import Job
    from app.trello.utils import add_business_days
    from datetime import date
    from collections import defaultdict
    
    try:
        # Get all jobs that have start_install dates (required for rendering)
        jobs = Job.query.filter(Job.start_install.isnot(None)).all()
        
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
            source='Brain',  # Will be formatted as 'Brain:username' automatically
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
                # Convert to float
                fab_order = float(fab_order)
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
    from app.models import Job, db, JobEvents
    from app.services.job_event_service import JobEventService
    
    logger.info(f"update_notes called", extra={
        'job': job,
        'release': release,
        'has_notes': bool(request.json.get('notes'))
    })

    try:
        notes = request.json.get('notes', '')
        # Convert to string, allow empty string
        if notes is None:
            notes = ''
        else:
            notes = str(notes).strip()

        # Fetch job record
        job_record = Job.query.filter_by(job=job, release=release).first()
        if not job_record:
            logger.warning(f"Job not found: {job}-{release}")
            return jsonify({'error': 'Job not found'}), 404

        # Capture old state for payload
        old_notes = job_record.notes

        # Create event (handles deduplication, logging internally)
        event = JobEventService.create(
            job=job,
            release=release,
            action='update_notes',
            source='Brain',  # Will be formatted as 'Brain:username' automatically
            payload={
                'from': old_notes,
                'to': notes
            }
        )

        # Check if event was deduplicated
        if event is None:
            logger.info(f"Event already exists for job {job}-{release} notes update")
            return jsonify({'error': 'Event already exists'}), 400
        
        # Update job fields (overwrite)
        job_record.notes = notes if notes else None
        job_record.last_updated_at = datetime.utcnow()
        job_record.source_of_update = 'Brain'

        # Add Trello update to outbox and process immediately (only if notes is not empty)
        outbox_item_created = False
        
        if job_record.trello_card_id and notes:
            try:
                # Create outbox item
                outbox_item = OutboxService.add(
                    destination='trello',
                    action='update_notes',
                    event_id=event.id
                )
                outbox_item_created = True
                
                # Try to process immediately for live updates
                try:
                    if OutboxService.process_item(outbox_item):
                        logger.info(f"Trello notes update processed immediately for job {job}-{release}")
                except Exception as process_error:
                    logger.error(f"Error during immediate processing of outbox {outbox_item.id}: {process_error}", exc_info=True)
                    
            except Exception as outbox_error:
                logger.error(f"Failed to create outbox for event {event.id}: {outbox_error}", exc_info=True)
        else:
            if not job_record.trello_card_id:
                logger.warning(
                    f"Job {job}-{release} has no trello_card_id, skipping Trello update",
                    extra={'job': job, 'release': release}
                )
            elif not notes:
                logger.info(f"Notes is empty for job {job}-{release}, skipping Trello comment")
        
        # Close event only if no outbox item was created
        if not outbox_item_created:
            JobEventService.close(event.id)
        
        # Commit all changes
        db.session.commit()
        
        logger.info(f"update_notes completed successfully", extra={
            'job': job,
            'release': release,
            'event_id': event.id
        })
        
        return jsonify({
            'status': 'success',
            'event_id': event.id
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
        created_count = 0
        trello_cards_created = 0
        
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
                
                # Check if job already exists
                existing_job = Job.query.filter_by(job=job_number, release=release_number).first()
                if existing_job:
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
                
                # Get current user and format source with username
                user = get_current_user()
                formatted_source = format_source_with_user('Brain', user)
                
                # Create event
                event = JobEvents(
                    job=job_number,
                    release=release_number,
                    action='created',
                    payload=excel_data_dict,
                    payload_hash=payload_hash,
                    source=formatted_source,
                    user_id=user.id if user else None
                )
                db.session.add(event)
                
                # Create new job
                new_job = Job(
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
                    fab_order=safe_float(row_values['fab_order']),
                    last_updated_at=datetime.utcnow(),
                    source_of_update='Brain'
                )
                db.session.add(new_job)
                db.session.commit()
                
                # Create Trello card for new job
                trello_result = create_trello_card_for_job(new_job, excel_data_dict)
                processed_record = {
                    'job': job_number,
                    'release': release_number,
                    'action': 'created'
                }
                
                if trello_result and trello_result.get('success'):
                    trello_cards_created += 1
                    processed_record['trello_card_created'] = True
                    processed_record['trello_card_id'] = trello_result.get('card_id')
                    db.session.commit()
                else:
                    error_msg = trello_result.get('error', 'Unknown error') if trello_result else 'Trello card creation failed'
                    errors.append({
                        'row': row_idx,
                        'error': error_msg,
                        'data': row
                    })
                
                # Update event applied_at time
                event = JobEvents.query.filter_by(payload_hash=payload_hash).first()
                if event:
                    event.applied_at = datetime.utcnow()
                    db.session.commit()
                
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
            'trello_cards_created': trello_cards_created,
            'error_count': len(errors),
            'processed': processed,
            'errors': errors if errors else None
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
@login_required
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
        job = request.args.get('job', type=int)  # Filter by job number
        release = request.args.get('release')  # Filter by release

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
            submittal_events = submittal_query.order_by(SubmittalEvents.created_at.desc()).limit(limit).all()
        # Apply job and release filters (only applies to job events)
        # When filtering by job/release, exclude submittal events entirely
        elif job is not None or release:
            if job is not None:
                job_query = job_query.filter(JobEvents.job == job)
            if release:
                job_query = job_query.filter(JobEvents.release == str(release).strip())
            # Don't include submittal events when filtering by job/release
            job_events = job_query.order_by(JobEvents.created_at.desc()).limit(limit).all()
            submittal_events = []
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
                'job': job,
                'release': release,
            }
        }), 200
    except Exception as e:
        logger.error("Error getting job events", error=str(e))
        return jsonify({"error": str(e)}), 500

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

@brain_bp.route("/recalculate-scheduling", methods=["POST"])
@login_required
def recalculate_scheduling():
    """
    Recalculate and update scheduling fields (start_install, comp_eta) for all jobs.
    
    This endpoint:
    - Fetches all jobs from the database
    - Calculates scheduling fields based on fab_order, stage, fab_hrs, install_hrs
    - Updates start_install and comp_eta fields in the database
    - Commits changes in batches
    
    Query Parameters:
        reference_date (string, optional): ISO date string for reference date (defaults to today)
        batch_size (int, optional): Number of jobs to commit per batch (default: 100)
    
    Returns:
        JSON object with:
        - total_jobs: Total number of jobs processed
        - updated: Number of jobs that had changes
        - errors: List of any errors encountered
        
    Status Codes:
        - 200: Success
        - 500: Server error
    """
    from datetime import datetime
    from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling
    
    try:
        # Get optional parameters
        reference_date_str = request.args.get('reference_date')
        batch_size = request.args.get('batch_size', 100, type=int)
        
        reference_date = None
        if reference_date_str:
            try:
                reference_date = datetime.fromisoformat(reference_date_str.replace('Z', '+00:00')).date()
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid reference_date parameter: {reference_date_str}, using today")
        
        logger.info(f"Recalculate scheduling endpoint called (reference_date={reference_date}, batch_size={batch_size})")
        
        result = recalculate_all_jobs_scheduling(
            reference_date=reference_date,
            batch_size=batch_size
        )
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error in recalculate scheduling: {e}", exc_info=True)
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

