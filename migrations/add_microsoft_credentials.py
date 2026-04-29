"""
Add microsoft_credentials table for per-user Outlook/Graph OAuth.

Creates:
  microsoft_credentials  new table (one row per user)

Idempotent — safe to re-run.

Usage:
    python migrations/add_microsoft_credentials.py
    python migrations/add_microsoft_credentials.py --database-url sqlite:///instance/jobs.sqlite
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


def index_exists(engine, table_name: str, index_name: str) -> bool:
    if not table_exists(engine, table_name):
        return False
    return any(idx["name"] == index_name for idx in inspect(engine).get_indexes(table_name))


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

        if not table_exists(engine, "microsoft_credentials"):
            print("Creating microsoft_credentials table...")
            if is_postgres:
                create_sql = """
                    CREATE TABLE microsoft_credentials (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL UNIQUE
                            REFERENCES users(id) ON DELETE CASCADE,
                        provider VARCHAR(32) NOT NULL DEFAULT 'microsoft',
                        ms_oid VARCHAR(255) NOT NULL UNIQUE,
                        tenant_id VARCHAR(255),
                        email VARCHAR(255) NOT NULL,
                        access_token TEXT NOT NULL,
                        refresh_token TEXT,
                        token_expires_at TIMESTAMP NOT NULL,
                        scopes TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_refreshed_at TIMESTAMP
                    )
                """
            else:
                create_sql = """
                    CREATE TABLE microsoft_credentials (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE
                            REFERENCES users(id) ON DELETE CASCADE,
                        provider VARCHAR(32) NOT NULL DEFAULT 'microsoft',
                        ms_oid VARCHAR(255) NOT NULL UNIQUE,
                        tenant_id VARCHAR(255),
                        email VARCHAR(255) NOT NULL,
                        access_token TEXT NOT NULL,
                        refresh_token TEXT,
                        token_expires_at DATETIME NOT NULL,
                        scopes TEXT NOT NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_refreshed_at DATETIME
                    )
                """
            with engine.begin() as conn:
                conn.execute(text(create_sql))
            print("✓ Created microsoft_credentials.")
        else:
            print("✓ microsoft_credentials already exists.")

        if not index_exists(engine, "microsoft_credentials", "ix_microsoft_credentials_email"):
            print("Creating index ix_microsoft_credentials_email...")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_microsoft_credentials_email "
                    "ON microsoft_credentials (email)"
                ))
            print("✓ Created ix_microsoft_credentials_email.")

        if not index_exists(engine, "microsoft_credentials", "ix_microsoft_credentials_tenant_id"):
            print("Creating index ix_microsoft_credentials_tenant_id...")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_microsoft_credentials_tenant_id "
                    "ON microsoft_credentials (tenant_id)"
                ))
            print("✓ Created ix_microsoft_credentials_tenant_id.")

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
        description="Add microsoft_credentials table for per-user Outlook OAuth."
    )
    parser.add_argument("--database-url", help="Database URL")
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
