"""
Add is_drafter column to users table.

This boolean flag grants drafter-level permissions: editing Comp Status,
Due Date, and Notes on the DWL page, without access to admin-only operations
like order manipulation, Procore status changes, or submittal bumping.

Usage:
    python migrations/add_is_drafter_to_users.py --database-url sqlite:///instance/jobs.sqlite
    python migrations/add_is_drafter_to_users.py
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
        os.environ.get("JOBS_SQLITE_PATH"),
        os.environ.get("SANDBOX_DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
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
    if table_name not in inspect(engine).get_table_names():
        return False
    return any(col["name"] == column_name for col in inspect(engine).get_columns(table_name))


def migrate(database_url: Optional[str] = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    connect_args = {}
    if "postgresql" in db_url.lower():
        connect_args["connect_timeout"] = 10

    engine = create_engine(db_url, connect_args=connect_args)

    try:
        if not table_exists(engine, "users"):
            print("\u2717 Table 'users' does not exist.")
            return False

        # Add is_drafter column if it doesn't exist
        if not column_exists(engine, "users", "is_drafter"):
            print("Adding column 'is_drafter'...")
            with engine.begin() as conn:
                # PostgreSQL requires FALSE, SQLite accepts 0 or FALSE
                default_val = "FALSE" if "postgresql" in db_url.lower() else "0"
                conn.execute(text(f"ALTER TABLE users ADD COLUMN is_drafter BOOLEAN NOT NULL DEFAULT {default_val}"))
            print("\u2713 Added 'is_drafter'.")
        else:
            print("\u2713 'is_drafter' already exists.")

        print("\u2713 Migration completed successfully.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"\u2717 Database error: {exc}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as exc:
        print(f"\u2717 Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add is_drafter column to users table."
    )
    parser.add_argument("--database-url", help="Database URL")
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
