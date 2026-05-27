"""
Create the chat_messages table for the Banana Boy assistant.

Usage:
    python migrations/create_chat_messages_table.py

Idempotent: inspects schema before creating the table or indexes.
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


def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url: str = None) -> str:
    candidates = [
        cli_url,
        os.environ.get("DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
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


def migrate(database_url: str = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)
    is_postgres = db_url.startswith("postgresql://")

    try:
        if table_exists(engine, "chat_messages"):
            print("Table 'chat_messages' already exists. Nothing to do.")
            return True

        print("Creating 'chat_messages' table...")
        if is_postgres:
            create_sql = """
                CREATE TABLE chat_messages (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role VARCHAR(16) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
        else:
            create_sql = """
                CREATE TABLE chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role VARCHAR(16) NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """

        with engine.begin() as conn:
            conn.execute(text(create_sql))
        print("Created 'chat_messages'.")

        for index_name, column in (
            ("ix_chat_messages_user_id", "user_id"),
            ("ix_chat_messages_created_at", "created_at"),
        ):
            if not index_exists(engine, "chat_messages", index_name):
                print(f"Creating index {index_name} on chat_messages({column})...")
                with engine.begin() as conn:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON chat_messages ({column})"
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
    parser = argparse.ArgumentParser(description="Create chat_messages table.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
