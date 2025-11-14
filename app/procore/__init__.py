# Package
import os
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

import pandas as pd
from flask import Blueprint, request, jsonify, current_app
from app.models import db, ProcoreSubmittal

from app.procore.procore import get_project_id_by_project_name

from app.procore.helpers import clean_value

from app.logging_config import get_logger

logger = get_logger(__name__)

procore_bp = Blueprint("procore", __name__)

@procore_bp.route("/webhook", methods=["HEAD", "POST"])
def procore_webhook():
    if request.method == "HEAD":
        return "", 200

    if request.method == "POST":
        data = request.json
        print(data)
        return "", 200

@procore_bp.route("/api/drafting-work-load", methods=["GET"])
def drafting_work_load():
    """Return Drafting Work Load data from the db"""
    submittals = ProcoreSubmittal.query.all()
    return jsonify({
        "submittals": [submittal.to_dict() for submittal in submittals]
    }), 200

@procore_bp.route("/api/upload/drafting-workload-submittals", methods=["POST"])
def drafting_workload_submittals():
    """Upload a new Drafting Work Load Excel file and save to DB"""
    try:
        # Validate file presence
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Read Excel file
        try:
            df = pd.read_excel(file)
        except Exception as exc:
            logger.error(f"Error reading Excel file: {str(exc)}", exc_info=True)
            return jsonify({'error': f'Failed to read Excel file: {str(exc)}'}), 400

        # Validate required columns
        required_columns = ['Submittals Id', 'Project Name', 'Project Number', 'Title', 
                          'Ball In Court Due Date', 'Status', 'Type', 'Ball In Court', 
                          'Submittal Manager']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.error(f"Missing required columns: {missing_columns}")
            return jsonify({'error': f'Missing required columns: {", ".join(missing_columns)}'}), 400

        # Helper function to safely get row value
        def safe_get(row, col, default=None):
            if col not in df.columns:
                return default
            try:
                value = row[col]
                if pd.isna(value):
                    return default
                return value
            except (KeyError, IndexError):
                return default

        # drop all columns in procoresubmittal table
        try:
            ProcoreSubmittal.query.delete()
            db.session.commit()
        except Exception as exc:
            logger.error(f"Error deleting existing records: {str(exc)}", exc_info=True)
            db.session.rollback()
            return jsonify({'error': f'Failed to clear existing records: {str(exc)}'}), 500

        # Cache project id lookups
        project_id_cache = {}
        skipped_count = 0
        inserted_count = 0
        error_count = 0

        for idx, row in df.iterrows():
            try:
                # Get and validate submittal_id
                submittal_id_raw = safe_get(row, 'Submittals Id')
                if submittal_id_raw is None:
                    skipped_count += 1
                    logger.warning(f"Row {idx}: Missing Submittals Id, skipping")
                    continue
                
                submittal_id = str(submittal_id_raw).strip()
                if not submittal_id:
                    skipped_count += 1
                    logger.warning(f"Row {idx}: Empty Submittals Id, skipping")
                    continue

                # Check if already exists (shouldn't happen after delete, but check anyway)
                if ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first():
                    skipped_count += 1
                    continue

                project_name = safe_get(row, 'Project Name', '').strip()
                if not project_name:
                    skipped_count += 1
                    logger.warning(f"Row {idx}: Missing Project Name, skipping")
                    continue

                # Get project_id from cache or API
                if project_name not in project_id_cache:
                    try:
                        project_id = get_project_id_by_project_name(project_name)
                        project_id_cache[project_name] = project_id
                    except Exception as exc:
                        logger.error(f"Error getting project_id for '{project_name}': {str(exc)}")
                        project_id = None
                        project_id_cache[project_name] = None
                else:
                    project_id = project_id_cache[project_name]

                # Convert project_id to string if it exists
                if project_id is not None:
                    project_id = str(project_id)

                # Insert/update in DB with cleaned values
                submittal = ProcoreSubmittal(
                    submittal_id=submittal_id,
                    procore_project_id=project_id,
                    project_number=str(safe_get(row, 'Project Number', '') or '').strip() or None,
                    project_name=project_name,
                    title=str(safe_get(row, 'Title', '') or '').strip() or None,
                    ball_in_court_due_date=clean_value(safe_get(row, 'Ball In Court Due Date')),
                    status=str(safe_get(row, 'Status', '') or '').strip() or None,
                    type=str(safe_get(row, 'Type', '') or '').strip() or None,
                    ball_in_court=str(safe_get(row, 'Ball In Court', '') or '').strip() or None,
                    submittal_manager=str(safe_get(row, 'Submittal Manager', '') or '').strip() or None
                )
                db.session.add(submittal)
                inserted_count += 1
            except Exception as exc:
                error_count += 1
                logger.error(f"Error processing row {idx}: {str(exc)}", exc_info=True)
                continue

        # Commit all inserts
        try:
            db.session.commit()
        except Exception as exc:
            logger.error(f"Error committing submittals: {str(exc)}", exc_info=True)
            db.session.rollback()
            return jsonify({'error': f'Failed to save submittals: {str(exc)}'}), 500

        # Assign order_number based on ball_in_court_due_date for submittals with null order_number
        # Group by ball_in_court, sort by ball_in_court_due_date (nulls last), then assign 0-x within each group
        try:
            submittals_without_order = ProcoreSubmittal.query.filter(
                ProcoreSubmittal.order_number.is_(None)
            ).all()
            
            # Group by ball_in_court
            grouped_by_ball_in_court = defaultdict(list)
            for submittal in submittals_without_order:
                ball_in_court_value = submittal.ball_in_court or 'None'
                grouped_by_ball_in_court[ball_in_court_value].append(submittal)
            
            # Sort each group by ball_in_court_due_date (nulls last) and assign order numbers
            total_assigned = 0
            for ball_in_court_value, submittals in grouped_by_ball_in_court.items():
                # Sort by ball_in_court_due_date (nulls last)
                submittals.sort(key=lambda s: (s.ball_in_court_due_date is None, s.ball_in_court_due_date or date.max))
                
                # Assign 0.0-x within this group (using floats)
                for index, submittal in enumerate(submittals):
                    submittal.order_number = float(index)
                    submittal.last_updated = datetime.utcnow()
                    total_assigned += 1
            
            db.session.commit()
        except Exception as exc:
            logger.error(f"Error assigning order numbers: {str(exc)}", exc_info=True)
            db.session.rollback()
            # Don't fail the whole request if order assignment fails

        return jsonify({
            'success': True, 
            'rows_updated': len(df), 
            'rows_inserted': inserted_count,
            'rows_skipped': skipped_count,
            'rows_with_errors': error_count,
            'projects_cached': len(project_id_cache), 
            'order_numbers_assigned': total_assigned
        }), 200

    except Exception as exc:
        logger.error(f"Unexpected error in drafting_workload_submittals: {str(exc)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'error': 'An unexpected error occurred',
            'details': str(exc)
        }), 500

@procore_bp.route("/api/drafting-work-load/order", methods=["PUT"])
def update_submittal_order():
    """Update the order_number for a submittal (simple update, no cascading)"""
    try:
        data = request.json
        submittal_id = data.get('submittal_id')
        order_number = data.get('order_number')
        
        if submittal_id is None:
            return jsonify({
                "error": "submittal_id is required"
            }), 400
        
        # Ensure submittal_id is a string for proper database comparison
        submittal_id = str(submittal_id)
        
        submittal = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({
                "error": "Submittal not found"
            }), 404
        
        # Convert order_number to float if provided, allow None
        if order_number is not None:
            try:
                order_number = float(order_number)
            except (ValueError, TypeError):
                return jsonify({
                    "error": "order_number must be a valid number"
                }), 400
        
        # Simple update - no cascading
        submittal.order_number = order_number
        submittal.last_updated = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "order_number": order_number
        }), 200
    except Exception as exc:
        logger.error("Error updating submittal order", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to update order",
            "details": str(exc)
        }), 500