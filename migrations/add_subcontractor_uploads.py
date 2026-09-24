"""
Subcontractor uploads (T3 sub portal): let a subcontractor account be the uploader
of a release photo and of a drawing version (the sub portal's "Upload file").

  release_photos.uploaded_by_user_id                       NOT NULL -> NULL
  release_photos.uploaded_by_subcontractor_id              new, nullable FK -> subcontractors(id)
  CHECK release_photos_one_uploader
  release_drawing_versions.uploaded_by_user_id             NOT NULL -> NULL
  release_drawing_versions.uploaded_by_subcontractor_id    new, nullable FK -> subcontractors(id)
  CHECK release_drawing_versions_one_uploader

Supersedes add_subcontractor_photo_uploads.py (same photo steps; safe if that ran).

DROP NOT NULL is instant; the ADD COLUMN is nullable with no default; the FK check
scans all-NULL rows; the CHECK is added NOT VALID then validated (SHARE UPDATE
EXCLUSIVE only); the index is built CONCURRENTLY on AUTOCOMMIT.

Usage:
    python migrations/add_subcontractor_uploads.py
    python migrations/add_subcontractor_uploads.py --database-url postgresql://...

Safety properties (Postgres) — see migrations/README.md: idempotent DDL, no schema
reflection under a lock, one AUTOCOMMIT connection, lock_timeout + retry.
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

# ADD COLUMN here is metadata-only (nullable, no default), so it needs the lock for
# only an instant — a short timeout plus a few retries beats blocking.
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


def _is_lock_timeout(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "lock" in msg and ("timeout" in msg or "not available" in msg or "55p03" in msg)


def _run_with_retry(conn, sql: str, label: str) -> None:
    """Execute one idempotent DDL statement, retrying on lock_timeout with backoff."""
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            conn.execute(text(sql))
            print(f"OK {label}")
            return
        except OperationalError as exc:
            if _is_lock_timeout(exc) and attempt < LOCK_RETRIES:
                delay = RETRY_BASE_SECONDS * attempt
                print(
                    f"  '{label}' couldn't get the lock (attempt {attempt}/{LOCK_RETRIES}); "
                    f"retrying in {delay}s — nothing committed, app keeps running"
                )
                time.sleep(delay)
                continue
            raise


def _migrate_postgres(engine) -> bool:
    # AUTOCOMMIT: each statement is its own transaction, so the ACCESS EXCLUSIVE lock the
    # ALTER needs is released the instant the statement finishes. No reflection involved.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        for table in ("subcontractors", "release_photos", "release_drawing_versions"):
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar() is None:
                print(f"FAILED Table '{table}' does not exist. Run the base schema first.")
                return False

        steps = [
            ("ALTER TABLE release_photos ALTER COLUMN uploaded_by_user_id DROP NOT NULL",
             "release_photos.uploaded_by_user_id nullable"),
            ("ALTER TABLE release_photos ADD COLUMN IF NOT EXISTS uploaded_by_subcontractor_id INTEGER "
             "REFERENCES subcontractors(id)",
             "release_photos.uploaded_by_subcontractor_id"),
            ("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_release_photos_uploaded_by_subcontractor_id "
             "ON release_photos (uploaded_by_subcontractor_id)",
             "ix_release_photos_uploaded_by_subcontractor_id"),
            ("ALTER TABLE release_drawing_versions ALTER COLUMN uploaded_by_user_id DROP NOT NULL",
             "release_drawing_versions.uploaded_by_user_id nullable"),
            ("ALTER TABLE release_drawing_versions ADD COLUMN IF NOT EXISTS uploaded_by_subcontractor_id INTEGER "
             "REFERENCES subcontractors(id)",
             "release_drawing_versions.uploaded_by_subcontractor_id"),
            ("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_release_drawing_versions_uploaded_by_subcontractor_id "
             "ON release_drawing_versions (uploaded_by_subcontractor_id)",
             "ix_release_drawing_versions_uploaded_by_subcontractor_id"),
        ]
        try:
            for sql, label in steps:
                _run_with_retry(conn, sql, label)

            for table in ("release_photos", "release_drawing_versions"):
                conname = f"{table}_one_uploader"
                exists = conn.execute(text(
                    "SELECT 1 FROM pg_constraint WHERE conname = :c"), {"c": conname}).scalar()
                if exists:
                    print(f"{conname} already exists, skipping")
                    continue
                _run_with_retry(
                    conn,
                    f"ALTER TABLE {table} ADD CONSTRAINT {conname} "
                    "CHECK ((uploaded_by_user_id IS NULL) <> (uploaded_by_subcontractor_id IS NULL)) NOT VALID",
                    f"{conname} (NOT VALID)",
                )
                _run_with_retry(conn, f"ALTER TABLE {table} VALIDATE CONSTRAINT {conname}", f"{conname} validated")
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"FAILED Gave up after {LOCK_RETRIES} attempts: could not get a lock. "
                    "Nothing from the failed statement was committed; earlier steps are "
                    "idempotent and safe to re-run.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # SQLite cannot DROP NOT NULL in place; a local SQLite dev DB should be recreated via
    # db.create_all() (tests already do). Only the additive column is applied here.
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table in ("subcontractors", "release_photos", "release_drawing_versions"):
        if table not in tables:
            print(f"FAILED Table '{table}' does not exist. Run the base schema first.")
            return False
    with engine.begin() as conn:
        for table in ("release_photos", "release_drawing_versions"):
            cols = {c["name"] for c in inspector.get_columns(table)}
            if "uploaded_by_subcontractor_id" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN uploaded_by_subcontractor_id INTEGER "
                                  "REFERENCES subcontractors(id)"))
                print(f"OK {table}.uploaded_by_subcontractor_id")
            else:
                print(f"{table}.uploaded_by_subcontractor_id already exists, skipping")
    print("NOTE SQLite: uploaded_by_user_id stays NOT NULL here; recreate the local DB "
          "with db.create_all() if you need sub uploads locally.")
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
        print(f"FAILED Database error during migration: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"FAILED Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Let subcontractor accounts upload release photos and drawing files."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
