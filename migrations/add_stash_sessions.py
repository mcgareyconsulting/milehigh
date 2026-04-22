"""
Migration: Create stash_sessions and stashed_job_changes tables.

Supports the Thursday review-meeting "stash" flow where an admin can pause
UI edits from being applied, review them as a batch, and apply (or discard)
them all at the end of the meeting.

Enforces at most one active session globally via a partial unique index.

Usage:
    python migrations/add_stash_sessions.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db

app = create_app()


CREATE_SESSIONS_SQL = """
CREATE TABLE IF NOT EXISTS stash_sessions (
    id SERIAL PRIMARY KEY,
    started_by_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);
"""

CREATE_ACTIVE_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ix_stash_session_active
    ON stash_sessions (status)
    WHERE status = 'active';
"""

CREATE_CHANGES_SQL = """
CREATE TABLE IF NOT EXISTS stashed_job_changes (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES stash_sessions(id) ON DELETE CASCADE,
    job INTEGER NOT NULL,
    release VARCHAR(16) NOT NULL,
    field VARCHAR(32) NOT NULL,
    baseline_value JSONB,
    new_value JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_at TIMESTAMP,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    error TEXT,
    CONSTRAINT _stash_change_uc UNIQUE (session_id, job, release, field)
);
"""

CREATE_CHANGES_SESSION_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_stashed_job_changes_session_id
    ON stashed_job_changes (session_id);
"""

CREATE_CHANGES_STATUS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_stashed_job_changes_session_status
    ON stashed_job_changes (session_id, status);
"""


def run_migration():
    with app.app_context():
        print("Creating stash_sessions table...")
        db.session.execute(db.text(CREATE_SESSIONS_SQL))
        db.session.commit()
        print("  stash_sessions ready.")

        print("Creating partial unique index on stash_sessions(status='active')...")
        db.session.execute(db.text(CREATE_ACTIVE_UNIQUE_INDEX_SQL))
        db.session.commit()
        print("  index ready.")

        print("Creating stashed_job_changes table...")
        db.session.execute(db.text(CREATE_CHANGES_SQL))
        db.session.commit()
        print("  stashed_job_changes ready.")

        print("Creating stashed_job_changes indexes...")
        db.session.execute(db.text(CREATE_CHANGES_SESSION_INDEX_SQL))
        db.session.execute(db.text(CREATE_CHANGES_STATUS_INDEX_SQL))
        db.session.commit()
        print("  indexes ready.")

        print("Migration complete.")


if __name__ == '__main__':
    run_migration()
