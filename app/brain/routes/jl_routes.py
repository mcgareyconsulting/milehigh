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
        job: Job database object
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
        from app.trello.api import (
            get_list_by_name, update_job_record_with_trello_data,
            calculate_installation_duration, add_comment_to_trello_card,
            update_card_custom_field_number
        )
        from app.config import Config as cfg
        import requests
        import math
        
        # Determine Trello list to create the card in (default to "Released" list)
        list_name = "Released"
        target_list = get_list_by_name(list_name)
        if not target_list:
            # Fall back to configured new-card list
            list_id = cfg.NEW_TRELLO_CARD_LIST_ID
        else:
            list_id = target_list["id"]
        
        # Format card title
        job_number = excel_data_dict.get('Job #', job.job)
        release_number = excel_data_dict.get('Release #', job.release)
        job_name = excel_data_dict.get('Job', job.job_name or 'Unknown Job')
        job_description = excel_data_dict.get('Description', job.description or 'Unknown Description')
        card_title = f"{job_number}-{release_number} {job_name} {job_description}"
        
        # Format card description with bold field names
        description_parts = []
        
        # Job description (first line)
        if excel_data_dict.get('Description') or job.description:
            desc = excel_data_dict.get('Description') or job.description
            description_parts.append(f"**Description:** {desc}")
        
        # Add field details with bold formatting
        install_hrs = excel_data_dict.get('Install HRS') or job.install_hrs
        if install_hrs:
            description_parts.append(f"**Install HRS:** {install_hrs}")
            # Number of Guys
            num_guys = 2
            description_parts.append(f"**Number of Guys:** {num_guys}")
            
            # Installation Duration calculation
            installation_duration = calculate_installation_duration(install_hrs, num_guys)
            if installation_duration is not None:
                description_parts.append(f"**Installation Duration:** {installation_duration} days")
        
        # Paint Color
        paint_color = excel_data_dict.get('Paint color') or job.paint_color
        if paint_color:
            description_parts.append(f"**Paint color:** {paint_color}")
        
        # Team
        pm = excel_data_dict.get('PM') or job.pm
        by = excel_data_dict.get('BY') or job.by
        if pm and by:
            description_parts.append(f"**Team:** PM: {pm} / BY: {by}")
        
        # Released
        released = excel_data_dict.get('Released') or job.released
        if released:
            if isinstance(released, str):
                released_date = to_date(released)
            else:
                released_date = released
            if released_date:
                description_parts.append(f"**Released:** {released_date}")
        
        # Join all description parts with newlines
        card_description = "\n".join(description_parts)
        
        # Create the card
        url = "https://api.trello.com/1/cards"
        
        payload = {
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
            "name": card_title,
            "desc": card_description,
            "idList": list_id,
            "pos": "top"  # Add to top of list
        }
        
        logger.info(f"Creating Trello card for job {job.job}-{job.release}")
        response = requests.post(url, params=payload)
        response.raise_for_status()
        
        card_data = response.json()
        logger.info(f"Trello card created successfully: {card_data['id']}")
        
        # Update the job record with Trello card data
        success = update_job_record_with_trello_data(job, card_data)
        
        if success:
            logger.info(f"Successfully updated database record with Trello data")
        else:
            logger.error(f"Failed to update database record with Trello data")
        
        # Handle Fab Order custom field
        fab_order_value = excel_data_dict.get('Fab Order') or job.fab_order
        if fab_order_value is not None and not pd.isna(fab_order_value):
            try:
                # Convert to int (round up if float)
                if isinstance(fab_order_value, float):
                    fab_order_int = math.ceil(fab_order_value)
                else:
                    fab_order_int = int(fab_order_value)
                
                # Update Trello custom field
                if cfg.FAB_ORDER_FIELD_ID:
                    from app.trello.api import update_card_custom_field_number
                    fab_order_success = update_card_custom_field_number(
                        card_data["id"],
                        cfg.FAB_ORDER_FIELD_ID,
                        fab_order_int
                    )
                    if fab_order_success:
                        logger.info(f"Successfully set Fab Order custom field to {fab_order_int}")
                        
                        # Sort the list if needed
                        from app.trello.utils import sort_list_if_needed
                        sort_list_if_needed(
                            list_id,
                            cfg.FAB_ORDER_FIELD_ID,
                            None,
                            "list"
                        )
            except (ValueError, TypeError) as e:
                logger.error(f"Could not convert Fab Order '{fab_order_value}' to int: {e}")
        
        # Handle notes field - append as comment if not empty
        notes_value = excel_data_dict.get('Notes') or job.notes
        if (notes_value is not None and 
            not pd.isna(notes_value) and 
            str(notes_value).strip() and
            str(notes_value).strip().lower() not in ['nan', 'none']):
            comment_success = add_comment_to_trello_card(card_data["id"], str(notes_value).strip())
            if comment_success:
                logger.info(f"Successfully added notes as comment to Trello card")
        
        return {
            "success": True,
            "card_id": card_data["id"],
            "card_name": card_data["name"],
            "card_url": card_data["url"]
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

