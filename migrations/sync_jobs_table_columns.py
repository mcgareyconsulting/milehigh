"""
Sync all columns from the Job model to the jobs table.

This migration ensures the local database has all columns that the Job model expects.
It's idempotent and safe to run multiple times.

Usage:
    python migrations/sync_jobs_table_columns.py
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
    if not inspector.has_table(table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def get_sqlite_type(sqlalchemy_type):
    """Convert SQLAlchemy type to SQLite type string."""
    type_str = str(sqlalchemy_type)
    
    # Handle common SQLAlchemy types
    if "VARCHAR" in type_str or "String" in type_str:
        # Extract length if present
        if "(" in type_str:
            length = type_str.split("(")[1].split(")")[0]
            return f"VARCHAR({length})"
        return "VARCHAR(255)"
    elif "Integer" in type_str:
        return "INTEGER"
    elif "Float" in type_str:
        return "REAL"
    elif "Boolean" in type_str:
        return "BOOLEAN"
    elif "Date" in type_str:
        return "DATE"
    elif "DateTime" in type_str:
        return "DATETIME"
    elif "Text" in type_str:
        return "TEXT"
    else:
        # Default fallback
        return "TEXT"


def migrate(database_url: str = None) -> bool:
    """Sync all Job model columns to the jobs table."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)

    try:
        inspector = inspect(engine)
        if not inspector.has_table("jobs"):
            print("✗ Table 'jobs' does not exist. Please create it first using db.create_all().")
            return False

        # Import the Job model to get column definitions
        sys.path.insert(0, ROOT_DIR)
        from app.models import Job

        # Get all columns from the model
        columns_to_add = []
        for column in Job.__table__.columns:
            col_name = column.name
            if not column_exists(engine, "jobs", col_name):
                # Skip primary key and auto-increment columns
                if column.primary_key:
                    continue
                
                sqlite_type = get_sqlite_type(column.type)
                nullable = "NULL" if column.nullable else "NOT NULL"
                
                # Handle default values
                default_clause = ""
                if column.default is not None:
                    if hasattr(column.default, 'arg'):
                        default_val = column.default.arg
                        if isinstance(default_val, str):
                            default_clause = f" DEFAULT '{default_val}'"
                        elif isinstance(default_val, (int, float)):
                            default_clause = f" DEFAULT {default_val}"
                        elif isinstance(default_val, bool):
                            default_clause = f" DEFAULT {1 if default_val else 0}"
                
                columns_to_add.append((col_name, sqlite_type, nullable, default_clause))
            else:
                print(f"✓ Column '{col_name}' already exists on 'jobs'.")

        if not columns_to_add:
            print("✓ All columns already exist on 'jobs'. Nothing to do.")
            return True

        print(f"\nAdding {len(columns_to_add)} missing column(s) to 'jobs' table...")
        with engine.begin() as conn:
            for col_name, col_type, nullable, default_clause in columns_to_add:
                print(f"  Adding column '{col_name}' ({col_type} {nullable}{default_clause})...")
                try:
                    conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type} {nullable}{default_clause}"))
                    print(f"    ✓ Successfully added '{col_name}'")
                except Exception as e:
                    print(f"    ✗ Failed to add '{col_name}': {e}")
                    return False

        # Re-check to confirm all columns were added
        print("\nVerifying column additions...")
        all_added = True
        for col_name, _, _, _ in columns_to_add:
            if column_exists(engine, "jobs", col_name):
                print(f"✓ Verified: '{col_name}' exists")
            else:
                print(f"✗ Column '{col_name}' addition did not succeed. Please verify manually.")
                all_added = False

        if all_added:
            print("\n✓ Migration completed successfully! All columns are now in sync.")
            return True

        print("\n✗ Some columns were not added. Please verify manually.")
        return False

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error while adding columns: {exc}")
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
        description="Sync all Job model columns to the jobs table."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

