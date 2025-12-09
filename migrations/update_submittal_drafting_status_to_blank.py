"""
Update all submittal_drafting_status values to blank placeholder.

This migration sets all existing submittal_drafting_status values to an empty string ''
to serve as a blank placeholder, allowing users to start with a blank status.

Usage:
    python migrations/update_submittal_drafting_status_to_blank.py
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


def table_exists(engine, table_name: str) -> bool:
    """Check if a table exists."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a given column exists on the specified table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def migrate(database_url: str = None) -> bool:
    """Perform the migration, updating all submittal_drafting_status values to blank."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)

    try:
        if not table_exists(engine, "procore_submittals"):
            print("✗ Table 'procore_submittals' does not exist. Nothing to do.")
            return False

        if not column_exists(engine, "procore_submittals", "submittal_drafting_status"):
            print("✗ Column 'submittal_drafting_status' does not exist. Nothing to do.")
            return False

        # Start transaction
        with engine.begin() as conn:
            # Count rows that will be updated
            result = conn.execute(text("SELECT COUNT(*) FROM procore_submittals"))
            total_count = result.scalar()
            
            if total_count == 0:
                print("✓ No rows to update. Nothing to do.")
                return True

            print(f"Found {total_count} rows in procore_submittals table.")
            print("Updating all submittal_drafting_status values to blank placeholder ('')...")
            
            # Update all rows to use empty string as blank placeholder
            result = conn.execute(text("""
                UPDATE procore_submittals 
                SET submittal_drafting_status = ''
            """))
            
            updated_count = result.rowcount
            print(f"✓ Successfully updated {updated_count} rows to use blank placeholder for submittal_drafting_status.")

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
    parser = argparse.ArgumentParser(description="Update all submittal_drafting_status values to blank placeholder.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

