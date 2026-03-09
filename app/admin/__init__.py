from flask import Blueprint, jsonify
from app.models import Jobs, db
from app.auth.utils import admin_required
from app.brain.map.utils.geofence import generate_geofence_polygon
from app.logging_config import get_logger

logger = get_logger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route('/jobsites/regenerate-geofences', methods=['POST'])
@admin_required
def regenerate_geofences():
    """Regenerate geofence polygons for all jobsites and persist to the database."""
    try:
        jobs = Jobs.query.filter(
            Jobs.latitude.isnot(None),
            Jobs.longitude.isnot(None),
            Jobs.radius_meters.isnot(None),
        ).all()
        for job in jobs:
            job.geofence_geojson = generate_geofence_polygon(
                job.latitude,
                job.longitude,
                job.radius_meters,
            )
        db.session.commit()
        return jsonify({"jobsites_updated": len(jobs)}), 200

    except Exception as exc:
        logger.error("Error regenerating geofences", error=str(exc))
        db.session.rollback()
        return jsonify({"error": "Failed to regenerate geofences", "details": str(exc)}), 500
