"""
Add Google OAuth columns to users + create google_credentials table.

Adds:
  users.email                VARCHAR(255), nullable, indexed
  users.google_sub           VARCHAR(255), unique, nullable, indexed
  google_credentials         new table (one row per user)

Backfills users.email from username when null (best-effort, since for
demo users `username` is already an email address).

Idempotent — safe to re-run.

Usage:
    python migrations/add_google_credentials.py
    python migrations/add_google_credentials.py --database-url sqlite:///instance/jobs.sqlite
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
    if not table_exists(engine, table_name):
        return False
    return any(col["name"] == column_name for col in inspect(engine).get_columns(table_name))


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

        # 1. users.email
        if not column_exists(engine, "users", "email"):
            print("Adding column users.email...")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
            print("✓ Added users.email.")
        else:
            print("✓ users.email already exists.")

        # 2. users.google_sub
        if not column_exists(engine, "users", "google_sub"):
            print("Adding column users.google_sub...")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)"))
            print("✓ Added users.google_sub.")
        else:
            print("✓ users.google_sub already exists.")

        # 3. Index on users.google_sub (unique)
        if not index_exists(engine, "users", "ux_users_google_sub"):
            print("Creating unique index ux_users_google_sub...")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE UNIQUE INDEX ux_users_google_sub ON users (google_sub)"
                ))
            print("✓ Created ux_users_google_sub.")

        # 4. Backfill users.email from username
        print("Backfilling users.email from username where null...")
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE users SET email = username WHERE email IS NULL"
            ))
        print("✓ Backfilled users.email.")

        # 5. google_credentials table
        if not table_exists(engine, "google_credentials"):
            print("Creating google_credentials table...")
            if is_postgres:
                create_sql = """
                    CREATE TABLE google_credentials (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL UNIQUE
                            REFERENCES users(id) ON DELETE CASCADE,
                        provider VARCHAR(32) NOT NULL DEFAULT 'google',
                        google_sub VARCHAR(255) NOT NULL UNIQUE,
                        email VARCHAR(255) NOT NULL,
                        email_verified BOOLEAN NOT NULL DEFAULT TRUE,
                        access_token TEXT NOT NULL,
                        refresh_token TEXT,
                        token_expires_at TIMESTAMP NOT NULL,
                        scopes TEXT NOT NULL,
                        id_token TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_refreshed_at TIMESTAMP
                    )
                """
            else:
                create_sql = """
                    CREATE TABLE google_credentials (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE
                            REFERENCES users(id) ON DELETE CASCADE,
                        provider VARCHAR(32) NOT NULL DEFAULT 'google',
                        google_sub VARCHAR(255) NOT NULL UNIQUE,
                        email VARCHAR(255) NOT NULL,
                        email_verified BOOLEAN NOT NULL DEFAULT 1,
                        access_token TEXT NOT NULL,
                        refresh_token TEXT,
                        token_expires_at DATETIME NOT NULL,
                        scopes TEXT NOT NULL,
                        id_token TEXT,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_refreshed_at DATETIME
                    )
                """
            with engine.begin() as conn:
                conn.execute(text(create_sql))
            print("✓ Created google_credentials.")
        else:
            print("✓ google_credentials already exists.")

        # 6. Email index on google_credentials
        if not index_exists(engine, "google_credentials", "ix_google_credentials_email"):
            print("Creating index ix_google_credentials_email...")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_google_credentials_email "
                    "ON google_credentials (email)"
                ))
            print("✓ Created ix_google_credentials_email.")

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
        description="Add google_credentials table + users.email/google_sub columns."
    )
    parser.add_argument("--database-url", help="Database URL")
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
