"""
Add photo/video attachments to T&M tickets: creates the tm_ticket_attachments
table and drops the now-superseded tm_tickets.attachments JSON column.

The Phase 1 reshape (reshape_tm_tickets_p1.py) added a placeholder JSON
`attachments` column on tm_tickets before the attachment feature was designed.
It was never written to (no rows populated it) — this migration replaces it
with a proper child table (TMTicketAttachment), mirroring board_item_photos:
normalized audit fields (uploader, size, timestamp), soft-delete, and cascade
delete when a ticket is removed. Safe to drop: zero data loss.

Usage:
    python migrations/add_tm_ticket_attachments.py
    python migrations/add_tm_ticket_attachments.py --database-url postgresql://...

Safety properties (Postgres) — mirrors migrations/add_start_install_to_dwl.py:
  - Idempotent DDL only (`CREATE TABLE/INDEX IF NOT EXISTS`, `DROP COLUMN IF
    EXISTS`), so NO schema reflection is needed (reflection on a second pooled
    connection while the first holds a lock is an undetectable self-deadlock).
  - One AUTOCOMMIT connection: each DDL is its own implicit transaction, so any
    ACCESS EXCLUSIVE lock is held only for the instant the statement runs.
  - `lock_timeout` makes a blocked statement FAIL FAST instead of queueing
    behind live traffic; it auto-retries with backoff.
  - DROP COLUMN on an unpopulated nullable JSON column is metadata-only in
    Postgres (no table rewrite), same instant-lock profile as ADD COLUMN.
"""

import argparse
import os
import sys
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

LOCK_TIMEOUT = "5s"
STATEMENT_TIMEOUT = "30s"
LOCK_RETRIES = 4
RETRY_BASE_SECONDS = 3

load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def _coerce_url(value: str) -> str:
    value = value.strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
        return value
    return normalize_sqlite_path(value)


def infer_database_url(cli_url: str = None) -> str:
    """Figure out which database to hit, honoring CLI and ENVIRONMENT (mirrors db_config.py)."""
    if cli_url:
        return _coerce_url(cli_url)

    environment = (os.environ.get("ENVIRONMENT") or "local").strip().lower()

    if environment == "production":
        value = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not value:
            raise ValueError(
                "ENVIRONMENT=production but neither PRODUCTION_DATABASE_URL nor "
                "DATABASE_URL is set (refusing to guess; pass --database-url)."
            )
        return _coerce_url(value)

    if environment == "sandbox":
        value = os.environ.get("SANDBOX_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not value:
            raise ValueError(
                "ENVIRONMENT=sandbox but neither SANDBOX_DATABASE_URL nor "
                "DATABASE_URL is set (refusing to guess; pass --database-url)."
            )
        return _coerce_url(value)

    candidates = [
        os.environ.get("LOCAL_DATABASE_URL"),
        os.environ.get("DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
    ]
    for value in candidates:
        if value:
            return _coerce_url(value)

    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def _mask(url: str) -> str:
    """Render a connection URL for logging without leaking the password."""
    try:
        u = urlparse(url)
        if u.hostname:
            user = f"{u.username}@" if u.username else ""
            return f"{u.scheme}://{user}{u.hostname}/{u.path.lstrip('/')}"
    except Exception:
        pass
    return url.split("@")[-1] if "@" in url else url


_ATTACHMENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS tm_ticket_attachments (
        id {pk},
        tm_ticket_id INTEGER NOT NULL REFERENCES tm_tickets (id) ON DELETE CASCADE,
        storage_key VARCHAR(512) NOT NULL,
        original_filename VARCHAR(256),
        mime_type VARCHAR(64) NOT NULL DEFAULT 'image/jpeg',
        file_size_bytes BIGINT NOT NULL,
        uploaded_by_user_id INTEGER NOT NULL REFERENCES users (id),
        uploaded_at TIMESTAMP NOT NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT {false}
    )
"""
_ATTACHMENTS_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_tm_ticket_attachments_tm_ticket_id "
    "ON tm_ticket_attachments (tm_ticket_id)"
)


def _is_lock_timeout(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "lock" in msg and ("timeout" in msg or "not available" in msg or "55p03" in msg)


def _run_with_retry(conn, sql: str, label: str) -> None:
    """Execute one idempotent DDL statement, retrying on lock_timeout with backoff."""
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            conn.execute(text(sql))
            print(f"✓ {label}")
            return
        except OperationalError as exc:
            if _is_lock_timeout(exc) and attempt < LOCK_RETRIES:
                delay = RETRY_BASE_SECONDS * attempt
                print(
                    f"  ⏳ '{label}' couldn't get the lock (attempt {attempt}/{LOCK_RETRIES}); "
                    f"retrying in {delay}s — nothing committed, app keeps running"
                )
                time.sleep(delay)
                continue
            raise


def _migrate_postgres(engine) -> bool:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        if conn.execute(text("SELECT to_regclass('tm_tickets')")).scalar() is None:
            print("✗ Table 'tm_tickets' does not exist. Run migrations/add_tm_tickets.py first.")
            return False
        if conn.execute(text("SELECT to_regclass('users')")).scalar() is None:
            print("✗ Table 'users' does not exist. Run the base schema first.")
            return False

        try:
            _run_with_retry(
                conn,
                _ATTACHMENTS_TABLE.format(pk="SERIAL PRIMARY KEY", false="FALSE"),
                "tm_ticket_attachments table",
            )
            _run_with_retry(conn, _ATTACHMENTS_INDEX, "tm_ticket_attachments.tm_ticket_id index")
            _run_with_retry(
                conn,
                "ALTER TABLE tm_tickets DROP COLUMN IF EXISTS attachments",
                "tm_tickets.attachments (dropped, superseded by tm_ticket_attachments)",
            )
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock — "
                    "the referenced table is under sustained load. Nothing was committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # SQLite is single-writer with no concurrent prod traffic; no lock concerns.
    inspector = inspect(engine)
    if "tm_tickets" not in inspector.get_table_names():
        print("✗ Table 'tm_tickets' does not exist. Run migrations/add_tm_tickets.py first.")
        return False
    if "users" not in inspector.get_table_names():
        print("✗ Table 'users' does not exist. Run the base schema first.")
        return False

    with engine.begin() as conn:
        conn.execute(text(_ATTACHMENTS_TABLE.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT", false="0")))
        conn.execute(text(_ATTACHMENTS_INDEX))
        print("✓ tm_ticket_attachments table + index")

        existing = {c["name"] for c in inspector.get_columns("tm_tickets")}
        if "attachments" in existing:
            # SQLite (3.35+) supports DROP COLUMN directly.
            conn.execute(text("ALTER TABLE tm_tickets DROP COLUMN attachments"))
            print("✓ tm_tickets.attachments dropped")
        else:
            print("tm_tickets.attachments already absent, skipping")
    return True


def migrate(database_url: str = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {_mask(db_url)}")

    engine = create_engine(db_url)
    try:
        if engine.dialect.name == "sqlite":
            return _migrate_sqlite(engine)
        return _migrate_postgres(engine)
    except ProgrammingError as exc:
        print(f"✗ Database error during migration: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create tm_ticket_attachments and drop the superseded tm_tickets.attachments column."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
