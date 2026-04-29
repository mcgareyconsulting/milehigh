"""
Create the banana_boy_usage table for per-API-call tracking.

Usage:
    ENVIRONMENT=sandbox    python migrations/create_banana_boy_usage_table.py
    ENVIRONMENT=production python migrations/create_banana_boy_usage_table.py

Pulls the DB URL the same way the app does (app/db_config.py):
- ENVIRONMENT=sandbox    -> SANDBOX_DATABASE_URL
- ENVIRONMENT=production -> PRODUCTION_DATABASE_URL or DATABASE_URL
- ENVIRONMENT=local      -> LOCAL_DATABASE_URL (or sqlite:///jobs.sqlite)

Idempotent: inspects schema before creating the table or indexes.
"""

import argparse
import os
import sys

# Make `app` importable when run as `python migrations/<file>.py` from the repo root.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Triggers app/config.py's load_dotenv(...) on import so DATABASE_URL etc. are populated.
from app import config as _app_config  # noqa: F401, E402  (side effect: load .env)
from app.db_config import get_database_config  # noqa: E402

from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.exc import OperationalError, ProgrammingError  # noqa: E402


def resolve_database_url(cli_url: str | None) -> str:
    if cli_url:
        url = cli_url.strip()
        return url.replace("postgres://", "postgresql://", 1) if url.startswith("postgres://") else url

    environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
    db_url, _engine_options = get_database_config(environment.lower())
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return db_url


def table_exists(engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def index_exists(engine, table_name: str, index_name: str) -> bool:
    if not table_exists(engine, table_name):
        return False
    return any(idx["name"] == index_name for idx in inspect(engine).get_indexes(table_name))


def migrate(database_url: str | None = None) -> bool:
    db_url = resolve_database_url(database_url)
    safe_url = db_url
    if "@" in safe_url:
        # Mask credentials for the log line.
        prefix, rest = safe_url.split("://", 1)
        creds, host = rest.split("@", 1)
        safe_url = f"{prefix}://***@{host}"
    print(f"Connecting to database: {safe_url}")

    is_postgres = db_url.startswith("postgresql://")
    engine = create_engine(db_url)

    try:
        if table_exists(engine, "banana_boy_usage"):
            print("Table 'banana_boy_usage' already exists. Nothing to do.")
            return True

        print("Creating 'banana_boy_usage' table...")
        if is_postgres:
            create_sql = """
                CREATE TABLE banana_boy_usage (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    chat_message_id INTEGER REFERENCES chat_messages(id) ON DELETE SET NULL,
                    provider VARCHAR(32) NOT NULL,
                    operation VARCHAR(32) NOT NULL,
                    model VARCHAR(64) NOT NULL,
                    iteration INTEGER,
                    duration_ms INTEGER NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cache_read_tokens INTEGER,
                    cache_creation_tokens INTEGER,
                    input_chars INTEGER,
                    output_bytes INTEGER,
                    audio_seconds DOUBLE PRECISION,
                    audio_bytes INTEGER,
                    cost_usd DOUBLE PRECISION,
                    payload JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
        else:
            create_sql = """
                CREATE TABLE banana_boy_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    chat_message_id INTEGER REFERENCES chat_messages(id) ON DELETE SET NULL,
                    provider VARCHAR(32) NOT NULL,
                    operation VARCHAR(32) NOT NULL,
                    model VARCHAR(64) NOT NULL,
                    iteration INTEGER,
                    duration_ms INTEGER NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cache_read_tokens INTEGER,
                    cache_creation_tokens INTEGER,
                    input_chars INTEGER,
                    output_bytes INTEGER,
                    audio_seconds REAL,
                    audio_bytes INTEGER,
                    cost_usd REAL,
                    payload TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """

        with engine.begin() as conn:
            conn.execute(text(create_sql))
        print("Created 'banana_boy_usage'.")

        for index_name, column in (
            ("ix_banana_boy_usage_user_id", "user_id"),
            ("ix_banana_boy_usage_chat_message_id", "chat_message_id"),
            ("ix_banana_boy_usage_created_at", "created_at"),
        ):
            if not index_exists(engine, "banana_boy_usage", index_name):
                print(f"Creating index {index_name} on banana_boy_usage({column})...")
                with engine.begin() as conn:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON banana_boy_usage ({column})"
                    ))

        print("Migration complete.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"Database error: {exc}")
        return False
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create banana_boy_usage table.")
    parser.add_argument("--database-url", help="Override DB URL (otherwise from ENVIRONMENT).")
    args = parser.parse_args()
    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
