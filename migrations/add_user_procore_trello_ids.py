"""
Add procore_id and trello_id columns to users table.

Standalone migration - safe to run even if rename_job_tables_and_add_user_ids
already ran (idempotent).

SQLAlchemy 2.0 note: Raw SQL does NOT auto-commit. We use
`with engine.begin() as conn:` which commits on block exit. Each column
is added in its OWN transaction so commits happen immediately and we
avoid long-held locks / commit freeze on Render/Postgres.

Usage:
    # Use local SQLite (recommended for dev - avoids remote DB hangs):
    python migrations/add_user_procore_trello_ids.py --database-url sqlite:///instance/jobs.sqlite

    # Or let it infer from env (may connect to remote Postgres):
    python migrations/add_user_procore_trello_ids.py
"""

import argparse
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url: Optional[str] = None) -> str:
    candidates = [
        cli_url,
        os.environ.get("JOBS_SQLITE_PATH"),
        os.environ.get("SANDBOX_DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
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


def column_exists(engine, table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def migrate(database_url: Optional[str] = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    # Use connect_timeout for Postgres to fail fast instead of hanging
    connect_args = {}
    if "postgresql" in db_url.lower():
        connect_args["connect_timeout"] = 10

    engine = create_engine(db_url, connect_args=connect_args)

    try:
        if not table_exists(engine, "users"):
            print("✗ Table 'users' does not exist. Run add_user_authentication first.")
            return False

        # Each column in its own transaction: commit immediately, avoid freeze.
        if not column_exists(engine, "users", "procore_id"):
            print("Adding column 'procore_id' to 'users' table...")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN procore_id VARCHAR(255)"))
            print("✓ Successfully added 'procore_id' column.")
        else:
            print("✓ Column 'procore_id' already exists.")

        if not column_exists(engine, "users", "trello_id"):
            print("Adding column 'trello_id' to 'users' table...")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN trello_id VARCHAR(255)"))
            print("✓ Successfully added 'trello_id' column.")
        else:
            print("✓ Column 'trello_id' already exists.")

        print("✓ Migration completed successfully.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error: {exc}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as exc:
        print(f"✗ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add procore_id and trello_id columns to users table."
    )
    parser.add_argument(
        "--database-url",
        help="Database URL (e.g. sqlite:///instance/jobs.sqlite for local dev)",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
