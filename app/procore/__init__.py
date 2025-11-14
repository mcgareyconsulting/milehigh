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
    file = request.files['file']
    df = pd.read_excel(file)

    # drop all columns in procoresubmittal table
    ProcoreSubmittal.query.delete()
    db.session.commit()

    # Cache project id lookups
    project_id_cache = {}
    skipped_count = 0
    inserted_count = 0

    for _, row in df.iterrows():
        submittal_id = str(row['Submittals Id']) if pd.notna(row['Submittals Id']) else None
        if not submittal_id or ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first():
            skipped_count += 1
            continue

        project_name = row['Project Name']

        # Get project_id from cache or API
        if project_name not in project_id_cache:
            project_id = get_project_id_by_project_name(project_name)
            project_id_cache[project_name] = project_id
        else:
            project_id = project_id_cache[project_name]

        # Insert/update in DB
        submittal = ProcoreSubmittal(
            submittal_id=submittal_id,
            procore_project_id=project_id,
            project_number=row['Project Number'],
            project_name=project_name,
            title=row['Title'],
            ball_in_court_due_date=clean_value(row['Ball In Court Due Date']),
            status=row['Status'],
            type=row['Type'],
            ball_in_court=row['Ball In Court'],
            submittal_manager=row['Submittal Manager']
        )
        db.session.add(submittal)
        inserted_count += 1
    db.session.commit()

    # Assign order_number based on ball_in_court_due_date for submittals with null order_number
    # Group by ball_in_court, sort by ball_in_court_due_date (nulls last), then assign 0-x within each group
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

    return {'success': True, 'rows_updated': len(df), 'projects_cached': len(project_id_cache), 'order_numbers_assigned': total_assigned}

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