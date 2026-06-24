"""
Add PDF-drawing comment threads with @mention notifications:
  - the `drawing_version_comments` table (one comment thread per drawing version)
  - the `drawing_version_comment_id` FK column on `notifications`

Each comment on a `ReleaseDrawingVersion` can `@FirstName`-mention teammates; the
comment route parses the body and writes `notifications` rows that click through
to the drawing. This migration only adds the table/column; nothing is backfilled.

Usage:
    python migrations/add_drawing_version_comments.py
    python migrations/add_drawing_version_comments.py --database-url postgresql://...

Safety properties (Postgres) — this script must never freeze a table:
  - Every statement is idempotent (`ADD COLUMN IF NOT EXISTS`, `CREATE TABLE/INDEX
    IF NOT EXISTS`), so it needs NO schema reflection on Postgres (reflection on a
    second pooled connection while the first holds ACCESS EXCLUSIVE is a self-block
    Postgres can't auto-detect).
  - One AUTOCOMMIT connection: each DDL is its own implicit transaction, so any
    ACCESS EXCLUSIVE lock is held only for the instant the statement runs.
  - `lock_timeout` makes a blocked ALTER FAIL FAST instead of queueing behind live
    traffic; it then auto-retries with backoff so transient contention self-heals.
  - The ADD COLUMN is metadata-only (nullable, no default) so it needs the lock
    for only an instant.
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


# Idempotent DDL — works on both Postgres and modern SQLite.
_COMMENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS drawing_version_comments (
        id {pk},
        drawing_version_id INTEGER NOT NULL,
        release_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        author_id INTEGER NOT NULL,
        author_name VARCHAR(160) NOT NULL,
        created_at TIMESTAMP NOT NULL
    )
"""
_COMMENTS_VERSION_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_drawing_version_comments_drawing_version_id "
    "ON drawing_version_comments (drawing_version_id)"
)
_COMMENTS_RELEASE_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_drawing_version_comments_release_id "
    "ON drawing_version_comments (release_id)"
)
_NOTIF_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_notifications_drawing_version_comment_id "
    "ON notifications (drawing_version_comment_id)"
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

        if conn.execute(text("SELECT to_regclass('notifications')")).scalar() is None:
            print("✗ Table 'notifications' does not exist. Run the base schema first.")
            return False

        try:
            _run_with_retry(conn, _COMMENTS_TABLE.format(pk="SERIAL PRIMARY KEY"), "drawing_version_comments table")
            _run_with_retry(conn, _COMMENTS_VERSION_INDEX, "drawing_version_comments.drawing_version_id index")
            _run_with_retry(conn, _COMMENTS_RELEASE_INDEX, "drawing_version_comments.release_id index")
            _run_with_retry(
                conn,
                "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS drawing_version_comment_id INTEGER",
                "notifications.drawing_version_comment_id",
            )
            _run_with_retry(conn, _NOTIF_INDEX, "notifications.drawing_version_comment_id index")
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock — the "
                    "table is under sustained load. Nothing was committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # SQLite is single-writer with no concurrent prod traffic, so lock contention isn't a
    # concern. Older SQLite lacks ADD COLUMN IF NOT EXISTS, so guard the column by inspection.
    inspector = inspect(engine)
    if "notifications" not in inspector.get_table_names():
        print("✗ Table 'notifications' does not exist. Run the base schema first.")
        return False
    existing = {c["name"] for c in inspector.get_columns("notifications")}

    with engine.begin() as conn:
        conn.execute(text(_COMMENTS_TABLE.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT")))
        conn.execute(text(_COMMENTS_VERSION_INDEX))
        conn.execute(text(_COMMENTS_RELEASE_INDEX))
        print("✓ drawing_version_comments table + indexes")

        if "drawing_version_comment_id" not in existing:
            conn.execute(text("ALTER TABLE notifications ADD COLUMN drawing_version_comment_id INTEGER"))
            print("✓ notifications.drawing_version_comment_id")
        else:
            print("notifications.drawing_version_comment_id already exists, skipping")
        conn.execute(text(_NOTIF_INDEX))
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
        description="Add drawing_version_comments table and notifications.drawing_version_comment_id."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
