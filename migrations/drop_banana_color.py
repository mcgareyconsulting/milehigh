"""
Drop the banana_color column from the releases table.

Background:
    banana_color was a free-form urgency string (e.g. red/yellow) shown on the
    Job Log before the stage-driven banana progress indicator replaced it.
    The column was removed from the Releases ORM model in PR #191; this
    migration drops the now-orphaned column from the database.

Usage:
    python migrations/drop_banana_color.py --dry-run
    python migrations/drop_banana_color.py

The script is idempotent and safe to run multiple times.
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

sys.path.insert(0, ROOT_DIR)

load_dotenv()


TABLE = "releases"
COLUMN = "banana_color"


def column_exists(engine, table: str, column: str) -> bool:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return False
    return any(col["name"] == column for col in insp.get_columns(table))


def migrate(database_url: str, dry_run: bool = False) -> bool:
    engine = create_engine(database_url)
    try:
        if not column_exists(engine, TABLE, COLUMN):
            print(f"✓ Column '{COLUMN}' is already absent from '{TABLE}'. Nothing to do.")
            return True

        print(f"Found column '{COLUMN}' on '{TABLE}'.")
        if dry_run:
            print(f"[dry-run] Would execute: ALTER TABLE {TABLE} DROP COLUMN {COLUMN}")
            return True

        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN}"))

        if column_exists(engine, TABLE, COLUMN):
            print(f"✗ Column '{COLUMN}' still present after DROP — investigate.")
            return False

        print(f"✓ Dropped column '{COLUMN}' from '{TABLE}'.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error: {exc}")
        return False
    except Exception as exc:
        print(f"✗ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Drop banana_color column from the releases table."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without committing.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}"),
        help="SQLAlchemy database URL (defaults to $DATABASE_URL or local SQLite).",
    )
    args = parser.parse_args()

    success = migrate(database_url=args.database_url, dry_run=args.dry_run)
    sys.exit(0 if success else 1)
