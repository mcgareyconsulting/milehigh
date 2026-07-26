"""
@milehigh-header
schema_version: 1
purpose: Read-only HTTP endpoints for the Projects tab. Serve the live rollup payload
  (Projects row + value-joined Releases/Submittals + merged events + computed health)
  that the ProjectDetail modal overlays onto its demo scaffold. Login-gated, GET-only.
exports:
  (routes registered on brain_bp)
    GET /brain/projects            -> {projects: [...]}   index with counts
    GET /brain/projects/<job_number> -> live project payload, or 404
imports_from: [flask, app.brain, app.auth.utils, app.brain.projects.service, app.logging_config]
imported_by: [app/brain/__init__.py]
invariants:
  - Read-only. No writes; SELECTs only.
"""
from flask import jsonify

from app.brain import brain_bp
from app.auth.utils import login_required
from app.brain.projects import service
from app.logging_config import get_logger

logger = get_logger(__name__)


@brain_bp.route("/projects", methods=["GET"])
@login_required
def projects_index():
    """Every project + release/submittal counts and assigned PM."""
    return jsonify({"projects": service.list_projects()}), 200


@brain_bp.route("/projects/<job_number>", methods=["GET"])
@login_required
def project_live(job_number):
    """Live rollup for one project by job_number. 404 if no matching Projects row."""
    try:
        payload = service.get_project_live(job_number)
    except Exception as exc:
        logger.error(
            "project_live_failed",
            job=job_number,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return jsonify({"error": "Failed to load project."}), 500
    if payload is None:
        return jsonify({"error": "Project not found."}), 404
    return jsonify(payload), 200
