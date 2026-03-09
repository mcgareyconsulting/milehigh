from app.brain import brain_bp
from flask import jsonify
from app.models import Jobs, ProjectManager, db
from app.auth.utils import login_required
from app.logging_config import get_logger

logger = get_logger(__name__)


@brain_bp.route('/jobsites/map')
@login_required
def jobsites_map():
    """Return a GeoJSON FeatureCollection of all jobsites that have geofence polygons."""
    try:
        rows = (
            db.session.query(Jobs, ProjectManager)
            .outerjoin(ProjectManager, Jobs.pm_id == ProjectManager.id)
            .filter(Jobs.geofence_geojson.isnot(None))
            .all()
        )

        features = []
        for job, pm in rows:
            features.append({
                "type": "Feature",
                "geometry": job.geofence_geojson,
                "properties": {
                    "id": job.id,
                    "job_name": job.name,
                    "address": job.address,
                    "pm_name": pm.name if pm else None,
                    "pm_color": pm.color if pm else "#888888",
                    "latitude": job.latitude,
                    "longitude": job.longitude,
                },
            })

        return jsonify({"type": "FeatureCollection", "features": features}), 200

    except Exception as exc:
        logger.error("Error fetching jobsites map", error=str(exc))
        return jsonify({"error": "Failed to fetch jobsites map", "details": str(exc)}), 500
