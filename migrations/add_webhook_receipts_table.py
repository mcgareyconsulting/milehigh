"""
Create webhook_receipts table for Procore burst dedup.

Procore sends 2-5 identical webhook deliveries per update within ~7 seconds.
The webhook handler writes a receipt on first delivery; retries hit the unique
constraint and are rejected before any Procore API call is made.

Usage:
    python migrations/add_webhook_receipts_table.py
    python migrations/add_webhook_receipts_table.py --database-url postgresql://...

Idempotent — safe to run multiple times.
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


def infer_database_url(cli_url=None):
    candidates = [
        cli_url,
        os.environ.get("SANDBOX_DATABASE_URL"),
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
        if value.startswith(("postgresql://", "mysql://", "sqlite://")):
            return value
        return f"sqlite:///{os.path.join(ROOT_DIR, value) if not os.path.isabs(value) else value}"
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"


def table_exists(engine, table_name):
    return table_name in inspect(engine).get_table_names()


def migrate(database_url=None):
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")
    engine = create_engine(db_url)

    try:
        if table_exists(engine, "webhook_receipts"):
            print("✓ Table 'webhook_receipts' already exists. Nothing to do.")
            return True

        is_pg = "postgresql" in db_url.lower()

        with engine.begin() as conn:
            if is_pg:
                conn.execute(text("""
                    CREATE TABLE webhook_receipts (
                        id          SERIAL PRIMARY KEY,
                        receipt_hash VARCHAR(64) NOT NULL UNIQUE,
                        provider    VARCHAR(32) NOT NULL DEFAULT 'procore',
                        resource_id VARCHAR(64),
                        received_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """))
                conn.execute(text(
                    "CREATE INDEX ix_webhook_receipts_received_at ON webhook_receipts (received_at)"
                ))
            else:
                conn.execute(text("""
                    CREATE TABLE webhook_receipts (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        receipt_hash VARCHAR(64) NOT NULL UNIQUE,
                        provider    VARCHAR(32) NOT NULL DEFAULT 'procore',
                        resource_id VARCHAR(64),
                        received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text(
                    "CREATE INDEX ix_webhook_receipts_received_at ON webhook_receipts (received_at)"
                ))

        print("✓ Table 'webhook_receipts' created successfully.")
        return True

    except (OperationalError, ProgrammingError) as e:
        print(f"✗ Database error: {e}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create webhook_receipts table.")
    parser.add_argument("--database-url", help="Override database URL.")
    args = parser.parse_args()
    sys.exit(0 if migrate(args.database_url) else 1)
