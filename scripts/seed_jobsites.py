"""
Seed jobsites from docs/json/jobsites.json into the Jobs table.

Usage:
    python scripts/seed_jobsites.py

Each jobsite is inserted with radius_meters=3218.69 (2 miles).
geofence_geojson is left null; run POST /admin/jobsites/regenerate-geofences
to populate it.
"""
import json
import os
import sys
from pathlib import Path

# Allow imports from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.models import db, Jobs, ProjectManager

RADIUS_METERS = 2 * 1609.34  # 3218.68 m = 2 miles
JSON_PATH = Path(__file__).resolve().parent.parent / "docs" / "json" / "jobsites.json"


def seed():
    app = create_app()
    with app.app_context():
        data = json.loads(JSON_PATH.read_text())
        jobsites = data["jobsites"]

        created = 0
        skipped = 0

        for js in jobsites:
            job_number = js["job_number"]

            # Skip if already exists
            if Jobs.query.filter_by(job_number=job_number).first():
                print(f"  SKIP  job_number={job_number} ({js['name']}) — already exists")
                skipped += 1
                continue

            # Warn if PM not found
            pm_id = js.get("pm_id")
            if pm_id and not ProjectManager.query.get(pm_id):
                print(f"  WARN  pm_id={pm_id} not found in project_managers table for {js['name']}")

            job = Jobs(
                job_number=job_number,
                name=js["name"],
                address=js.get("address"),
                latitude=js.get("latitude"),
                longitude=js.get("longitude"),
                pm_id=pm_id,
                is_active=js.get("is_active", True),
                geometry=js["geometry"],
                radius_meters=RADIUS_METERS,
                geofence_geojson=None,
            )
            db.session.add(job)
            print(f"  CREATE job_number={job_number} ({js['name']})")
            created += 1

        db.session.commit()
        print(f"\nDone. Created {created} jobsite(s), skipped {skipped}.")


if __name__ == "__main__":
    seed()
