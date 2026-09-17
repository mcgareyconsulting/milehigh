"""
Add ``releases.additional_install_hrs`` and ``releases.additional_install_note`` — the
splice modal's "additional install hours" (T9, Bill 2026-09-16): hours on a splice that
come from OUTSIDE the parent's budget install-hour pool, with the required note saying why.

``install_hrs`` on a splice stays its TOTAL install hours (it drives comp_eta everywhere);
``additional_install_hrs`` is the part of that total that does not draw from the parent's
pool. Existing rows stay NULL = no additional hours.

Usage:
    python migrations/add_splice_additional_install_hrs.py
    python migrations/add_splice_additional_install_hrs.py --database-url postgresql://...

Safety properties (Postgres) — per migrations/README.md:
  - Idempotent DDL only (`ADD COLUMN IF NOT EXISTS`), so no schema reflection is needed.
  - One AUTOCOMMIT connection: each statement is its own implicit transaction, so the
    ACCESS EXCLUSIVE lock is held for an instant, never across the migration.
  - `lock_timeout` makes a blocked ALTER fail fast; it retries with backoff.
  - Both ADD COLUMNs are metadata-only (nullable, no default) so they are instant.
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

    for value in (
        os.environ.get("LOCAL_DATABASE_URL"),
        os.environ.get("DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
    ):
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
    """Execute one idempotent statement, retrying on lock_timeout with backoff."""
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


COLUMNS = (
    ("additional_install_hrs", "DOUBLE PRECISION", "FLOAT"),
    ("additional_install_note", "TEXT", "TEXT"),
)


def _migrate_postgres(engine) -> bool:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        if conn.execute(text("SELECT to_regclass('releases')")).scalar() is None:
            print("✗ Table 'releases' does not exist. Run the base schema first.")
            return False

        try:
            for name, pg_type, _ in COLUMNS:
                _run_with_retry(
                    conn,
                    f"ALTER TABLE releases ADD COLUMN IF NOT EXISTS {name} {pg_type}",
                    f"releases.{name}",
                )
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock on "
                    "'releases' — the table is under sustained load. Nothing was committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    inspector = inspect(engine)
    if "releases" not in inspector.get_table_names():
        print("✗ Table 'releases' does not exist. Run the base schema first.")
        return False
    existing = {c["name"] for c in inspector.get_columns("releases")}

    with engine.begin() as conn:
        for name, _, sqlite_type in COLUMNS:
            if name in existing:
                print(f"releases.{name} already exists, skipping")
                continue
            conn.execute(text(f"ALTER TABLE releases ADD COLUMN {name} {sqlite_type}"))
            print(f"✓ releases.{name}")
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
        description="Add releases.additional_install_hrs / additional_install_note (splice additional hours)."
    )
    parser.add_argument("--database-url", help="Override database URL (otherwise inferred from env).")
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
