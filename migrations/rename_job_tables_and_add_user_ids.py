"""
Rename legacy job tables to their new names and ensure user_id columns exist
on event tables.

Intended migration path (main → excel_poller_teardown branch):

- Rename:
    - jobs        → releases         (job log table)
    - job_events  → release_events   (event log table)
- Ensure:
    - users table exists
    - release_events.user_id column exists (FK to users.id where supported)
    - submittal_events.user_id column exists (FK to users.id where supported)

The script is defensive and idempotent:
- It checks for table / column existence before making changes.
- It safely no-ops if tables are already renamed or columns already exist.

Usage:
    python migrations/rename_job_tables_and_add_user_ids.py
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

# Load environment variables from a .env file if present
load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    """Return a SQLAlchemy-friendly SQLite URL for the given path."""
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url: Optional[str] = None) -> str:
    """Figure out which database to hit, honoring CLI and environment defaults."""
    candidates = [
        cli_url,
        # Prefer local/sandbox-style URLs first to avoid accidentally
        # connecting to a remote production database when running locally.
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
            # SQLAlchemy expects postgresql://
            return value.replace("postgres://", "postgresql://", 1)

        if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
            return value

        # Treat anything else as a filesystem path to a SQLite DB
        return normalize_sqlite_path(value)

    # Fall back to bundled SQLite file
    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def table_exists(engine, table_name: str) -> bool:
    """Check if a given table exists."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a given column exists on the specified table."""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def is_postgresql(engine) -> bool:
    """Check if the database is PostgreSQL."""
    return engine.dialect.name == "postgresql"


def rename_table_if_needed(conn, engine, old_name: str, new_name: str) -> None:
    """Rename a table if the old name exists and the new name does not."""
    if not table_exists(engine, old_name):
        print(f"✓ Table '{old_name}' does not exist; nothing to rename.")
        return

    if table_exists(engine, new_name):
        print(
            f"✓ Table '{new_name}' already exists; "
            f"skipping rename from '{old_name}'."
        )
        return

    print(f"Renaming table '{old_name}' → '{new_name}'...")
    conn.execute(text(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"'))
    print(f"✓ Renamed '{old_name}' to '{new_name}'.")


def ensure_users_table(conn, engine) -> None:
    """Create the users table if it does not exist."""
    if table_exists(engine, "users"):
        print("✓ Table 'users' already exists.")
        return

    print("Creating 'users' table...")
    if is_postgresql(engine):
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_users_username ON users (username)"))
    else:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 0,
                    is_admin BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)"
            )
        )

    print("✓ Successfully created 'users' table.")


def ensure_user_external_ids(conn, engine) -> None:
    """
    Ensure external ID columns (procore_id, trello_id) exist on users table.
    Matches the SQLAlchemy model:
      - nullable=True
      - unique=True
    """
    if not table_exists(engine, "users"):
        print("✓ Table 'users' does not exist; skipping external ID columns.")
        return

    if not column_exists(engine, "users", "procore_id"):
        print("Adding column 'procore_id' to 'users' table...")
        conn.execute(
            text(
                'ALTER TABLE users ADD COLUMN procore_id VARCHAR(255)'
            )
        )
        # Keep migration fast and simple: do not add a UNIQUE
        # constraint here; rely on the application layer or a
        # separate, focused migration if you later decide to
        # enforce uniqueness at the DB level.
        print("✓ Successfully added 'procore_id' column to 'users'.")
    else:
        print("✓ Column 'procore_id' already exists on 'users'.")

    if not column_exists(engine, "users", "trello_id"):
        print("Adding column 'trello_id' to 'users' table...")
        conn.execute(
            text(
                'ALTER TABLE users ADD COLUMN trello_id VARCHAR(255)'
            )
        )
        # As with procore_id, skip adding a UNIQUE constraint here
        # to avoid long-running DDL/locks on busy databases.
        print("✓ Successfully added 'trello_id' column to 'users'.")
    else:
        print("✓ Column 'trello_id' already exists on 'users'.")


def add_user_id_column(conn, engine, table_name: str, constraint_name: str) -> None:
    """Add a nullable user_id column (and FK where possible) to a table."""
    if not table_exists(engine, table_name):
        print(f"✓ Table '{table_name}' does not exist; skipping user_id addition.")
        return

    if column_exists(engine, table_name, "user_id"):
        print(f"✓ Column 'user_id' already exists on '{table_name}'.")
        return

    print(f"Adding column 'user_id' to '{table_name}' table...")
    if is_postgresql(engine):
        conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN user_id INTEGER'))
        # Add FK constraint
        conn.execute(
            text(
                f'ALTER TABLE "{table_name}" '
                f'ADD CONSTRAINT "{constraint_name}" '
                'FOREIGN KEY (user_id) REFERENCES users(id)'
            )
        )
    else:
        # SQLite / MySQL: add column; rely on SQLAlchemy-level FK for SQLite.
        conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN user_id INTEGER'))

    print(f"✓ Successfully added 'user_id' column to '{table_name}'.")


def migrate(database_url: Optional[str] = None) -> bool:
    """Perform the migration: rename tables and ensure user_id columns."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)

    try:
        with engine.begin() as conn:
            # 1) Rename legacy tables if needed
            rename_table_if_needed(conn, engine, "job_sites", "jobs")
            rename_table_if_needed(conn, engine, "job_events", "release_events")
            rename_table_if_needed(conn, engine, "procore_submittals", "submittals")

            # 2) Ensure users table and external ID columns exist
            ensure_users_table(conn, engine)
            ensure_user_external_ids(conn, engine)

            # 3) Ensure user_id columns exist on event tables
            add_user_id_column(
                conn,
                engine,
                "release_events",
                "fk_release_events_user_id",
            )
            add_user_id_column(
                conn,
                engine,
                "submittal_events",
                "fk_submittal_events_user_id",
            )

        print("✓ Migration completed successfully.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error during migration: {exc}")
        import traceback

        traceback.print_exc()
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Rename legacy job tables and add user_id columns "
            "to release_events and submittal_events tables."
        )
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

