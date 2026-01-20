"""
Job Log routes for handling CSV release data.

Provides API endpoints for releasing job data from CSV clipboard data.
"""
from app.brain import brain_bp
from flask import jsonify, request
from app.logging_config import get_logger
from app.models import Job, db, JobEvents
from datetime import datetime
import csv
import json 
import hashlib
import io
import pandas as pd

logger = get_logger(__name__)


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


@brain_bp.route("/job-log/release", methods=["POST"])
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
                
                # Create event
                event = JobEvents(
                    job=job_number,
                    release=release_number,
                    action='created',
                    payload=excel_data_dict,
                    payload_hash=payload_hash,
                    source='user'
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

