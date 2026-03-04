"""
Rename outbox table to trello_outbox and add procore_outbox for Procore API calls.

- Rename: outbox → trello_outbox
- Create: procore_outbox (submittal_id, project_id, action, request_payload, source_application_id, status, retry fields, timestamps)

Idempotent: safe to run multiple times.
Usage:
    python migrations/rename_outbox_to_trello_and_add_procore_outbox.py
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")
load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url=None):
    candidates = [
        cli_url,
        os.environ.get("SANDBOX_DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
        os.environ.get("DATABASE_URL"),
    ]
    for value in candidates:
        if not value:
            continue
        value = value.strip()
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql://", 1)
        if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
            return value
        return normalize_sqlite_path(value)
    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def table_exists(engine, table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def is_postgresql(engine) -> bool:
    return engine.dialect.name == "postgresql"


def rename_table_if_needed(conn, engine, old_name: str, new_name: str) -> None:
    if not table_exists(engine, old_name):
        print(f"✓ Table '{old_name}' does not exist; nothing to rename.")
        return
    if table_exists(engine, new_name):
        print(f"✓ Table '{new_name}' already exists; skipping rename.")
        return
    print(f"Renaming table '{old_name}' → '{new_name}'...")
    conn.execute(text(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"'))
    print(f"✓ Renamed '{old_name}' to '{new_name}'.")


def create_procore_outbox_if_needed(conn, engine) -> None:
    if table_exists(engine, "procore_outbox"):
        print("✓ Table 'procore_outbox' already exists.")
        return
    print("Creating table 'procore_outbox'...")
    if is_postgresql(engine):
        conn.execute(
            text(
                """
                CREATE TABLE procore_outbox (
                    id SERIAL PRIMARY KEY,
                    submittal_id VARCHAR(255) NOT NULL,
                    project_id INTEGER NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    request_payload JSONB,
                    source_application_id VARCHAR(255),
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 5,
                    next_retry_at TIMESTAMP,
                    error_message TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_procore_outbox_submittal_id ON procore_outbox (submittal_id)"))
        conn.execute(text("CREATE INDEX ix_procore_outbox_project_id ON procore_outbox (project_id)"))
        conn.execute(text("CREATE INDEX ix_procore_outbox_source_application_id ON procore_outbox (source_application_id)"))
    else:
        conn.execute(
            text(
                """
                CREATE TABLE procore_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submittal_id VARCHAR(255) NOT NULL,
                    project_id INTEGER NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    request_payload TEXT,
                    source_application_id VARCHAR(255),
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 5,
                    next_retry_at TIMESTAMP,
                    error_message TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_procore_outbox_submittal_id ON procore_outbox (submittal_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_procore_outbox_project_id ON procore_outbox (project_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_procore_outbox_source_application_id ON procore_outbox (source_application_id)"))
    print("✓ Created 'procore_outbox'.")


def main():
    parser = argparse.ArgumentParser(description="Rename outbox to trello_outbox and add procore_outbox")
    parser.add_argument("--database-url", help="Database URL (default from env)")
    args = parser.parse_args()
    url = infer_database_url(args.database_url)
    print(f"Using database: {url.split('@')[-1] if '@' in url else url}")

    try:
        engine = create_engine(url)
        # Rename outbox → trello_outbox (own transaction)
        with engine.begin() as conn:
            rename_table_if_needed(conn, engine, "outbox", "trello_outbox")
        # Create procore_outbox (own transaction)
        with engine.begin() as conn:
            create_procore_outbox_if_needed(conn, engine)
        print("Migration completed.")
    except OperationalError as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
