# Package
import os
from pathlib import Path
from datetime import datetime

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

    # Cache project id lookups
    project_id_cache = {}
    skipped_count = 0
    inserted_count = 0

    for _, row in df.iterrows():
        submittal_id = row['Submittals Id']
        if ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first():
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
            submittal_id=row['Submittals Id'],
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

    return {'success': True, 'rows_updated': len(df), 'projects_cached': len(project_id_cache)}