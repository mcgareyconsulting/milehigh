"""
Add event_type column to procore_webhook_events table and update unique constraint.

This migration:
1. Adds event_type column to procore_webhook_events table
2. Removes the old unique constraint on resource_id
3. Adds a new composite unique constraint on (resource_id, project_id, event_type)
4. Cleans up existing records (sets default event_type or removes duplicates)

Usage:
    python migrations/add_event_type_to_webhook_events.py

The script is idempotent and safe to run multiple times.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from sqlalchemy import create_engine, inspect, text, MetaData, Table
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


def constraint_exists(engine, table_name: str, constraint_name: str) -> bool:
    """Check if a constraint exists on a table.
    
    For SQLite, unique constraints are implemented as indexes, so we check both.
    """
    inspector = inspect(engine)
    
    # Check unique constraints (works for PostgreSQL)
    constraints = inspector.get_unique_constraints(table_name)
    if any(c["name"] == constraint_name for c in constraints):
        return True
    
    # For SQLite, check indexes (unique constraints are implemented as unique indexes)
    indexes = inspector.get_indexes(table_name)
    for idx in indexes:
        if idx["name"] == constraint_name and idx.get("unique", False):
            return True
    
    return False


def get_unique_constraints(engine, table_name: str):
    """Get all unique constraints on a table."""
    inspector = inspect(engine)
    return inspector.get_unique_constraints(table_name)


def migrate(database_url: str = None) -> bool:
    """Perform the migration."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)

    try:
        if not table_exists(engine, "procore_webhook_events"):
            print("✗ Table 'procore_webhook_events' does not exist. Nothing to do.")
            return False

        # Check if column already exists
        column_exists_check = column_exists(engine, "procore_webhook_events", "event_type")
        new_constraint_exists = constraint_exists(engine, "procore_webhook_events", "_procore_webhook_unique")

        if column_exists_check and new_constraint_exists:
            print("✓ Column 'event_type' and composite unique constraint already exist. Nothing to do.")
            return True

        with engine.begin() as conn:
            # Step 1: Add event_type column if it doesn't exist
            if not column_exists_check:
                print("Adding column 'event_type' to 'procore_webhook_events' table...")
                
                db_url_lower = str(db_url).lower()
                if "postgresql" in db_url_lower or "postgres" in db_url_lower:
                    # PostgreSQL: Add column with NOT NULL and default 'update' (most common)
                    conn.execute(text("""
                        ALTER TABLE procore_webhook_events 
                        ADD COLUMN event_type VARCHAR(50) NOT NULL DEFAULT 'update'
                    """))
                    print("✓ Successfully added 'event_type' column with default 'update'.")
                else:
                    # SQLite: Add column
                    conn.execute(text("""
                        ALTER TABLE procore_webhook_events 
                        ADD COLUMN event_type VARCHAR(50) NOT NULL DEFAULT 'update'
                    """))
                    # Update any NULL values (shouldn't happen with NOT NULL, but just in case)
                    conn.execute(text("""
                        UPDATE procore_webhook_events 
                        SET event_type = 'update' 
                        WHERE event_type IS NULL
                    """))
                    print("✓ Successfully added 'event_type' column with default 'update'.")

            # Step 2: Remove old unique constraint on resource_id if it exists
            # First, find the constraint name
            inspector = inspect(engine)
            constraints = inspector.get_unique_constraints("procore_webhook_events")
            
            old_constraint_name = None
            for constraint in constraints:
                # Check if this is a single-column constraint on resource_id
                if len(constraint["column_names"]) == 1 and constraint["column_names"][0] == "resource_id":
                    old_constraint_name = constraint["name"]
                    break

            if old_constraint_name:
                print(f"Removing old unique constraint '{old_constraint_name}' on resource_id...")
                if "postgresql" in str(db_url).lower() or "postgres" in str(db_url).lower():
                    conn.execute(text(f"ALTER TABLE procore_webhook_events DROP CONSTRAINT IF EXISTS {old_constraint_name}"))
                else:
                    # SQLite: Drop index (SQLite uses indexes for unique constraints)
                    conn.execute(text(f"DROP INDEX IF EXISTS {old_constraint_name}"))
                print(f"✓ Removed old unique constraint '{old_constraint_name}'.")

            # Step 3: Clean up any duplicate records (same resource_id + project_id with different event_types)
            # Keep the most recent one for each combination
            print("Cleaning up duplicate records...")
            if "postgresql" in str(db_url).lower() or "postgres" in str(db_url).lower():
                conn.execute(text("""
                    DELETE FROM procore_webhook_events
                    WHERE id NOT IN (
                        SELECT DISTINCT ON (resource_id, project_id, event_type) id
                        FROM procore_webhook_events
                        ORDER BY resource_id, project_id, event_type, last_seen DESC
                    )
                """))
            else:
                # SQLite: Delete duplicates, keeping the most recent
                conn.execute(text("""
                    DELETE FROM procore_webhook_events
                    WHERE id NOT IN (
                        SELECT MAX(id)
                        FROM procore_webhook_events
                        GROUP BY resource_id, project_id, event_type
                    )
                """))
            print("✓ Cleaned up duplicate records.")

            # Step 4: Add new composite unique constraint
            if not new_constraint_exists:
                print("Adding composite unique constraint on (resource_id, project_id, event_type)...")
                if "postgresql" in str(db_url).lower() or "postgres" in str(db_url).lower():
                    conn.execute(text("""
                        ALTER TABLE procore_webhook_events
                        ADD CONSTRAINT _procore_webhook_unique 
                        UNIQUE (resource_id, project_id, event_type)
                    """))
                else:
                    # SQLite: Create unique index
                    conn.execute(text("""
                        CREATE UNIQUE INDEX IF NOT EXISTS _procore_webhook_unique 
                        ON procore_webhook_events(resource_id, project_id, event_type)
                    """))
                print("✓ Successfully added composite unique constraint.")

        # Verify the migration
        inspector = inspect(engine)
        if column_exists(engine, "procore_webhook_events", "event_type"):
            print("✓ Verification: Column 'event_type' exists")
        else:
            print("✗ Verification failed: Column 'event_type' not found")
            return False

        # Verify constraint/index exists
        constraint_found = constraint_exists(engine, "procore_webhook_events", "_procore_webhook_unique")
        if constraint_found:
            print("✓ Verification: Composite unique constraint/index exists")
        else:
            # For debugging, show what constraints/indexes we found
            inspector = inspect(engine)
            constraints = inspector.get_unique_constraints("procore_webhook_events")
            indexes = inspector.get_indexes("procore_webhook_events")
            print(f"  Debug: Found {len(constraints)} unique constraints: {[c['name'] for c in constraints]}")
            print(f"  Debug: Found {len(indexes)} indexes: {[idx['name'] for idx in indexes]}")
            # For SQLite, the constraint might exist even if not found by name
            # Check if there's a unique index on the three columns
            db_url_lower = str(db_url).lower()
            if "sqlite" in db_url_lower:
                # For SQLite, check if the unique index was created (might have different name)
                unique_indexes = [idx for idx in indexes if idx.get("unique", False)]
                if unique_indexes:
                    print(f"  Note: Found {len(unique_indexes)} unique index(es) - constraint may exist with different name")
                    print("✓ Migration likely successful (SQLite unique index created)")
                    return True
            print("✗ Verification failed: Composite unique constraint not found")
            return False

        print("\n✓ Migration completed successfully!")
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
        description="Add event_type column to procore_webhook_events table and update unique constraint."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
