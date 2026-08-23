"""
Add `stage_at_upload` to the release_photos table — the release's stage at the moment a
photo was uploaded (N9 photo stamp).

This is deliberately NOT the existing `release_photos.stage` column. That one is the
stage-GATE tag: it is set only when a photo is uploaded to satisfy a stage-change gate
and is NULL for an ordinary photo, and it decides whether a stage change is allowed.
Overloading it would let a stamp tag unlock a gate it was never meant to.

`stage_at_upload` is evidence, not permission: it records what stage the release was in
when the photo was taken, so a "paint complete" claim can be checked against an unpainted
photo. It is stored rather than only burned into the stamped image because the original
is kept clean and derivatives are re-rendered — a re-render reading the *current* stage
would silently manufacture the exact false evidence the stamp exists to catch.

Nullable with no backfill: photos uploaded before this migration have no recorded stage
and must render without one rather than guessing.

Usage:
    python migrations/add_stage_at_upload_to_release_photos.py
    python migrations/add_stage_at_upload_to_release_photos.py --database-url postgresql://...

Safety properties (Postgres) — same discipline as add_start_install_to_dwl.py:
  - Idempotent `ADD COLUMN IF NOT EXISTS`, so no schema reflection is needed and the
    self-deadlock that froze an earlier migration cannot recur.
  - One AUTOCOMMIT connection: the ACCESS EXCLUSIVE lock is held for an instant, not
    across the migration.
  - `lock_timeout` makes a blocked ALTER fail fast and retry with backoff.
  - The ADD COLUMN is metadata-only (nullable, no default), so it is instant.
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
_ADD_COLUMN_PG = (
    "ALTER TABLE release_photos ADD COLUMN IF NOT EXISTS stage_at_upload VARCHAR(64)"
)
_ADD_COLUMN_SQLITE = "ALTER TABLE release_photos ADD COLUMN stage_at_upload VARCHAR(64)"


def _is_lock_timeout(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "lock" in msg and ("timeout" in msg or "not available" in msg or "55p03" in msg)


def _run_with_retry(conn, sql: str, label: str) -> None:
    """Execute one idempotent DDL statement, retrying on lock_timeout with backoff."""
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            conn.execute(text(sql))
            print(f"\u2713 {label}")
            return
        except OperationalError as exc:
            if _is_lock_timeout(exc) and attempt < LOCK_RETRIES:
                delay = RETRY_BASE_SECONDS * attempt
                print(
                    f"  \u23f3 '{label}' couldn't get the lock (attempt {attempt}/{LOCK_RETRIES}); "
                    f"retrying in {delay}s — nothing committed, app keeps running"
                )
                time.sleep(delay)
                continue
            raise


def _migrate_postgres(engine) -> bool:
    # AUTOCOMMIT: the ALTER's ACCESS EXCLUSIVE lock is released the instant the statement
    # finishes. No reflection anywhere in this function — that is what froze the table before.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        if conn.execute(text("SELECT to_regclass('release_photos')")).scalar() is None:
            print("\u2717 Table 'release_photos' does not exist. Run the base schema first.")
            return False

        try:
            _run_with_retry(conn, _ADD_COLUMN_PG, "release_photos.stage_at_upload")
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"\u2717 Gave up after {LOCK_RETRIES} attempts: could not get the lock on "
                    "'release_photos' — the table is under sustained load. Nothing was committed.\n"
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
    if "release_photos" not in inspector.get_table_names():
        print("\u2717 Table 'release_photos' does not exist. Run the base schema first.")
        return False
    existing = {c["name"] for c in inspector.get_columns("release_photos")}

    with engine.begin() as conn:
        if "stage_at_upload" not in existing:
            conn.execute(text(_ADD_COLUMN_SQLITE))
            print("\u2713 release_photos.stage_at_upload")
        else:
            print("release_photos.stage_at_upload already exists, skipping")
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
        print(f"\u2717 Database error during migration: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"\u2717 Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add release_photos.stage_at_upload (N9 photo stamp)."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
