"""
Replace 'name' column on users table with 'first_name' and 'last_name'.

Steps:
  1. Add first_name VARCHAR(255)
  2. Add last_name VARCHAR(255)
  3. Backfill from existing 'name' column (split on first space)
  4. Drop 'name' column

Idempotent — safe to re-run.

Usage:
    python migrations/add_first_last_name_to_users.py --database-url sqlite:///instance/jobs.sqlite
    python migrations/add_first_last_name_to_users.py
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
    is_postgres = "postgresql" in db_url.lower()

    try:
        if not table_exists(engine, "users"):
            print("✗ Table 'users' does not exist.")
            return False

        # 1. Add first_name
        if not column_exists(engine, "users", "first_name"):
            print("Adding column 'first_name'...")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR(255)"))
            print("✓ Added 'first_name'.")
        else:
            print("✓ 'first_name' already exists.")

        # 2. Add last_name
        if not column_exists(engine, "users", "last_name"):
            print("Adding column 'last_name'...")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR(255)"))
            print("✓ Added 'last_name'.")
        else:
            print("✓ 'last_name' already exists.")

        # 3. Backfill from 'name' if it exists
        if column_exists(engine, "users", "name"):
            print("Backfilling first_name / last_name from 'name'...")
            with engine.begin() as conn:
                if is_postgres:
                    conn.execute(text("""
                        UPDATE users
                        SET
                            first_name = COALESCE(first_name, SPLIT_PART(name, ' ', 1)),
                            last_name  = COALESCE(last_name,  NULLIF(TRIM(SUBSTRING(name FROM POSITION(' ' IN name))), ''))
                        WHERE name IS NOT NULL AND name != ''
                    """))
                else:
                    # SQLite
                    conn.execute(text("""
                        UPDATE users
                        SET
                            first_name = COALESCE(first_name,
                                CASE WHEN INSTR(name, ' ') > 0
                                     THEN SUBSTR(name, 1, INSTR(name, ' ') - 1)
                                     ELSE name
                                END),
                            last_name = COALESCE(last_name,
                                CASE WHEN INSTR(name, ' ') > 0
                                     THEN TRIM(SUBSTR(name, INSTR(name, ' ')))
                                     ELSE NULL
                                END)
                        WHERE name IS NOT NULL AND name != ''
                    """))
            print("✓ Backfilled names.")

            # 4. Drop 'name' column
            print("Dropping column 'name'...")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users DROP COLUMN name"))
            print("✓ Dropped 'name'.")
        else:
            print("✓ Column 'name' already removed.")

        print("✓ Migration completed successfully.")
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
        description="Replace 'name' with 'first_name'/'last_name' on users table."
    )
    parser.add_argument("--database-url", help="Database URL")
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
