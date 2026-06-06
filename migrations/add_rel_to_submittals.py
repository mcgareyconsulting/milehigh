"""
Add `rel` and `rel_assigned_at` columns to the submittals table.

`rel` holds the release identifier (100-999) shown in the new "Rel" column on the
Drafting Work Load tab. It is assigned the first time a submittal arrives as a DRR
("Drafting Release Review") type, sequentially per DRR submittal, wrapping 999 -> 100.
`rel_assigned_at` records when the number was handed out so the next assignment can be
derived from the most recently assigned value (handles wraparound).

This migration only adds the columns. Existing DRR submittals are intentionally NOT
backfilled — Rel numbers are assigned going forward as new DRR submittals are synced
from Procore.

Usage:
    python migrations/add_rel_to_submittals.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db

app = create_app()


def upgrade():
    """Add rel and rel_assigned_at columns to submittals (idempotent)."""
    with app.app_context():
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('submittals')]

        with db.engine.connect() as conn:
            if 'rel' not in columns:
                conn.execute(db.text("""
                    ALTER TABLE submittals
                    ADD COLUMN rel INTEGER DEFAULT NULL
                """))
                print("✓ Added rel column to submittals")
            else:
                print("rel column already exists, skipping")

            if 'rel_assigned_at' not in columns:
                conn.execute(db.text("""
                    ALTER TABLE submittals
                    ADD COLUMN rel_assigned_at TIMESTAMP DEFAULT NULL
                """))
                print("✓ Added rel_assigned_at column to submittals")
            else:
                print("rel_assigned_at column already exists, skipping")

            conn.commit()


def downgrade():
    """Remove rel and rel_assigned_at columns from submittals."""
    with app.app_context():
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('submittals')]

        with db.engine.connect() as conn:
            if 'rel' in columns:
                conn.execute(db.text("ALTER TABLE submittals DROP COLUMN IF EXISTS rel"))
                print("✓ Removed rel column from submittals")
            if 'rel_assigned_at' in columns:
                conn.execute(db.text("ALTER TABLE submittals DROP COLUMN IF EXISTS rel_assigned_at"))
                print("✓ Removed rel_assigned_at column from submittals")
            conn.commit()


if __name__ == '__main__':
    upgrade()
