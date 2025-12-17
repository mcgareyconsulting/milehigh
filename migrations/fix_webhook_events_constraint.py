"""
Fix procore_webhook_events table by removing old unique constraint on resource_id.

This migration fixes the issue where the old unique constraint on resource_id
wasn't properly removed. It handles SQLite's implicit unique constraints.

Usage:
    python migrations/fix_webhook_events_constraint.py
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


def table_exists(engine, table_name: str) -> bool:
    """Check if a table exists."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def migrate(database_url: str = None) -> bool:
    """Fix the unique constraint issue."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)

    try:
        if not table_exists(engine, "procore_webhook_events"):
            print("✗ Table 'procore_webhook_events' does not exist. Nothing to do.")
            return False

        db_url_lower = str(db_url).lower()
        is_sqlite = "sqlite" in db_url_lower

        with engine.begin() as conn:
            if is_sqlite:
                # For SQLite, we need to check sqlite_master for the table definition
                # and recreate the table without the old unique constraint
                print("Checking SQLite table structure...")
                
                # Get the current table schema
                result = conn.execute(text("""
                    SELECT sql FROM sqlite_master 
                    WHERE type='table' AND name='procore_webhook_events'
                """))
                table_sql = result.fetchone()
                
                if table_sql and table_sql[0]:
                    table_def = table_sql[0]
                    print(f"Current table definition found.")
                    
                    # Check if resource_id has a unique constraint in the definition
                    # This could be: UNIQUE (resource_id) as a table constraint
                    # or resource_id INTEGER UNIQUE as a column constraint
                    import re
                    has_old_constraint = False
                    
                    # Check for table-level constraint: UNIQUE (resource_id)
                    if re.search(r'UNIQUE\s*\(\s*resource_id\s*\)', table_def, re.IGNORECASE):
                        has_old_constraint = True
                        print("Found table-level UNIQUE constraint on resource_id.")
                    # Check for column-level constraint: resource_id INTEGER UNIQUE
                    elif re.search(r'resource_id\s+\w+\s+UNIQUE', table_def, re.IGNORECASE):
                        has_old_constraint = True
                        print("Found column-level UNIQUE constraint on resource_id.")
                    
                    if has_old_constraint:
                        print("Recreating table without old unique constraint...")
                        
                        # Step 1: Create new table without the old constraint
                        print("Creating new table structure...")
                        conn.execute(text("""
                            CREATE TABLE procore_webhook_events_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                resource_id INTEGER NOT NULL,
                                project_id INTEGER NOT NULL,
                                event_type VARCHAR(50) NOT NULL,
                                last_seen DATETIME NOT NULL,
                                UNIQUE(resource_id, project_id, event_type)
                            )
                        """))
                        
                        # Step 2: Copy data (handle case where event_type might not exist yet)
                        print("Copying data to new table...")
                        try:
                            conn.execute(text("""
                                INSERT INTO procore_webhook_events_new 
                                (id, resource_id, project_id, event_type, last_seen)
                                SELECT id, resource_id, project_id, 
                                       COALESCE(event_type, 'update') as event_type,
                                       last_seen
                                FROM procore_webhook_events
                            """))
                        except Exception as e:
                            # If event_type column doesn't exist, add it first
                            print(f"  Note: {e}")
                            print("  Adding event_type column first...")
                            try:
                                conn.execute(text("""
                                    ALTER TABLE procore_webhook_events 
                                    ADD COLUMN event_type VARCHAR(50) NOT NULL DEFAULT 'update'
                                """))
                                # Update any NULL values
                                conn.execute(text("""
                                    UPDATE procore_webhook_events 
                                    SET event_type = 'update' 
                                    WHERE event_type IS NULL
                                """))
                                # Now copy data
                                conn.execute(text("""
                                    INSERT INTO procore_webhook_events_new 
                                    (id, resource_id, project_id, event_type, last_seen)
                                    SELECT id, resource_id, project_id, event_type, last_seen
                                    FROM procore_webhook_events
                                """))
                            except Exception as copy_error:
                                print(f"  Error copying data: {copy_error}")
                                # Drop the new table
                                conn.execute(text("DROP TABLE IF EXISTS procore_webhook_events_new"))
                                raise
                        
                        # Step 3: Drop old table
                        print("Dropping old table...")
                        conn.execute(text("DROP TABLE procore_webhook_events"))
                        
                        # Step 4: Rename new table
                        print("Renaming new table...")
                        conn.execute(text("ALTER TABLE procore_webhook_events_new RENAME TO procore_webhook_events"))
                        
                        print("✓ Successfully recreated table without old unique constraint.")
                    else:
                        print("No unique constraint found on resource_id.")
                        # Check if we need to add event_type column
                        inspector = inspect(engine)
                        columns = inspector.get_columns("procore_webhook_events")
                        has_event_type = any(col["name"] == "event_type" for col in columns)
                        
                        if not has_event_type:
                            print("Adding event_type column...")
                            conn.execute(text("""
                                ALTER TABLE procore_webhook_events 
                                ADD COLUMN event_type VARCHAR(50) NOT NULL DEFAULT 'update'
                            """))
                            conn.execute(text("""
                                UPDATE procore_webhook_events 
                                SET event_type = 'update' 
                                WHERE event_type IS NULL
                            """))
                        
                        # Ensure composite unique constraint exists
                        indexes = inspector.get_indexes("procore_webhook_events")
                        has_composite = any(
                            idx.get("name") == "_procore_webhook_unique" and idx.get("unique", False)
                            for idx in indexes
                        )
                        
                        if not has_composite:
                            print("Adding composite unique constraint...")
                            conn.execute(text("""
                                CREATE UNIQUE INDEX IF NOT EXISTS _procore_webhook_unique 
                                ON procore_webhook_events(resource_id, project_id, event_type)
                            """))
                else:
                    print("Could not find table definition in sqlite_master.")
                    
            else:
                # PostgreSQL: Try to find and drop the constraint
                print("Checking PostgreSQL constraints...")
                inspector = inspect(engine)
                constraints = inspector.get_unique_constraints("procore_webhook_events")
                
                old_constraint = None
                for constraint in constraints:
                    if len(constraint["column_names"]) == 1 and constraint["column_names"][0] == "resource_id":
                        old_constraint = constraint["name"]
                        break
                
                if old_constraint:
                    print(f"Removing old unique constraint '{old_constraint}'...")
                    conn.execute(text(f"ALTER TABLE procore_webhook_events DROP CONSTRAINT IF EXISTS {old_constraint}"))
                    print(f"✓ Removed old constraint.")
                else:
                    print("No old unique constraint found on resource_id.")
                
                # Ensure composite constraint exists
                has_composite = any(
                    c["name"] == "_procore_webhook_unique" 
                    for c in inspector.get_unique_constraints("procore_webhook_events")
                )
                
                if not has_composite:
                    print("Adding composite unique constraint...")
                    conn.execute(text("""
                        ALTER TABLE procore_webhook_events
                        ADD CONSTRAINT _procore_webhook_unique 
                        UNIQUE (resource_id, project_id, event_type)
                    """))

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
        description="Fix unique constraint on procore_webhook_events table."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
