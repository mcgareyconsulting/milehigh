"""
Migration: Add installer column to releases table.

Adds a nullable installer column (VARCHAR(64)) holding the installer team name,
which matches the per-installer Trello list name. Used to display the installer
on the Job Log Start Install column and to route the mirror card.

Usage:
    python migrations/add_installer_to_releases.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db

app = create_app()

ADD_COLUMN_SQL = """
ALTER TABLE releases
ADD COLUMN IF NOT EXISTS installer VARCHAR(64);
"""


def run_migration():
    with app.app_context():
        print("Adding installer column to releases table...")
        db.session.execute(db.text(ADD_COLUMN_SQL))
        db.session.commit()
        print("Column added (or already exists).")


if __name__ == '__main__':
    run_migration()
