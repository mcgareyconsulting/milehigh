"""
Rename procore_submittals table to submittals.

- Rename: procore_submittals → submittals

Idempotent: safe to run multiple times.
Usage:
    python migrations/rename_procore_submittals_to_submittals.py
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")
load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url=None):
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
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def rename_table_if_needed(conn, engine, old_name: str, new_name: str) -> None:
    if not table_exists(engine, old_name):
        print(f"✓ Table '{old_name}' does not exist; nothing to rename.")
        return
    if table_exists(engine, new_name):
        print(f"✓ Table '{new_name}' already exists; skipping rename.")
        return
    print(f"Renaming table '{old_name}' → '{new_name}'...")
    conn.execute(text(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"'))
    print(f"✓ Renamed '{old_name}' to '{new_name}'.")


def main():
    parser = argparse.ArgumentParser(description="Rename procore_submittals to submittals")
    parser.add_argument("--database-url", help="Database URL (default from env)")
    args = parser.parse_args()
    url = infer_database_url(args.database_url)
    print(f"Using database: {url.split('@')[-1] if '@' in url else url}")

    try:
        engine = create_engine(url)
        with engine.begin() as conn:
            rename_table_if_needed(conn, engine, "procore_submittals", "submittals")
        print("Migration completed.")
    except OperationalError as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
