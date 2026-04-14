"""
@milehigh-header
schema_version: 1
purpose: Serve jobsite geofence polygons as GeoJSON for the map view.
exports:
  jobsites_map: GET endpoint returning a GeoJSON FeatureCollection of all jobsites with geofences.
imports_from: [app.brain, flask, app.models, app.auth.utils, app.logging_config]
imported_by: [app/brain/__init__.py]
invariants:
  - Only returns projects where geofence_geojson is not None.
  - Route is registered on brain_bp, not its own blueprint.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""

from app.brain import brain_bp
from flask import jsonify
from app.models import Projects, ProjectManager, db
from app.auth.utils import login_required
from app.logging_config import get_logger

logger = get_logger(__name__)


@brain_bp.route('/jobsites/map')
@login_required
def jobsites_map():
    """Return a GeoJSON FeatureCollection of all jobsites that have geofence polygons."""
    try:
        rows = (
            db.session.query(Projects, ProjectManager)
            .outerjoin(ProjectManager, Projects.pm_id == ProjectManager.id)
            .filter(Projects.geofence_geojson.isnot(None))
            .all()
        )

        features = []
        for project, pm in rows:
            features.append({
                "type": "Feature",
                "geometry": project.geofence_geojson,
                "properties": {
                    "id": project.id,
                    "job_name": project.name,
                    "address": project.address,
                    "pm_name": pm.name if pm else None,
                    "pm_color": pm.color if pm else "#888888",
                    "latitude": project.latitude,
                    "longitude": project.longitude,
                },
            })

        return jsonify({"type": "FeatureCollection", "features": features}), 200

    except Exception as exc:
        logger.error("Error fetching jobsites map", error=str(exc))
        return jsonify({"error": "Failed to fetch jobsites map", "details": str(exc)}), 500
