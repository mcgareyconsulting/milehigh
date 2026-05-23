"""
Tests for LocationService.get_job_numbers_for_location.

These run on in-memory SQLite, so they only exercise the Python point-in-polygon
fallback path. The PostGIS branch (which previously had a stale `FROM job_sites`
reference, fixed in this branch) cannot be exercised here. Verify that branch
manually against staging Postgres.
"""
from app.brain.drafting_work_load.service import LocationService
from app.models import Projects, db


def _make_project(job_number, polygon_coords, is_active=True):
    p = Projects(
        name=f"Project {job_number}",
        job_number=job_number,
        geofence_geojson={"type": "Polygon", "coordinates": [polygon_coords]},
        is_active=is_active,
    )
    db.session.add(p)
    db.session.flush()
    return p


def test_returns_job_numbers_for_point_inside_polygon(app):
    with app.app_context():
        # Square around (lng=-104.99, lat=39.74), ~1km half-extent
        _make_project("100", [
            [-105.00, 39.73], [-104.98, 39.73],
            [-104.98, 39.75], [-105.00, 39.75],
            [-105.00, 39.73],
        ])
        # A second project well to the east
        _make_project("200", [
            [-104.50, 39.73], [-104.48, 39.73],
            [-104.48, 39.75], [-104.50, 39.75],
            [-104.50, 39.73],
        ])
        db.session.commit()

        result = LocationService.get_job_numbers_for_location(lat=39.74, lng=-104.99)
        assert result == ["100"]


def test_returns_empty_when_no_polygon_contains_point(app):
    with app.app_context():
        _make_project("100", [
            [-105.00, 39.73], [-104.98, 39.73],
            [-104.98, 39.75], [-105.00, 39.75],
            [-105.00, 39.73],
        ])
        db.session.commit()

        result = LocationService.get_job_numbers_for_location(lat=40.50, lng=-100.00)
        assert result == []


def test_skips_inactive_projects(app):
    with app.app_context():
        _make_project("100", [
            [-105.00, 39.73], [-104.98, 39.73],
            [-104.98, 39.75], [-105.00, 39.75],
            [-105.00, 39.73],
        ], is_active=False)
        db.session.commit()

        # Inactive projects are filtered in the PostGIS SQL but the Python fallback
        # iterates Projects.query.filter_by(is_active=True), so this still returns [].
        result = LocationService.get_job_numbers_for_location(lat=39.74, lng=-104.99)
        assert result == []
