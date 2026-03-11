"""
Migration script to seed Releases table from Jobs table (one-time, idempotent).

Run this script with:
    python migrations/seed_releases_from_jobs.py

This migration:
1. Reads all Job rows from the jobs table
2. Maps Job fields to Releases fields
3. Inserts into releases table with ON CONFLICT handling
4. Is idempotent - can be run multiple times safely

Field mapping Job → Releases:
- Direct: job, release, job_name, description, fab_hrs, install_hrs, paint_color, pm, by, released, fab_order, start_install, comp_eta, job_comp, invoiced, notes
- Trello: trello_card_id, trello_card_name, trello_list_id, trello_list_name, trello_card_description, trello_card_date, viewer_url
- Derived: stage = trello_list_name, source_of_update = "Excel"
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, Job, Releases


def migrate() -> bool:
    """
    Seed Releases table from Job table (one-time, idempotent).

    Returns:
        bool: True if migration was successful, False on error.
    """
    app = create_app()
    with app.app_context():
        try:
            # Check if jobs table exists
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if 'jobs' not in inspector.get_table_names():
                print("✓ 'jobs' table does not exist yet. Skipping seed (will run after job creation).")
                return True

            if 'releases' not in inspector.get_table_names():
                print("✗ ERROR: 'releases' table does not exist. Create it before seeding.")
                return False

            # Query all Job rows
            jobs = Job.query.all()
            if not jobs:
                print("✓ No jobs found in 'jobs' table. Skipping seed.")
                return True

            print(f"Seeding {len(jobs)} job(s) into 'releases' table...")

            created = 0
            skipped = 0

            for job in jobs:
                # Check if release already exists (idempotent)
                existing = Releases.query.filter_by(job=job.job, release=job.release).first()
                if existing:
                    skipped += 1
                    continue

                # Map Job fields to Releases
                release = Releases(
                    job=job.job,
                    release=job.release,
                    job_name=job.job_name,
                    description=job.description,
                    fab_hrs=job.fab_hrs,
                    install_hrs=job.install_hrs,
                    paint_color=job.paint_color,
                    pm=job.pm,
                    by=job.by,
                    released=job.released,
                    fab_order=job.fab_order,
                    stage=job.trello_list_name,  # Derive stage from trello_list_name
                    stage_group=None,  # Not in Job model
                    banana_color=None,  # Not in Job model
                    start_install=job.start_install,
                    start_install_formula=job.start_install_formula,
                    start_install_formulaTF=job.start_install_formulaTF,
                    comp_eta=job.comp_eta,
                    job_comp=job.job_comp,
                    invoiced=job.invoiced,
                    notes=job.notes,
                    trello_card_id=job.trello_card_id,
                    trello_card_name=job.trello_card_name,
                    trello_list_id=job.trello_list_id,
                    trello_list_name=job.trello_list_name,
                    trello_card_description=job.trello_card_description,
                    trello_card_date=job.trello_card_date,
                    viewer_url=job.viewer_url,
                    source_of_update="Excel",  # OneDrive jobs come from Excel
                    last_updated_at=job.last_updated_at,
                )
                db.session.add(release)
                created += 1

            db.session.commit()
            print(f"✓ Seed completed: {created} created, {skipped} already existed")
            return True

        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
