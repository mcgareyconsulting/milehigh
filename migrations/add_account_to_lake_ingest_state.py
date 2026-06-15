"""
Add the `account` column to lake_ingest_state and key it by (source, account).

Schema drift fix: lake_ingest_state was originally created keyed by `source`
alone (unique constraint lake_ingest_state_source_key). The model later gained
an `account` column (per-mailbox watermark) plus a (source, account) unique
constraint (uq_lake_ingest_source_account), but environments that already had
the table never picked up the additive change — so polls fail with
"column lake_ingest_state.account does not exist".

This migration:
  1. Adds the nullable `account` VARCHAR(255) column if missing.
  2. Drops the old source-only unique (lake_ingest_state_source_key) if present.
  3. Adds the (source, account) unique (uq_lake_ingest_source_account) if missing.

The watermark table is advisory (RawSourceRecord uniqueness guarantees
idempotency), so no data backfill is required. Constraint reconciliation is
Postgres-only; on SQLite the column add is sufficient (the in-memory test DB is
built straight from the models).

Usage:
    python migrations/add_account_to_lake_ingest_state.py
    python migrations/add_account_to_lake_ingest_state.py --database-url postgresql://...

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

load_dotenv()

TABLE = "lake_ingest_state"
OLD_UNIQUE = "lake_ingest_state_source_key"
NEW_UNIQUE = "uq_lake_ingest_source_account"


def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def _coerce_url(value: str) -> str:
    value = value.strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
        return value
    return normalize_sqlite_path(value)


def infer_database_url(cli_url: str = None) -> str:
    """Mirror app/db_config.py: ENVIRONMENT selects the authoritative URL."""
    if cli_url:
        return _coerce_url(cli_url)

    environment = (os.environ.get("ENVIRONMENT") or "local").strip().lower()

    if environment == "production":
        value = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not value:
            raise ValueError(
                "ENVIRONMENT=production but neither PRODUCTION_DATABASE_URL nor "
                "DATABASE_URL is set (refusing to guess; pass --database-url)."
            )
        return _coerce_url(value)

    if environment == "sandbox":
        value = os.environ.get("SANDBOX_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not value:
            raise ValueError(
                "ENVIRONMENT=sandbox but neither SANDBOX_DATABASE_URL nor "
                "DATABASE_URL is set (refusing to guess; pass --database-url)."
            )
        return _coerce_url(value)

    candidates = [
        os.environ.get("LOCAL_DATABASE_URL"),
        os.environ.get("DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
    ]
    for value in candidates:
        if value:
            return _coerce_url(value)

    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def column_exists(engine, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in inspect(engine).get_columns(table_name))


def unique_exists(engine, table_name: str, constraint_name: str) -> bool:
    insp = inspect(engine)
    names = {uc["name"] for uc in insp.get_unique_constraints(table_name)}
    names |= {ix["name"] for ix in insp.get_indexes(table_name) if ix.get("unique")}
    return constraint_name in names


def migrate(database_url: str = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)
    is_postgres = engine.dialect.name == "postgresql"

    try:
        if not inspect(engine).has_table(TABLE):
            print(f"✗ Table '{TABLE}' does not exist. Run add_lake_tables.py first.")
            return False

        # 1. Add the account column if missing.
        if column_exists(engine, TABLE, "account"):
            print("✓ Column 'account' already exists. Nothing to add.")
        else:
            print("Adding column 'account' to lake_ingest_state...")
            with engine.begin() as conn:
                if is_postgres:
                    conn.execute(text(
                        f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS account VARCHAR(255)"
                    ))
                else:
                    conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN account VARCHAR(255)"))
            print("✓ Column 'account' added.")

        # 2 & 3. Reconcile the unique constraint (Postgres only — SQLite can't
        # ALTER constraints, and its test DB is built from the models anyway).
        if is_postgres:
            with engine.begin() as conn:
                if unique_exists(engine, TABLE, OLD_UNIQUE):
                    print(f"Dropping old unique '{OLD_UNIQUE}' (source-only)...")
                    conn.execute(text(
                        f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OLD_UNIQUE}"
                    ))
                if unique_exists(engine, TABLE, NEW_UNIQUE):
                    print(f"✓ Unique '{NEW_UNIQUE}' already present.")
                else:
                    print(f"Adding unique '{NEW_UNIQUE}' on (source, account)...")
                    conn.execute(text(
                        f"ALTER TABLE {TABLE} ADD CONSTRAINT {NEW_UNIQUE} "
                        f"UNIQUE (source, account)"
                    ))
                    print(f"✓ Unique '{NEW_UNIQUE}' added.")
        else:
            print("• SQLite: skipping constraint reconciliation (built from models).")

        # Confirm the column landed.
        if column_exists(engine, TABLE, "account"):
            print("✓ Migration complete: lake_ingest_state.account is present.")
            return True
        print("✗ Column 'account' still missing after migration. Verify manually.")
        return False

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error during migration: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add account column + (source, account) unique to lake_ingest_state."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
