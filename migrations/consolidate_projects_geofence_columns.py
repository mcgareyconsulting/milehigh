"""
Consolidate the projects.geometry and projects.geofence_geojson columns.

After this migration there is a single canonical column — `geofence_geojson` —
used by both the map renderer and the on-site location filter. The previous
split (where the regenerate-geofences endpoint wrote one column and
LocationService read the other) caused projects to render on the map but be
invisible to on-site filtering.

Steps (each in its own transaction so locks release immediately):
  1. Backfill: copy `geometry` into `geofence_geojson` for every row where
     geofence_geojson IS NULL (or stored as an empty value) but geometry has
     a usable value. No data loss.
  2. Drop the `geometry` column.

Idempotent: re-running after success is a no-op (the column is already gone
and there is nothing left to backfill).

Usage:
    python migrations/consolidate_projects_geofence_columns.py
    python migrations/consolidate_projects_geofence_columns.py --database-url postgresql://...
"""

import argparse
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url: Optional[str] = None) -> str:
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


def table_exists(engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def column_exists(engine, table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def is_postgresql(engine) -> bool:
    return engine.dialect.name == "postgresql"


def backfill_geofence_geojson(conn, engine) -> None:
    """Copy geometry into geofence_geojson where the latter is empty but the former isn't."""
    if not table_exists(engine, "projects"):
        print("✓ Table 'projects' does not exist; skipping backfill.")
        return
    if not column_exists(engine, "projects", "geometry"):
        print("✓ Column 'geometry' already dropped; nothing to backfill.")
        return
    if not column_exists(engine, "projects", "geofence_geojson"):
        # Should not happen, but if it does abort — operator must add the column first.
        raise RuntimeError(
            "projects.geofence_geojson does not exist; create it before running this migration."
        )

    if is_postgresql(engine):
        result = conn.execute(text("""
            UPDATE projects
            SET geofence_geojson = geometry
            WHERE geofence_geojson IS NULL
              AND geometry IS NOT NULL
        """))
    else:
        result = conn.execute(text("""
            UPDATE projects
            SET geofence_geojson = geometry
            WHERE geofence_geojson IS NULL
              AND geometry IS NOT NULL
        """))
    rowcount = getattr(result, "rowcount", -1)
    print(f"✓ Backfilled geofence_geojson from geometry on {rowcount} row(s).")


def drop_geometry_column(conn, engine) -> None:
    if not table_exists(engine, "projects"):
        print("✓ Table 'projects' does not exist; nothing to drop.")
        return
    if not column_exists(engine, "projects", "geometry"):
        print("✓ Column 'projects.geometry' already dropped.")
        return

    if is_postgresql(engine):
        print("Dropping column 'projects.geometry'...")
        conn.execute(text('ALTER TABLE "projects" DROP COLUMN "geometry"'))
        print("✓ Dropped 'projects.geometry'.")
    else:
        # SQLite >= 3.35 supports DROP COLUMN; older versions do not. Try, fall back to no-op.
        try:
            conn.execute(text('ALTER TABLE "projects" DROP COLUMN "geometry"'))
            print("✓ Dropped 'projects.geometry' (SQLite).")
        except (OperationalError, ProgrammingError) as e:
            print(
                "! SQLite refused DROP COLUMN (likely older version). "
                "Tests use in-memory SQLite which won't see this column anyway. "
                f"Error was: {e}"
            )


def migrate(database_url: Optional[str] = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    connect_args = {}
    if "postgresql" in db_url.lower():
        connect_args["connect_timeout"] = 10

    engine = create_engine(db_url, connect_args=connect_args)

    try:
        with engine.begin() as conn:
            backfill_geofence_geojson(conn, engine)
        with engine.begin() as conn:
            drop_geometry_column(conn, engine)
        print("✓ Migration completed successfully.")
        return True
    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error during migration: {exc}")
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override database URL.")
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
