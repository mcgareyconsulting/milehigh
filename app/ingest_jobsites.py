"""
@milehigh-header
schema_version: 1
purpose: One-shot script to seed the Projects table from a JSON fixture (docs/jobsites.json), skipping existing job numbers.
exports:
  (script — no importable exports)
imports_from: [app, app/models]
imported_by: []
invariants:
  - Standalone script; invoked directly, not imported. Requires an app context (creates one via create_app).
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
## To run this script
# curl -X POST http://mile-high-metal-works-trello-onedrive.onrender.com/admin/jobsites/regenerate-geofences \
#   -H "Cookie: session=eyJfcGVybWFuZW50Ijp0cnVlLCJ1c2VyX2lkIjoyNSwidXNlcm5hbWUiOiJtY2dhcmV5Y29uc3VsdGluZ0BnbWFpbC5jb20ifQ.abRdRg.8fCLedpy8OpuHV49_0yfYYSXO3g" \
#   -H "Content-Type: application/json"


import json
from app import create_app
from app.models import Projects, db

app = create_app()

with app.app_context():
    with open("docs/jobsites.json") as f:
        data = json.load(f)

    for site in data["jobsites"]:
        existing = Projects.query.filter_by(job_number=site["job_number"]).first()

        if existing:
            print(f"Skipping existing project {site['job_number']}")
            continue

        project = Projects(
            name=site["name"],
            job_number=site["job_number"],
            geometry=site["geometry"],
            address=site.get("address"),
            latitude=site.get("latitude"),
            longitude=site.get("longitude"),
            radius_meters=site.get(
                "radius_meters", 3218.68
            ),  # Default to 2 miles if not provided
            pm_id=site.get("pm_id"),
            is_active=site.get("is_active", True),
            geofence_geojson=site.get("geofence_geojson"),
        )

        db.session.add(project)

    db.session.commit()

    # print("Import complete")

    # To update radius in bulk
    # Grab projects
    # projects = Projects.query.all()

    # Update radius
    # for project in projects:
    #     project.radius_meters = 3218.68
    #     db.session.add(project)
    # print("Updated radius")
