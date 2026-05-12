"""
Migration: Add start_install_asap column to releases table.

Adds a boolean start_install_asap column (default False) used by ASAP Mode.

Usage:
    python migrations/add_start_install_asap_to_releases.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db

app = create_app()

ADD_COLUMN_SQL = """
ALTER TABLE releases
ADD COLUMN IF NOT EXISTS start_install_asap BOOLEAN NOT NULL DEFAULT FALSE;
"""


def run_migration():
    with app.app_context():
        print("Adding start_install_asap column to releases table...")
        db.session.execute(db.text(ADD_COLUMN_SQL))
        db.session.commit()
        print("Column added (or already exists).")


if __name__ == '__main__':
    run_migration()
