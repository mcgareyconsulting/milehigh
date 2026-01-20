"""
Migrate jobs table schema and data from local SQLite to sandbox database.

This script:
1. Connects to local SQLite database (source)
2. Connects to sandbox database (target)
3. Compares schemas and adds missing columns if needed
4. Transfers all job data to sandbox database
5. Handles conflicts (e.g., duplicate job-release combinations)

Usage:
    python migrations/migrate_jobs_to_sandbox.py [--dry-run] [--skip-schema] [--clear-existing]

Options:
    --dry-run: Show what would be done without making changes
    --skip-schema: Skip schema migration (assume schema is already correct)
    --clear-existing: Clear existing jobs data in sandbox before migration
"""

import argparse
import os
import sys
from typing import Dict, List, Set, Tuple, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text, MetaData, Table
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.engine import Engine
import pandas as pd

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


def get_local_database_url() -> str:
    """Get the local SQLite database URL."""
    candidates = [
        os.environ.get("LOCAL_DATABASE_URL"),
        os.environ.get("DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
    ]

    for value in candidates:
        if not value:
            continue

        value = value.strip()
        if value.startswith("sqlite://"):
            return value

        # Treat as filesystem path to SQLite DB
        return normalize_sqlite_path(value)

    # Fall back to default SQLite file
    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def get_sandbox_database_url() -> str:
    """Get the sandbox database URL."""
    database_url = os.environ.get("SANDBOX_DATABASE_URL")
    if not database_url:
        raise ValueError(
            "SANDBOX_DATABASE_URL must be set. "
            "Please set it in your .env file or environment variables."
        )
    
    # Convert postgres:// to postgresql:// if needed
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    return database_url


def get_table_schema(engine: Engine, table_name: str) -> Dict[str, Dict]:
    """Get the schema of a table as a dictionary mapping column names to column info."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    
    schema = {}
    for col in columns:
        schema[col["name"]] = {
            "type": col["type"],
            "nullable": col["nullable"],
            "default": col.get("default"),
            "autoincrement": col.get("autoincrement", False),
            "primary_key": col.get("primary_key", False),
        }
    
    return schema


def get_primary_key_columns(engine: Engine, table_name: str) -> List[str]:
    """Get the primary key column names for a table."""
    inspector = inspect(engine)
    pk_constraint = inspector.get_pk_constraint(table_name)
    return pk_constraint.get("constrained_columns", [])


def get_unique_constraints(engine: Engine, table_name: str) -> List[List[str]]:
    """Get unique constraint column groups for a table."""
    inspector = inspect(engine)
    unique_constraints = inspector.get_unique_constraints(table_name)
    return [uc["column_names"] for uc in unique_constraints]


def column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def get_sqlalchemy_type_string(sqlalchemy_type) -> str:
    """Convert SQLAlchemy type to a string representation for ALTER TABLE."""
    type_str = str(sqlalchemy_type)
    
    # Handle common types
    if "VARCHAR" in type_str.upper() or "STRING" in type_str.upper():
        # Extract length if present
        if "(" in type_str:
            return type_str.upper()
        return "VARCHAR(255)"
    elif "INTEGER" in type_str.upper() or "INT" in type_str.upper():
        return "INTEGER"
    elif "FLOAT" in type_str.upper() or "REAL" in type_str.upper():
        return "REAL"
    elif "DATE" in type_str.upper():
        return "DATE"
    elif "DATETIME" in type_str.upper() or "TIMESTAMP" in type_str.upper():
        return "TIMESTAMP"
    elif "BOOLEAN" in type_str.upper() or "BOOL" in type_str.upper():
        return "BOOLEAN"
    elif "TEXT" in type_str.upper():
        return "TEXT"
    
    return type_str.upper()


def migrate_schema(
    source_engine: Engine,
    target_engine: Engine,
    table_name: str,
    dry_run: bool = False
) -> Tuple[bool, List[str]]:
    """
    Migrate schema from source to target database.
    Returns (success, list of changes made).
    """
    changes = []
    
    # Check if table exists in target
    if not table_exists(target_engine, table_name):
        print(f"✗ Table '{table_name}' does not exist in target database.")
        print("  Please create the table first using SQLAlchemy models or another migration.")
        return False, changes
    
    # Get schemas
    source_schema = get_table_schema(source_engine, table_name)
    target_schema = get_table_schema(target_engine, table_name)
    
    # Find missing columns in target
    missing_columns = set(source_schema.keys()) - set(target_schema.keys())
    
    if not missing_columns:
        print("✓ Schema is already in sync. No changes needed.")
        return True, changes
    
    print(f"Found {len(missing_columns)} missing columns in target database:")
    for col_name in sorted(missing_columns):
        col_info = source_schema[col_name]
        col_type = get_sqlalchemy_type_string(col_info["type"])
        nullable = "NULL" if col_info["nullable"] else "NOT NULL"
        
        print(f"  - {col_name}: {col_type} {nullable}")
        
        if not dry_run:
            try:
                with target_engine.begin() as conn:
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                    if not col_info["nullable"]:
                        alter_sql += " NOT NULL"
                    # Note: We can't easily set defaults for existing rows, so we'll allow NULL
                    # and update them later if needed
                    conn.execute(text(alter_sql))
                changes.append(f"Added column {col_name}")
                print(f"    ✓ Added column '{col_name}'")
            except Exception as e:
                print(f"    ✗ Failed to add column '{col_name}': {e}")
                return False, changes
        else:
            changes.append(f"Would add column {col_name}")
    
    return True, changes


def get_existing_job_ids(target_engine: Engine) -> Set[Tuple[int, str]]:
    """Get set of (job, release) tuples that already exist in target database."""
    try:
        with target_engine.connect() as conn:
            result = conn.execute(text("SELECT job, release FROM jobs"))
            return {(row[0], row[1]) for row in result}
    except Exception as e:
        print(f"Warning: Could not fetch existing jobs: {e}")
        return set()


def transfer_data(
    source_engine: Engine,
    target_engine: Engine,
    table_name: str,
    dry_run: bool = False,
    clear_existing: bool = False,
    skip_conflicts: bool = True
) -> Tuple[bool, Dict[str, int]]:
    """
    Transfer data from source to target database.
    Returns (success, stats dict).
    """
    stats = {
        "total_source": 0,
        "transferred": 0,
        "skipped": 0,
        "errors": 0
    }
    
    try:
        # Read all data from source
        print(f"Reading data from source database...")
        df = pd.read_sql_table(table_name, source_engine)
        stats["total_source"] = len(df)
        
        if stats["total_source"] == 0:
            print("No data to transfer.")
            return True, stats
        
        print(f"Found {stats['total_source']} rows in source database.")
        
        # Clear existing data if requested
        if clear_existing:
            if dry_run:
                print("  [DRY RUN] Would clear existing jobs data")
            else:
                print("Clearing existing jobs data in target database...")
                with target_engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM {table_name}"))
                print("✓ Cleared existing data.")
        
        # Get existing job IDs if not clearing
        existing_jobs = set()
        if not clear_existing:
            existing_jobs = get_existing_job_ids(target_engine)
            if existing_jobs:
                print(f"Found {len(existing_jobs)} existing jobs in target database.")
        
        # Prepare data for insertion
        # Remove rows that already exist (if not clearing)
        if not clear_existing and existing_jobs:
            initial_count = len(df)
            df = df[~df.apply(lambda row: (row['job'], row['release']) in existing_jobs, axis=1)]
            skipped = initial_count - len(df)
            stats["skipped"] = skipped
            if skipped > 0:
                print(f"Skipping {skipped} rows that already exist in target.")
        
        if len(df) == 0:
            print("No new data to transfer.")
            return True, stats
        
        print(f"Transferring {len(df)} rows to target database...")
        
        if dry_run:
            print(f"  [DRY RUN] Would transfer {len(df)} rows")
            stats["transferred"] = len(df)
            return True, stats
        
        # Transfer data in batches
        batch_size = 100
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(df))
            batch_df = df.iloc[start_idx:end_idx]
            
            try:
                # Use pandas to_sql with if_exists='append' to insert data
                batch_df.to_sql(
                    table_name,
                    target_engine,
                    if_exists='append',
                    index=False,
                    method='multi'  # Use multi-row insert for efficiency
                )
                stats["transferred"] += len(batch_df)
                print(f"  Transferred batch {batch_num + 1}/{total_batches} ({len(batch_df)} rows)")
            except Exception as e:
                print(f"  ✗ Error transferring batch {batch_num + 1}: {e}")
                stats["errors"] += len(batch_df)
                if not skip_conflicts:
                    return False, stats
        
        print(f"✓ Successfully transferred {stats['transferred']} rows.")
        if stats["skipped"] > 0:
            print(f"  (Skipped {stats['skipped']} existing rows)")
        
        return True, stats
        
    except Exception as e:
        print(f"✗ Error during data transfer: {e}")
        import traceback
        traceback.print_exc()
        return False, stats


def migrate(
    dry_run: bool = False,
    skip_schema: bool = False,
    clear_existing: bool = False
) -> bool:
    """Perform the complete migration."""
    print("=" * 80)
    print("JOBS TABLE MIGRATION: Local SQLite → Sandbox Database")
    print("=" * 80)
    
    if dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")
    
    # Get database URLs
    try:
        local_url = get_local_database_url()
        sandbox_url = get_sandbox_database_url()
    except ValueError as e:
        print(f"✗ Configuration error: {e}")
        return False
    
    print(f"\nSource (Local): {local_url}")
    print(f"Target (Sandbox): {sandbox_url.split('@')[1] if '@' in sandbox_url else '***'}\n")
    
    # Create engines
    try:
        source_engine = create_engine(local_url, echo=False)
        target_engine = create_engine(sandbox_url, echo=False)
        
        # Test connections
        print("Testing database connections...")
        with source_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Source database connection successful")
        
        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Target database connection successful")
        
        # Check if jobs table exists in source
        if not table_exists(source_engine, "jobs"):
            print("✗ 'jobs' table does not exist in source database.")
            return False
        
        # Check if jobs table exists in target
        if not table_exists(target_engine, "jobs"):
            print("✗ 'jobs' table does not exist in target database.")
            print("  Please create the table first using SQLAlchemy models.")
            return False
        
        # Step 1: Migrate schema
        if not skip_schema:
            print("\n" + "=" * 80)
            print("STEP 1: Schema Migration")
            print("=" * 80)
            schema_success, schema_changes = migrate_schema(
                source_engine, target_engine, "jobs", dry_run=dry_run
            )
            if not schema_success:
                return False
        else:
            print("\nSkipping schema migration (--skip-schema flag set)")
        
        # Step 2: Transfer data
        print("\n" + "=" * 80)
        print("STEP 2: Data Transfer")
        print("=" * 80)
        data_success, stats = transfer_data(
            source_engine,
            target_engine,
            "jobs",
            dry_run=dry_run,
            clear_existing=clear_existing
        )
        
        if not data_success:
            return False
        
        # Summary
        print("\n" + "=" * 80)
        print("MIGRATION SUMMARY")
        print("=" * 80)
        print(f"Source rows: {stats['total_source']}")
        print(f"Transferred: {stats['transferred']}")
        print(f"Skipped (existing): {stats['skipped']}")
        if stats['errors'] > 0:
            print(f"Errors: {stats['errors']}")
        
        if dry_run:
            print("\n⚠ This was a DRY RUN - no changes were made")
        else:
            print("\n✓ Migration completed successfully!")
        
        return True
        
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'source_engine' in locals():
            source_engine.dispose()
        if 'target_engine' in locals():
            target_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate jobs table from local SQLite to sandbox database."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Skip schema migration (assume schema is already correct)"
    )
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Clear existing jobs data in sandbox before migration"
    )
    args = parser.parse_args()
    
    success = migrate(
        dry_run=args.dry_run,
        skip_schema=args.skip_schema,
        clear_existing=args.clear_existing
    )
    sys.exit(0 if success else 1)

