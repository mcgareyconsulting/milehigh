"""
Add submittal-keyed columns to the BB review tables so a review can be keyed to a Procore
submittal drawing (submittal_id + prostore attachment_id) with no job-log release involved.

On `bb_drawing_reviews` and `bb_review_feedback`:
  - ADD COLUMN submittal_id VARCHAR(64)   (Procore submittal id)
  - ADD COLUMN attachment_id BIGINT       (Procore prostore attachment id)
  - relax the previously-NOT-NULL release-keyed columns to nullable
    (drawing_version_id + release_id on the reviews table, release_id on feedback), so a
    submittal-keyed row can leave them null
  - index submittal_id and attachment_id on both tables

Nothing is backfilled.

Usage:
    python migrations/add_submittal_review_columns.py
    python migrations/add_submittal_review_columns.py --database-url postgresql://...

Safety properties (Postgres) — mirrors migrations/add_start_install_to_dwl.py, the reference:
  - Every statement is idempotent (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT
    EXISTS`, and `DROP NOT NULL`, which is a no-op on an already-nullable column), so the
    script needs NO schema reflection at all.
  - One AUTOCOMMIT connection: each DDL is its own implicit transaction, so the ACCESS
    EXCLUSIVE lock an ALTER needs is held only for the instant the statement runs, never
    across the whole migration and never while anything else runs.
  - `lock_timeout` makes a blocked ALTER FAIL FAST instead of queueing behind live traffic
    (which would block every later query on the table); it then auto-retries with backoff.
  - ADD COLUMN here is metadata-only (nullable, no default), so it needs the lock only for
    an instant.
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

# Postgres lock/retry tuning. The ALTERs here are metadata-only, so they need the lock for
# only an instant — a short timeout plus a few retries beats blocking. Total worst-case
# wait ≈ LOCK_RETRIES * (LOCK_RETRIES+1)/2 * RETRY_BASE_SECONDS.
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


# Idempotent Postgres DDL: (label, sql). ADD COLUMN / CREATE INDEX use IF NOT EXISTS;
# DROP NOT NULL is a no-op when the column is already nullable, so re-running is safe.
_PG_STATEMENTS = [
    ("bb_drawing_reviews.submittal_id",
     "ALTER TABLE bb_drawing_reviews ADD COLUMN IF NOT EXISTS submittal_id VARCHAR(64)"),
    ("bb_drawing_reviews.attachment_id",
     "ALTER TABLE bb_drawing_reviews ADD COLUMN IF NOT EXISTS attachment_id BIGINT"),
    ("bb_drawing_reviews.drawing_version_id nullable",
     "ALTER TABLE bb_drawing_reviews ALTER COLUMN drawing_version_id DROP NOT NULL"),
    ("bb_drawing_reviews.release_id nullable",
     "ALTER TABLE bb_drawing_reviews ALTER COLUMN release_id DROP NOT NULL"),
    ("bb_drawing_reviews.submittal_id index",
     "CREATE INDEX IF NOT EXISTS ix_bb_drawing_reviews_submittal_id "
     "ON bb_drawing_reviews (submittal_id)"),
    ("bb_drawing_reviews.attachment_id index",
     "CREATE INDEX IF NOT EXISTS ix_bb_drawing_reviews_attachment_id "
     "ON bb_drawing_reviews (attachment_id)"),
    ("bb_review_feedback.submittal_id",
     "ALTER TABLE bb_review_feedback ADD COLUMN IF NOT EXISTS submittal_id VARCHAR(64)"),
    ("bb_review_feedback.attachment_id",
     "ALTER TABLE bb_review_feedback ADD COLUMN IF NOT EXISTS attachment_id BIGINT"),
    ("bb_review_feedback.release_id nullable",
     "ALTER TABLE bb_review_feedback ALTER COLUMN release_id DROP NOT NULL"),
    ("bb_review_feedback.submittal_id index",
     "CREATE INDEX IF NOT EXISTS ix_bb_review_feedback_submittal_id "
     "ON bb_review_feedback (submittal_id)"),
    ("bb_review_feedback.attachment_id index",
     "CREATE INDEX IF NOT EXISTS ix_bb_review_feedback_attachment_id "
     "ON bb_review_feedback (attachment_id)"),
]

_TABLES = ("bb_drawing_reviews", "bb_review_feedback")


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
    # ALTER needs is released the instant the statement finishes. No reflection involved.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        for tbl in _TABLES:
            if conn.execute(text(f"SELECT to_regclass('{tbl}')")).scalar() is None:
                print(f"✗ Table '{tbl}' does not exist. Run the base schema first.")
                return False

        try:
            for label, sql in _PG_STATEMENTS:
                _run_with_retry(conn, sql, label)
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock on a BB "
                    "review table — it's under sustained load. Nothing was committed.\n"
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
    # SQLite can't ALTER a column's NOT NULL in place; nullability is handled by the model
    # on a fresh create_all, so we only add the new columns + indexes here.
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for tbl in _TABLES:
        if tbl not in tables:
            print(f"✗ Table '{tbl}' does not exist. Run the base schema first.")
            return False

    add_cols = {
        "bb_drawing_reviews": [("submittal_id", "VARCHAR(64)"), ("attachment_id", "BIGINT")],
        "bb_review_feedback": [("submittal_id", "VARCHAR(64)"), ("attachment_id", "BIGINT")],
    }
    indexes = [
        ("ix_bb_drawing_reviews_submittal_id", "bb_drawing_reviews", "submittal_id"),
        ("ix_bb_drawing_reviews_attachment_id", "bb_drawing_reviews", "attachment_id"),
        ("ix_bb_review_feedback_submittal_id", "bb_review_feedback", "submittal_id"),
        ("ix_bb_review_feedback_attachment_id", "bb_review_feedback", "attachment_id"),
    ]

    with engine.begin() as conn:
        for tbl, cols in add_cols.items():
            existing = {c["name"] for c in inspector.get_columns(tbl)}
            for name, ddl_type in cols:
                if name in existing:
                    print(f"{tbl}.{name} already exists, skipping")
                else:
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {name} {ddl_type}"))
                    print(f"✓ {tbl}.{name}")
        for idx_name, tbl, col in indexes:
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ({col})"
            ))
            print(f"✓ {idx_name}")
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
        description="Add submittal-keyed columns/indexes to the BB review tables."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
