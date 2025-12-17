"""
Add was_multiple_assignees column to procore_submittals table.

Usage:
    python migrations/add_was_multiple_assignees_flag.py

The script is idempotent and safe to run multiple times. It inspects the current
schema before attempting to alter the table.
"""

import argparse
import os
import sys

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


def infer_database_url(cli_url: str = None) -> str:
    """Figure out which database to hit, honoring CLI and environment defaults."""
    candidates = [
        cli_url,
        os.environ.get("DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
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


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a given column exists on the specified table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def table_exists(engine, table_name: str) -> bool:
    """Check if a table exists."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def migrate(database_url: str = None) -> bool:
    """Perform the migration, adding was_multiple_assignees column if needed."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)

    try:
        if not table_exists(engine, "procore_submittals"):
            print("✗ Table 'procore_submittals' does not exist. Nothing to do.")
            return False

        # Check column existence BEFORE starting transaction to avoid lock conflicts
        column_exists_check = column_exists(engine, "procore_submittals", "was_multiple_assignees")

        if column_exists_check:
            print("✓ Column 'was_multiple_assignees' already exists. Nothing to do.")
            return True

        # Now start transaction only if we need to make changes
        with engine.begin() as conn:
            # Add was_multiple_assignees column if it doesn't exist
            print("Adding column 'was_multiple_assignees' to 'procore_submittals' table...")
            
            # Check if we're using PostgreSQL
            db_url_lower = str(db_url).lower()
            if "postgresql" in db_url_lower or "postgres" in db_url_lower:
                # PostgreSQL: Add column with NOT NULL and default
                conn.execute(text("""
                    ALTER TABLE procore_submittals 
                    ADD COLUMN was_multiple_assignees BOOLEAN NOT NULL DEFAULT FALSE
                """))
                print("✓ Successfully added 'was_multiple_assignees' column with default FALSE.")
            else:
                # SQLite: Add column (SQLite uses INTEGER for boolean, 0 = False, 1 = True)
                conn.execute(text("ALTER TABLE procore_submittals ADD COLUMN was_multiple_assignees INTEGER DEFAULT 0"))
                # Update any NULL values to 0 (False)
                conn.execute(text("UPDATE procore_submittals SET was_multiple_assignees = 0 WHERE was_multiple_assignees IS NULL"))
                print("✓ Successfully added 'was_multiple_assignees' column with default FALSE.")
                print("⚠ Note: SQLite uses INTEGER for boolean. All existing rows have been set to 0 (False).")

        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error: {exc}")
        return False
    except Exception as exc:
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add was_multiple_assignees column to procore_submittals table.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

