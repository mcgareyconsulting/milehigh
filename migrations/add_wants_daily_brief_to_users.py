"""
Add `wants_daily_brief` BOOLEAN column to users.

Default `False` — users opt in via the Banana Boy modal toggle.

Idempotent — safe to re-run.

Usage:
    python migrations/add_wants_daily_brief_to_users.py
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
    is_postgres = "postgresql" in db_url.lower()

    try:
        if column_exists(engine, "users", "wants_daily_brief"):
            print("✓ users.wants_daily_brief already exists.")
            return True

        if is_postgres:
            sql = (
                "ALTER TABLE users "
                "ADD COLUMN wants_daily_brief BOOLEAN NOT NULL DEFAULT FALSE"
            )
        else:
            sql = (
                "ALTER TABLE users "
                "ADD COLUMN wants_daily_brief BOOLEAN NOT NULL DEFAULT 0"
            )

        print("Adding column users.wants_daily_brief...")
        with engine.begin() as conn:
            conn.execute(text(sql))
        print("✓ Added users.wants_daily_brief.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error: {exc}")
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
    parser = argparse.ArgumentParser(
        description="Add wants_daily_brief column to users."
    )
    parser.add_argument("--database-url", help="Database URL")
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
