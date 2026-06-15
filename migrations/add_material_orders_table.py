"""
Create the material_orders table.

Stores parts/materials ordered from suppliers (parsed from order emails
forwarded to bb@mhmw.com), tagged to a job-release by value. See the
MaterialOrder model in app/models.py.

Usage:
    python migrations/add_material_orders_table.py
    python migrations/add_material_orders_table.py --database-url postgresql://...

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

TABLE = "material_orders"


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


def _create_table(conn, is_postgres):
    serial = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    conn.execute(text(
        f"""
        CREATE TABLE {TABLE} (
            id {serial},
            job INTEGER,
            release VARCHAR(16),
            supplier VARCHAR(128),
            supplier_contact VARCHAR(255),
            po_number VARCHAR(64),
            description VARCHAR(512),
            quantity FLOAT,
            unit VARCHAR(32),
            profile VARCHAR(64),
            gauge VARCHAR(32),
            finish VARCHAR(64),
            dimension VARCHAR(64),
            status VARCHAR(16) NOT NULL DEFAULT 'ordered',
            ordered_at DATE,
            received_at DATE,
            source VARCHAR(64),
            source_record_id INTEGER,
            line_index INTEGER NOT NULL DEFAULT 0,
            raw_line VARCHAR(512),
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            CONSTRAINT uq_material_order_source_line UNIQUE (source_record_id, line_index)
        )
        """
    ))
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS ix_material_orders_job_release "
        f"ON {TABLE} (job, release)"
    ))
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS ix_material_orders_status ON {TABLE} (status)"
    ))


def migrate(database_url: str = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)
    is_postgres = engine.dialect.name == "postgresql"

    try:
        if inspect(engine).has_table(TABLE):
            print(f"✓ Table '{TABLE}' already exists. Nothing to do.")
            return True

        print(f"Creating table '{TABLE}'...")
        with engine.begin() as conn:
            _create_table(conn, is_postgres)

        if inspect(engine).has_table(TABLE):
            print(f"✓ Successfully created table '{TABLE}'.")
            return True
        print("✗ Table creation did not succeed. Please verify manually.")
        return False

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error while creating table: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the material_orders table.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
