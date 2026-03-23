from flask import Blueprint, jsonify, request
from app.models import Projects, db
from app.auth.utils import admin_required
from app.brain.map.utils.geofence import generate_geofence_polygon
from app.logging_config import get_logger
from app.procore.client import get_procore_client
from app.procore.procore import get_project_info

logger = get_logger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route('/jobsites/regenerate-geofences', methods=['POST'])
@admin_required
def regenerate_geofences():
    """Regenerate geofence polygons for all jobsites and persist to the database."""
    try:
        projects = Projects.query.filter(
            Projects.latitude.isnot(None),
            Projects.longitude.isnot(None),
            Projects.radius_meters.isnot(None),
        ).all()
        for project in projects:
            project.geofence_geojson = generate_geofence_polygon(
                project.latitude,
                project.longitude,
                project.radius_meters,
            )
        db.session.commit()
        return jsonify({"jobsites_updated": len(projects)}), 200

    except Exception as exc:
        logger.error("Error regenerating geofences", error=str(exc))
        db.session.rollback()
        return jsonify({"error": "Failed to regenerate geofences", "details": str(exc)}), 500


@admin_bp.route('/procore/add-project/preview', methods=['POST'])
@admin_required
def add_project_preview():
    """Fetch submittals from Procore API (read-only) and return a preview for admin confirmation."""
    try:
        body = request.get_json() or {}
        raw_id = body.get('project_id')
        if raw_id is None:
            return jsonify({"error": "project_id is required"}), 400
        try:
            project_id = int(raw_id)
        except (ValueError, TypeError):
            return jsonify({"error": "project_id must be an integer"}), 400

        procore_client = get_procore_client()
        all_submittals = procore_client.get_submittals(project_id)
        project_info = get_project_info(project_id)

        submittal_counts = {}
        for s in all_submittals:
            if not isinstance(s, dict):
                continue
            status = s.get('status')
            if isinstance(status, dict):
                status = status.get('name') or status.get('value') or 'Unknown'
            status = str(status).strip() if status else 'Unknown'
            submittal_counts[status] = submittal_counts.get(status, 0) + 1

        return jsonify({
            "project_id": project_id,
            "project_name": project_info.get("name") if project_info else None,
            "project_number": project_info.get("project_number") if project_info else None,
            "webhook_url": procore_client.webhook_url,
            "submittal_counts": submittal_counts,
            "total": len(all_submittals),
        }), 200

    except Exception as exc:
        logger.error("Error previewing add-project", error=str(exc))
        return jsonify({"error": "Failed to preview project", "details": str(exc)}), 500


@admin_bp.route('/procore/add-project/confirm', methods=['POST'])
@admin_required
def add_project_confirm():
    """Create Procore webhook and sync all submittals to DB for a given project."""
    try:
        body = request.get_json() or {}
        raw_id = body.get('project_id')
        if raw_id is None:
            return jsonify({"error": "project_id is required"}), 400
        try:
            project_id = int(raw_id)
        except (ValueError, TypeError):
            return jsonify({"error": "project_id must be an integer"}), 400

        from app.procore.scripts.create import create_webhook_and_trigger
        from app.procore.scripts.sync_submittals import sync_submittals_for_project

        procore_client = get_procore_client()
        project_info = get_project_info(project_id)
        project_number = project_info.get("project_number") if project_info else None
        project_name = project_info.get("name") if project_info else None

        webhook_result = create_webhook_and_trigger(procore_client, project_id, project_number)

        if webhook_result.get("status") == "error":
            return jsonify({
                "error": "Failed to create webhook",
                "details": webhook_result.get("error"),
                "webhook_result": webhook_result,
            }), 500

        sync_result = sync_submittals_for_project(project_id)

        return jsonify({
            "project_id": project_id,
            "project_name": project_name,
            "webhook_result": webhook_result,
            "sync_result": sync_result,
        }), 200

    except Exception as exc:
        logger.error("Error confirming add-project", error=str(exc))
        return jsonify({"error": "Failed to add project", "details": str(exc)}), 500
