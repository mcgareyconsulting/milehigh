"""
Remove the X/O status fields (cut_start, fitup_comp, welded, paint_comp, ship) from the jobs table.

Usage:
    python migrations/remove_xo_fields_from_jobs.py

The script is idempotent and safe to run multiple times. It checks for column existence
before attempting to drop columns.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

# Add parent directory to path to import app modules
sys.path.insert(0, ROOT_DIR)

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


def migrate(database_url: str = None) -> bool:
    """Perform the migration, removing X/O fields from jobs table."""
    # Import app and models
    from app import create_app
    from app.models import db
    
    app = create_app()
    
    with app.app_context():
        try:
            # Use db.engine from app context to ensure same connection
            engine = db.engine
            
            # X/O fields to remove
            xo_fields = ['cut_start', 'fitup_comp', 'welded', 'paint_comp', 'ship']
            
            # Check which columns exist
            existing_fields = []
            for field in xo_fields:
                if column_exists(engine, "jobs", field):
                    existing_fields.append(field)
            
            if not existing_fields:
                print("✓ All X/O fields have already been removed from 'jobs' table.")
                return True
            
            print(f"Removing X/O fields from 'jobs' table: {', '.join(existing_fields)}")
            
            # Determine database type
            db_url_lower = str(db.engine.url).lower()
            is_sqlite = "sqlite" in db_url_lower
            is_postgres = "postgresql" in db_url_lower or "postgres" in db_url_lower
            
            with db.engine.begin() as conn:
                for field in existing_fields:
                    try:
                        if is_sqlite:
                            # SQLite doesn't support DROP COLUMN directly in older versions
                            # For SQLite 3.35.0+, we can use ALTER TABLE DROP COLUMN
                            # For older versions, we'd need to recreate the table
                            # Let's try the modern approach first
                            conn.execute(text(f"ALTER TABLE jobs DROP COLUMN {field}"))
                        elif is_postgres:
                            conn.execute(text(f"ALTER TABLE jobs DROP COLUMN IF EXISTS {field}"))
                        else:
                            # MySQL/MariaDB
                            conn.execute(text(f"ALTER TABLE jobs DROP COLUMN {field}"))
                        print(f"  ✓ Removed column '{field}'")
                    except Exception as e:
                        # If SQLite doesn't support DROP COLUMN, provide helpful error
                        if is_sqlite and "DROP COLUMN" in str(e).upper():
                            print(f"  ✗ Error removing '{field}': SQLite version may not support DROP COLUMN.")
                            print(f"    You may need to upgrade SQLite to 3.35.0+ or recreate the table manually.")
                            return False
                        else:
                            print(f"  ✗ Error removing '{field}': {e}")
                            return False
            
            # Verify columns were removed
            remaining_fields = []
            for field in xo_fields:
                if column_exists(engine, "jobs", field):
                    remaining_fields.append(field)
            
            if remaining_fields:
                print(f"✗ Warning: Some columns could not be removed: {', '.join(remaining_fields)}")
                return False
            
            print("✓ Successfully removed all X/O fields from 'jobs' table.")
            return True

        except (OperationalError, ProgrammingError) as exc:
            print(f"✗ Database error: {exc}")
            db.session.rollback()
            return False
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"✗ Unexpected error: {exc}")
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove X/O fields from jobs table.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

