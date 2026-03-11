import json
from app import create_app
from app.models import Jobs, db

app = create_app()

with app.app_context():
    with open("docs/jobsites.json") as f:
        data = json.load(f)

    for site in data["jobsites"]:
        existing = Jobs.query.filter_by(job_number=site["job_number"]).first()

        if existing:
            print(f"Skipping existing job {site['job_number']}")
            continue

        job = Jobs(
            name=site["name"],
            job_number=site["job_number"],
            geometry=site["geometry"],
            address=site.get("address"),
            latitude=site.get("latitude"),
            longitude=site.get("longitude"),
            pm_id=site.get("pm_id"),
            is_active=site.get("is_active", True),
            geofence_geojson=site.get("geofence_geojson"),
        )

        db.session.add(job)

    db.session.commit()

    # print("Import complete")

    # To update radius in bulk
    # Grab jobs
    # jobs = Jobs.query.all()

    # Update radius
    # for job in jobs:
    #     job.radius_meters = 3218.68
    #     db.session.add(job)
    # print("Updated radius")
