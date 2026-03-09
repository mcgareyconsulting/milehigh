"""
Add project_managers table and map-related columns to the jobs table.

Changes:
  - CREATE TABLE project_managers (id, name, color)
  - ALTER TABLE jobs ADD COLUMN address
  - ALTER TABLE jobs ADD COLUMN latitude
  - ALTER TABLE jobs ADD COLUMN longitude
  - ALTER TABLE jobs ADD COLUMN radius_meters
  - ALTER TABLE jobs ADD COLUMN pm_id  (FK to project_managers.id on Postgres)
  - ALTER TABLE jobs ADD COLUMN geofence_geojson

The script is idempotent — safe to run multiple times.

Usage:
    python migrations/add_jobsite_map_columns.py
    python migrations/add_jobsite_map_columns.py --database-url postgresql://...
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url: str = None) -> str:
    candidates = [
        cli_url,
        os.environ.get("SANDBOX_DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
        os.environ.get("DATABASE_URL"),
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


def is_postgresql(engine) -> bool:
    return engine.dialect.name == "postgresql"


def table_exists(engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def column_exists(engine, table_name: str, column_name: str) -> bool:
    if not table_exists(engine, table_name):
        return False
    return any(col["name"] == column_name for col in inspect(engine).get_columns(table_name))


def add_column_if_missing(conn, engine, table: str, column: str, definition: str) -> None:
    if column_exists(engine, table, column):
        print(f"✓ Column '{column}' already exists on '{table}'.")
    else:
        print(f"Adding column '{column}' to '{table}'...")
        conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {column} {definition}'))
        print(f"✓ Added '{column}'.")


# ---------------------------------------------------------------------------
# Migration steps (each runs in its own transaction)
# ---------------------------------------------------------------------------

def create_project_managers_table(engine) -> None:
    if table_exists(engine, "project_managers"):
        print("✓ Table 'project_managers' already exists.")
        return

    print("Creating table 'project_managers'...")
    with engine.begin() as conn:
        if is_postgresql(engine):
            conn.execute(text("""
                CREATE TABLE project_managers (
                    id   SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    color VARCHAR(50) NOT NULL DEFAULT '#888888'
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE project_managers (
                    id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    name  VARCHAR(255) NOT NULL,
                    color VARCHAR(50)  NOT NULL DEFAULT '#888888'
                )
            """))
    print("✓ Created 'project_managers'.")


def add_jobs_columns(engine) -> None:
    """Add map-related columns to the jobs table, one transaction per column."""
    pg = is_postgresql(engine)

    columns = [
        ("address",          "VARCHAR(500)"),
        ("latitude",         "DOUBLE PRECISION" if pg else "REAL"),
        ("longitude",        "DOUBLE PRECISION" if pg else "REAL"),
        ("radius_meters",    "DOUBLE PRECISION" if pg else "REAL"),
        ("pm_id",            "INTEGER"),
        ("geofence_geojson", "JSON" if pg else "TEXT"),
    ]

    for col_name, col_def in columns:
        with engine.begin() as conn:
            add_column_if_missing(conn, engine, "jobs", col_name, col_def)

    # Add FK constraint on Postgres (SQLite doesn't enforce FKs at DDL level)
    if pg:
        _add_pm_id_fk_if_missing(engine)


def _add_pm_id_fk_if_missing(engine) -> None:
    """Add FK constraint jobs.pm_id → project_managers.id on Postgres if not present."""
    constraint_name = "fk_jobs_pm_id"
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT 1
            FROM   information_schema.table_constraints
            WHERE  constraint_name = :name
            AND    table_name      = 'jobs'
        """), {"name": constraint_name}).fetchone()

        if result:
            print(f"✓ FK constraint '{constraint_name}' already exists.")
            return

        print(f"Adding FK constraint '{constraint_name}'...")
        conn.execute(text(f"""
            ALTER TABLE jobs
            ADD CONSTRAINT {constraint_name}
            FOREIGN KEY (pm_id) REFERENCES project_managers(id)
        """))
        print(f"✓ Added FK constraint '{constraint_name}'.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def migrate(database_url: str = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to: {db_url}\n")

    connect_args = {}
    if "postgresql" in db_url.lower():
        connect_args["connect_timeout"] = 10

    engine = create_engine(db_url, connect_args=connect_args)

    try:
        create_project_managers_table(engine)
        add_jobs_columns(engine)
        print("\n✓ Migration completed successfully.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"\n✗ Database error: {exc}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as exc:
        print(f"\n✗ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add project_managers table and map columns to jobs table."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()
    sys.exit(0 if migrate(args.database_url) else 1)
