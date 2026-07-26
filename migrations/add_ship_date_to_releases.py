"""
Migration: Add ship_date + ship_date_no_color columns to releases table.

Adds:
- ship_date (DATE, nullable): the planned ship date. An independent hard date,
  ideally one business day before start_install. Does NOT drive Trello due dates
  or comp_eta/scheduling.
- ship_date_no_color (BOOLEAN, default FALSE): mirrors start_install_no_color;
  suppresses the ship date's color flag once the release reaches the complete zone.

Both statements are idempotent (ADD COLUMN IF NOT EXISTS) and metadata-only
(nullable date / boolean with a constant default), so they are instant and safe
to re-run. A lock_timeout makes a blocked ALTER fail fast rather than queue.

Usage:
    python migrations/add_ship_date_to_releases.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db

app = create_app()

STATEMENTS = [
    "SET lock_timeout = '5s';",
    "ALTER TABLE releases ADD COLUMN IF NOT EXISTS ship_date DATE;",
    "ALTER TABLE releases ADD COLUMN IF NOT EXISTS ship_date_no_color BOOLEAN NOT NULL DEFAULT FALSE;",
]


def run_migration():
    with app.app_context():
        dialect = db.engine.dialect.name
        print("Adding ship_date + ship_date_no_color columns to releases table...")
        for stmt in STATEMENTS:
            # SET lock_timeout is Postgres-only; skip it on SQLite (local/tests).
            if stmt.startswith("SET lock_timeout") and dialect != "postgresql":
                continue
            db.session.execute(db.text(stmt))
        db.session.commit()
        print("Columns added (or already exist).")


if __name__ == '__main__':
    run_migration()
