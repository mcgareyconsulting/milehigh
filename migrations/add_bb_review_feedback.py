"""
Add the `bb_review_feedback` table: one row per PM accept/deny (+ optional notes) on a
single finding of a Banana Boy review (app/models.py BBReviewFeedback). This is the
training loop — PM decisions are landed here with the finding snapshot + review/release
context so they can be ingested into the rule library later. One row per
(review_id, finding_index); the app upserts.

This migration only creates the table + its indexes; nothing is backfilled.

Usage:
    python migrations/add_bb_review_feedback.py
    python migrations/add_bb_review_feedback.py --database-url postgresql://...

Safety properties (Postgres) — clones migrations/add_bb_drawing_reviews.py:
  - Idempotent DDL (`CREATE TABLE/INDEX IF NOT EXISTS`), so NO schema reflection.
  - One AUTOCOMMIT connection: each statement is its own transaction; this is a brand-new
    empty table, so locks are held only for the instant each statement runs.
  - `lock_timeout` makes any blocked statement fail fast and auto-retry with backoff.
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


# Idempotent DDL — works on both Postgres and modern SQLite. Inline REFERENCES are safe
# here because the table is brand-new and empty (no backfill lock on the parents).
_TABLE = """
    CREATE TABLE IF NOT EXISTS bb_review_feedback (
        id {pk},
        review_id INTEGER NOT NULL
            REFERENCES bb_drawing_reviews (id) ON DELETE CASCADE,
        release_id INTEGER NOT NULL REFERENCES releases (id),
        drawing_version_id INTEGER,
        finding_index INTEGER NOT NULL,
        rule_id VARCHAR(64),
        decision VARCHAR(16) NOT NULL,
        notes TEXT,
        finding_snapshot JSON,
        user_id INTEGER REFERENCES users (id),
        created_at TIMESTAMP DEFAULT NULL,
        updated_at TIMESTAMP DEFAULT NULL
    )
"""
_IDX_REVIEW = (
    "CREATE INDEX IF NOT EXISTS ix_bb_review_feedback_review_id "
    "ON bb_review_feedback (review_id)"
)
_IDX_RELEASE = (
    "CREATE INDEX IF NOT EXISTS ix_bb_review_feedback_release_id "
    "ON bb_review_feedback (release_id)"
)
# One feedback row per finding per review; the app upserts on this pair.
_IDX_UNIQUE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS _bb_review_feedback_finding_uc "
    "ON bb_review_feedback (review_id, finding_index)"
)


def _is_lock_timeout(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "lock" in msg and ("timeout" in msg or "not available" in msg or "55p03" in msg)


def _run_with_retry(conn, sql: str, label: str) -> None:
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

        if conn.execute(text("SELECT to_regclass('bb_drawing_reviews')")).scalar() is None:
            print("✗ Table 'bb_drawing_reviews' does not exist. Run add_bb_drawing_reviews.py first.")
            return False

        try:
            _run_with_retry(conn, _TABLE.format(pk="SERIAL PRIMARY KEY"), "bb_review_feedback table")
            _run_with_retry(conn, _IDX_REVIEW, "bb_review_feedback.review_id index")
            _run_with_retry(conn, _IDX_RELEASE, "bb_review_feedback.release_id index")
            _run_with_retry(conn, _IDX_UNIQUE, "bb_review_feedback (review_id, finding_index) unique index")
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts to get a lock. Nothing committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    inspector = inspect(engine)
    if "bb_drawing_reviews" not in inspector.get_table_names():
        print("✗ Table 'bb_drawing_reviews' does not exist. Run add_bb_drawing_reviews.py first.")
        return False

    with engine.begin() as conn:
        conn.execute(text(_TABLE.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT")))
        conn.execute(text(_IDX_REVIEW))
        conn.execute(text(_IDX_RELEASE))
        conn.execute(text(_IDX_UNIQUE))
        print("✓ bb_review_feedback table + indexes")
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
    parser = argparse.ArgumentParser(description="Create the bb_review_feedback table.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
