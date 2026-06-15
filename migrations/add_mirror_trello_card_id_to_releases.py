"""
Migration: Add mirror_trello_card_id column to releases table.

Adds a nullable string mirror_trello_card_id column holding the linked mirror
(installer-team) Trello card id, so inbound webhooks on the mirror card resolve
back to the release with a direct lookup instead of an attachment walk.

Usage:
    python migrations/add_mirror_trello_card_id_to_releases.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db

app = create_app()

ADD_COLUMN_SQL = """
ALTER TABLE releases
ADD COLUMN IF NOT EXISTS mirror_trello_card_id VARCHAR(64);
"""


def run_migration():
    with app.app_context():
        print("Adding mirror_trello_card_id column to releases table...")
        db.session.execute(db.text(ADD_COLUMN_SQL))
        db.session.commit()
        print("Column added (or already exists).")


if __name__ == '__main__':
    run_migration()
