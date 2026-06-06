"""
Migration: Add num_guys column to releases table.

Adds a nullable float num_guys column (installer headcount). Parsed/persisted from
the Trello card description ("**Number of Guys:** N"); treated as 2 when absent.
Used to size install duration: comp_eta = start_install + ceil(install_hrs / (num_guys * 8)) business days.

Usage:
    python migrations/add_num_guys_to_releases.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db

app = create_app()

ADD_COLUMN_SQL = """
ALTER TABLE releases
ADD COLUMN IF NOT EXISTS num_guys DOUBLE PRECISION;
"""


def run_migration():
    with app.app_context():
        print("Adding num_guys column to releases table...")
        db.session.execute(db.text(ADD_COLUMN_SQL))
        db.session.commit()
        print("Column added (or already exists).")


if __name__ == '__main__':
    run_migration()
