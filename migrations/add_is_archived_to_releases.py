"""
Migration: Add is_archived column to releases table.

Adds a boolean is_archived column (default False) and backfills it
to True for releases where both job_comp='X' AND invoiced='X'.

Usage:
    python migrations/add_is_archived_to_releases.py
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db

app = create_app()

# PostgreSQL: ADD COLUMN IF NOT EXISTS (supported since Postgres 9.6)
ADD_COLUMN_SQL = """
ALTER TABLE releases
ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE;
"""

BACKFILL_SQL = """
UPDATE releases
SET is_archived = TRUE
WHERE UPPER(TRIM(COALESCE(job_comp, ''))) = 'X'
  AND UPPER(TRIM(COALESCE(invoiced, ''))) = 'X';
"""


def run_migration():
    with app.app_context():
        print("Adding is_archived column to releases table...")
        db.session.execute(db.text(ADD_COLUMN_SQL))
        db.session.commit()
        print("Column added (or already exists).")

        print("Backfilling is_archived for releases with both job_comp='X' and invoiced='X'...")
        result = db.session.execute(db.text(BACKFILL_SQL))
        db.session.commit()
        print(f"Backfill complete. {result.rowcount} rows updated.")


if __name__ == '__main__':
    run_migration()
