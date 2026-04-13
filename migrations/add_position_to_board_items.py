"""
Add the position column to the board_items table for manual card ordering.

Usage:
    python migrations/add_position_to_board_items.py

The script is idempotent and safe to run multiple times. It inspects the current
schema before attempting to alter the table, then backfills existing rows with
per-column positions ordered by updated_at DESC.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

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
            return value.replace("postgres://", "postgresql://", 1)

        if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
            return value

        return normalize_sqlite_path(value)

    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a given column exists on the specified table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def migrate(database_url: str = None) -> bool:
    """Perform the migration, adding position to board_items if needed."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)

    try:
        if column_exists(engine, "board_items", "position"):
            print("✓ Column 'position' already exists on 'board_items'. Nothing to do.")
            return True

        print("Adding column 'position' to 'board_items' table...")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE board_items ADD COLUMN position INTEGER"))

        if not column_exists(engine, "board_items", "position"):
            print("✗ Column addition did not succeed. Please verify manually.")
            return False

        print("✓ Successfully added 'position' column.")

        # Backfill per-column positions using a window function
        print("Backfilling positions per column (ordered by updated_at DESC)...")
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE board_items SET position = (
                    SELECT sub.rn FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (PARTITION BY status ORDER BY updated_at DESC) - 1 AS rn
                        FROM board_items
                    ) sub
                    WHERE sub.id = board_items.id
                )
            """))
        print("✓ Positions backfilled.")

        # Add composite index for fast per-column ordering queries
        print("Adding composite index on (status, position)...")
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_board_items_status_position
                    ON board_items (status, position)
            """))
        print("✓ Index created.")

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
    parser = argparse.ArgumentParser(description="Add position column to board_items table.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
