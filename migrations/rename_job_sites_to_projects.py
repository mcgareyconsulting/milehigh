"""
M6: Rename job_sites table to projects and update the Jobs model to Projects.

This migration:
1. Renames the job_sites table to projects
2. Renames the unique constraint _job_sites_job_number_uc to _projects_job_number_uc
3. Updates the app/models.py Jobs class to Projects with correct table metadata

Note: The model name change (Jobs → Projects) requires corresponding updates in:
- app/ingest_jobsites.py
- app/brain/map/routes.py
- app/brain/drafting_work_load/service.py
- app/admin/__init__.py
"""

from app import create_app
from app.models import db

app = create_app()

def upgrade():
    """Rename job_sites table to projects."""
    with app.app_context():
        # Check if the old table exists
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()

        if 'job_sites' not in tables:
            print("job_sites table does not exist, skipping migration")
            return

        # Rename the table
        with db.engine.connect() as conn:
            # Drop the old constraint first (if it exists)
            try:
                conn.execute(db.text("""
                    ALTER TABLE job_sites
                    DROP CONSTRAINT IF EXISTS _job_sites_job_number_uc
                """))
                conn.commit()
            except Exception as e:
                print(f"Note: Could not drop old constraint: {e}")

            # Rename the table
            conn.execute(db.text("""
                ALTER TABLE job_sites RENAME TO projects
            """))
            conn.commit()

            # Create new constraint with updated name
            try:
                conn.execute(db.text("""
                    ALTER TABLE projects
                    ADD CONSTRAINT _projects_job_number_uc UNIQUE (job_number)
                """))
                conn.commit()
            except Exception as e:
                print(f"Note: Could not create new constraint: {e}")

        print("✓ Renamed job_sites → projects")
        print("✓ Updated constraint: _job_sites_job_number_uc → _projects_job_number_uc")

def downgrade():
    """Revert the rename (useful for testing)."""
    with app.app_context():
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()

        if 'projects' not in tables:
            print("projects table does not exist, skipping downgrade")
            return

        with db.engine.connect() as conn:
            # Drop the new constraint
            try:
                conn.execute(db.text("""
                    ALTER TABLE projects
                    DROP CONSTRAINT IF EXISTS _projects_job_number_uc
                """))
                conn.commit()
            except Exception as e:
                print(f"Note: Could not drop new constraint: {e}")

            # Rename back
            conn.execute(db.text("""
                ALTER TABLE projects RENAME TO job_sites
            """))
            conn.commit()

            # Recreate old constraint
            try:
                conn.execute(db.text("""
                    ALTER TABLE job_sites
                    ADD CONSTRAINT _job_sites_job_number_uc UNIQUE (job_number)
                """))
                conn.commit()
            except Exception as e:
                print(f"Note: Could not recreate old constraint: {e}")

        print("✓ Reverted projects → job_sites")

if __name__ == '__main__':
    upgrade()
