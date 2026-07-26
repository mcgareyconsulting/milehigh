"""
Phase 1 reshape of tm_tickets for the native mobile-creation T&M workflow.

The tm_tickets table was first created (migrations/add_tm_tickets.py) for the
legacy-paper vision-ingestion path. The module pivoted to native digital
creation, so this migration ADDS the header/creator/attachment columns the
creation form needs. Nothing is dropped: the vision-era columns
(raw_extraction, extract_model, extract_error, source_*) stay in place, nullable
and unused, since the paper-import path is parked (not removed).

New columns (all nullable, metadata-only):
    location, gc_company, gc_contact_name, foreman_name, created_by, attachments

Note on `status`: new native rows are written as 'draft' by the app (the model's
Python default), so this migration does NOT alter the column's DB server_default
— that keeps every statement metadata-only. Pre-existing test rows keep their old
status values harmlessly.

Usage:
    python migrations/reshape_tm_tickets_p1.py
    python migrations/reshape_tm_tickets_p1.py --database-url postgresql://...

Safety properties (Postgres) — mirrors migrations/add_start_install_to_dwl.py:
  - Idempotent `ADD COLUMN IF NOT EXISTS` only, so NO schema reflection is needed
    (reflection on a second pooled connection while the first holds a lock is an
    undetectable self-deadlock).
  - One AUTOCOMMIT connection: each ALTER is its own implicit transaction, so the
    ACCESS EXCLUSIVE lock is held only for the instant the statement runs.
  - `lock_timeout` makes a blocked ALTER FAIL FAST instead of queueing behind live
    traffic; it auto-retries with backoff.
  - Each ADD COLUMN is metadata-only (nullable, no volatile default) so it's instant.
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

# column name -> SQL type. JSON degrades to TEXT affinity on SQLite, which is what
# SQLAlchemy's JSON type expects there.
_NEW_COLUMNS = (
    ("location", "VARCHAR(255)"),
    ("gc_company", "VARCHAR(128)"),
    ("gc_contact_name", "VARCHAR(128)"),
    ("foreman_name", "VARCHAR(128)"),
    ("created_by", "VARCHAR(80)"),
    ("attachments", "JSON"),
)


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

        try:
            for name, sqltype in _NEW_COLUMNS:
                _run_with_retry(
                    conn,
                    f"ALTER TABLE tm_tickets ADD COLUMN IF NOT EXISTS {name} {sqltype}",
                    f"tm_tickets.{name}",
                )
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock on "
                    "'tm_tickets' — the table is under sustained load. Nothing was committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # SQLite is single-writer with no concurrent prod traffic; lock contention isn't a
    # concern. Older SQLite lacks ADD COLUMN IF NOT EXISTS, so guard columns by inspection.
    inspector = inspect(engine)
    if "tm_tickets" not in inspector.get_table_names():
        print("✗ Table 'tm_tickets' does not exist. Run migrations/add_tm_tickets.py first.")
        return False
    existing = {c["name"] for c in inspector.get_columns("tm_tickets")}

    with engine.begin() as conn:
        for name, sqltype in _NEW_COLUMNS:
            if name in existing:
                print(f"tm_tickets.{name} already exists, skipping")
                continue
            conn.execute(text(f"ALTER TABLE tm_tickets ADD COLUMN {name} {sqltype}"))
            print(f"✓ tm_tickets.{name}")
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
        description="Phase 1 reshape: add native-creation columns to tm_tickets."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
