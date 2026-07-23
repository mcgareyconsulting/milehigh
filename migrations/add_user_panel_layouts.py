"""
Add the `user_panel_layouts` table backing the K2 configurable grid engine.

One row per (user, surface) pair stores that user's dashboard layout for a grid instance —
the Projects page, Employee Home, the metrics grid, etc. `layout` is a JSON list of
{id, span, hidden}: panel order, S/M/L size class, and which widgets are parked. The grid
falls back to localStorage when the endpoint is unavailable, so this table is a cross-device
convenience, never a hard dependency; nothing is backfilled.

Usage:
    python migrations/add_user_panel_layouts.py
    python migrations/add_user_panel_layouts.py --database-url postgresql://...

Safety properties (Postgres) — mirrors migrations/add_start_install_to_dwl.py:
  - Idempotent CREATE TABLE/INDEX IF NOT EXISTS, so NO schema reflection is needed on
    Postgres (reflection on a second pooled connection is what froze a prior migration).
  - One AUTOCOMMIT connection: each DDL is its own implicit transaction, so any lock is
    held only for the instant the statement runs.
  - lock_timeout makes a blocked statement FAIL FAST and retry with backoff rather than
    queueing behind live traffic. CREATE TABLE takes no lock on existing tables anyway;
    this table is brand new, so contention is effectively nil.
  - The DB URL is masked in all log output.
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


# Idempotent DDL — works on both Postgres and modern SQLite. JSON maps to jsonb-less
# `JSON` on Postgres and TEXT-backed JSON on SQLite; both accept a JSON array literal.
_LAYOUT_TABLE = """
    CREATE TABLE IF NOT EXISTS user_panel_layouts (
        id {pk},
        user_id INTEGER NOT NULL REFERENCES users(id),
        surface_key VARCHAR(120) NOT NULL,
        layout {json} NOT NULL DEFAULT '[]',
        updated_at TIMESTAMP DEFAULT NULL
    )
"""
_LAYOUT_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_panel_layout "
    "ON user_panel_layouts (user_id, surface_key)"
)
_LAYOUT_USER_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_user_panel_layouts_user_id "
    "ON user_panel_layouts (user_id)"
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

        if conn.execute(text("SELECT to_regclass('users')")).scalar() is None:
            print("✗ Table 'users' does not exist. Run the base schema first.")
            return False

        try:
            _run_with_retry(
                conn,
                _LAYOUT_TABLE.format(pk="SERIAL PRIMARY KEY", json="JSON"),
                "user_panel_layouts table",
            )
            _run_with_retry(conn, _LAYOUT_INDEX, "uq_user_panel_layout (user_id, surface_key)")
            _run_with_retry(conn, _LAYOUT_USER_INDEX, "ix_user_panel_layouts_user_id")
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get a lock. "
                    "Nothing was committed. Re-run during a quieter window."
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        print("✗ Table 'users' does not exist. Run the base schema first.")
        return False

    with engine.begin() as conn:
        conn.execute(text(_LAYOUT_TABLE.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT", json="JSON")))
        conn.execute(text(_LAYOUT_INDEX))
        conn.execute(text(_LAYOUT_USER_INDEX))
        print("✓ user_panel_layouts table + indexes")
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
        description="Add the user_panel_layouts table (K2 grid engine persistence)."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
