"""
Add performance indexes to the releases and submittals tables.

Creates eight indexes that match the declarations in app/models.py:

  releases:
    idx_releases_last_updated_at_id  (last_updated_at, id)  -- cursor poll filter + ORDER BY
    idx_releases_archived_active     (is_archived, is_active) -- every list endpoint filter
    idx_releases_stage_group         (stage_group)
    idx_releases_stage               (stage)

  submittals:
    ix_submittals_status             (status)
    ix_submittals_ball_in_court      (ball_in_court)
    ix_submittals_project_number     (project_number)
    ix_submittals_order_number       (order_number)

Usage:
    python migrations/add_releases_submittals_indexes.py
    python migrations/add_releases_submittals_indexes.py --database-url postgresql://...

The script is idempotent and safe to run multiple times. It inspects the
current schema before creating each index and skips any that already exist.

Plain CREATE INDEX is fine at the current table sizes. If either table ever
nears ~1M rows, switch to CREATE INDEX CONCURRENTLY (Postgres) and run each
statement with an AUTOCOMMIT connection (CONCURRENTLY cannot run inside a
transaction block).
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

# (table, index_name, ordered columns) — names hardcoded identical to the
# declarations in app/models.py so new and existing databases converge.
INDEXES = [
    ("releases", "idx_releases_last_updated_at_id", ("last_updated_at", "id")),
    ("releases", "idx_releases_archived_active", ("is_archived", "is_active")),
    ("releases", "idx_releases_stage_group", ("stage_group",)),
    ("releases", "idx_releases_stage", ("stage",)),
    ("submittals", "ix_submittals_status", ("status",)),
    ("submittals", "ix_submittals_ball_in_court", ("ball_in_court",)),
    ("submittals", "ix_submittals_project_number", ("project_number",)),
    ("submittals", "ix_submittals_order_number", ("order_number",)),
]


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
        os.environ.get("SANDBOX_DATABASE_URL"),
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


def index_exists(engine, table_name: str, index_name: str) -> bool:
    """Check if a given index exists on the specified table."""
    inspector = inspect(engine)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a given column exists on the specified table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def table_exists(engine, table_name: str) -> bool:
    """Check if a given table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def migrate(database_url: str = None) -> bool:
    """Create the releases/submittals indexes that are missing."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)
    ok = True

    try:
        for table_name, index_name, columns in INDEXES:
            if not table_exists(engine, table_name):
                print(f"✗ Table '{table_name}' does not exist. Skipping '{index_name}'.")
                ok = False
                continue

            missing_cols = [c for c in columns if not column_exists(engine, table_name, c)]
            if missing_cols:
                print(
                    f"✗ Column(s) {missing_cols} missing on '{table_name}'. "
                    f"Skipping '{index_name}'."
                )
                ok = False
                continue

            if index_exists(engine, table_name, index_name):
                print(f"✓ Index '{index_name}' already exists on '{table_name}'. Nothing to do.")
                continue

            col_list = ", ".join(columns)
            print(f"Adding index '{index_name}' on {table_name} ({col_list})...")
            with engine.begin() as conn:
                conn.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({col_list})"))

            if index_exists(engine, table_name, index_name):
                print(f"✓ Successfully added index '{index_name}' to '{table_name}'.")
            else:
                print(f"✗ Index '{index_name}' creation did not succeed. Please verify manually.")
                ok = False

        return ok

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error while adding indexes: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add performance indexes to the releases and submittals tables."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
