"""
Add DWL start-install tracking: `start_install` and `design_drawings_due` columns on
the submittals table, plus the `pending_start_installs` handoff table.

A desired start-install date can be set on a DRR ("Drafting Release Review") submittal in
the Drafting Work Load before any release exists. `design_drawings_due` (DDD) is derived as
15 business days before that date. The `pending_start_installs` table queues the date keyed
by Rel so the matching job-log release picks it up when it is created (the pasted Release #
equals the Rel).

This migration only adds the columns/table; nothing is backfilled.

Usage:
    python migrations/add_start_install_to_dwl.py
    python migrations/add_start_install_to_dwl.py --database-url postgresql://...

Safety properties (Postgres) — this script must never freeze the table again:
  - Every statement is idempotent (`ADD COLUMN IF NOT EXISTS`, `CREATE TABLE/INDEX
    IF NOT EXISTS`), so it needs NO schema reflection. The original froze because it
    called SQLAlchemy reflection (inspect/get_columns) on a SECOND pooled connection
    while the FIRST connection still held ACCESS EXCLUSIVE on submittals — a self-block
    Postgres can't auto-detect (the holder was idle-in-transaction, not lock-waiting).
  - One AUTOCOMMIT connection: each DDL is its own implicit transaction, so the
    ACCESS EXCLUSIVE lock is held only for the instant the statement runs, never across
    the whole migration.
  - `lock_timeout` makes a blocked ALTER FAIL FAST instead of queueing behind live
    traffic (which would block every later query on submittals). It then auto-retries
    with backoff, so transient contention self-heals without manual intervention.
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

# Postgres lock/retry tuning. ADD COLUMN here is metadata-only (nullable, no default),
# so it needs the lock for only an instant — a short timeout plus a few retries beats
# blocking. Total worst-case wait ≈ LOCK_RETRIES * (LOCK_RETRIES+1)/2 * RETRY_BASE_SECONDS.
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


# Idempotent DDL — works on both Postgres and modern SQLite.
_PENDING_TABLE = """
    CREATE TABLE IF NOT EXISTS pending_start_installs (
        id {pk},
        rel INTEGER NOT NULL,
        job_number VARCHAR(100),
        submittal_id VARCHAR(255),
        start_install DATE NOT NULL,
        consumed_at TIMESTAMP DEFAULT NULL,
        consumed_job INTEGER DEFAULT NULL,
        consumed_release VARCHAR(16) DEFAULT NULL,
        created_at TIMESTAMP DEFAULT NULL,
        updated_at TIMESTAMP DEFAULT NULL
    )
"""
_PENDING_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_pending_start_installs_rel "
    "ON pending_start_installs (rel)"
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
    # AUTOCOMMIT: each statement is its own transaction, so the ACCESS EXCLUSIVE lock an
    # ALTER needs is released the instant the statement finishes — never held across the
    # migration, and never held while we run anything else. No reflection involved.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        if conn.execute(text("SELECT to_regclass('submittals')")).scalar() is None:
            print("✗ Table 'submittals' does not exist. Run the base schema first.")
            return False

        try:
            _run_with_retry(
                conn,
                "ALTER TABLE submittals ADD COLUMN IF NOT EXISTS start_install DATE",
                "submittals.start_install",
            )
            _run_with_retry(
                conn,
                "ALTER TABLE submittals ADD COLUMN IF NOT EXISTS design_drawings_due DATE",
                "submittals.design_drawings_due",
            )
            _run_with_retry(conn, _PENDING_TABLE.format(pk="SERIAL PRIMARY KEY"), "pending_start_installs table")
            _run_with_retry(conn, _PENDING_INDEX, "pending_start_installs.rel unique index")
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock on "
                    "'submittals' — the table is under sustained load. Nothing was committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # SQLite is single-writer with no concurrent prod traffic, so lock contention isn't a
    # concern. Older SQLite lacks ADD COLUMN IF NOT EXISTS, so guard columns by inspection.
    inspector = inspect(engine)
    if "submittals" not in inspector.get_table_names():
        print("✗ Table 'submittals' does not exist. Run the base schema first.")
        return False
    existing = {c["name"] for c in inspector.get_columns("submittals")}

    with engine.begin() as conn:
        if "start_install" not in existing:
            conn.execute(text("ALTER TABLE submittals ADD COLUMN start_install DATE"))
            print("✓ submittals.start_install")
        else:
            print("submittals.start_install already exists, skipping")

        if "design_drawings_due" not in existing:
            conn.execute(text("ALTER TABLE submittals ADD COLUMN design_drawings_due DATE"))
            print("✓ submittals.design_drawings_due")
        else:
            print("submittals.design_drawings_due already exists, skipping")

        conn.execute(text(_PENDING_TABLE.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT")))
        conn.execute(text(_PENDING_INDEX))
        print("✓ pending_start_installs table + rel unique index")
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
        description="Add DWL start_install/DDD columns and the pending_start_installs table."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
