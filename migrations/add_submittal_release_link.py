"""
Add submittal→release link columns for the Submittal Matching review tool.

Adds to `submittals`:
  - linked_release_id INTEGER NULL  — loose reference to releases.id (deliberately no FK:
    the link must survive the release being archived or soft-deleted, since historical
    matching is the whole point of the tool)
  - link_status VARCHAR(16) NOT NULL DEFAULT ''  — '' unreviewed | 'linked' | 'no_match'

Plus an index on linked_release_id. Nothing is backfilled; links are created by admins
through /brain/submittal-matching.

Usage:
    python migrations/add_submittal_release_link.py
    python migrations/add_submittal_release_link.py --database-url postgresql://...

Safety properties (Postgres):
  - Every statement is idempotent (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT
    EXISTS`), so the script needs NO schema reflection — no second pooled connection
    that could self-block behind our own ACCESS EXCLUSIVE lock.
  - One AUTOCOMMIT connection: each DDL is its own implicit transaction, so the
    exclusive lock is held only for the instant the statement runs.
  - `lock_timeout` makes a blocked ALTER fail fast instead of queueing behind live
    traffic; it auto-retries with backoff.
  - Both ADD COLUMNs are metadata-only (nullable / constant default), so they're instant.
"""

import argparse
import os
import sys
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

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


_ADD_LINKED_RELEASE_ID = (
    "ALTER TABLE submittals ADD COLUMN IF NOT EXISTS linked_release_id INTEGER"
)
_ADD_LINK_STATUS = (
    "ALTER TABLE submittals ADD COLUMN IF NOT EXISTS "
    "link_status VARCHAR(16) NOT NULL DEFAULT ''"
)
_ADD_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_submittals_linked_release_id "
    "ON submittals (linked_release_id)"
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
    # ALTER needs is released the instant the statement finishes. No reflection involved.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        if conn.execute(text("SELECT to_regclass('submittals')")).scalar() is None:
            print("✗ Table 'submittals' does not exist. Run the base schema first.")
            return False

        _run_with_retry(conn, _ADD_LINKED_RELEASE_ID, "submittals.linked_release_id column")
        _run_with_retry(conn, _ADD_LINK_STATUS, "submittals.link_status column")
        _run_with_retry(conn, _ADD_INDEX, "ix_submittals_linked_release_id index")
    return True


def _sqlite_has_column(conn, table: str, column: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _migrate_sqlite(engine) -> bool:
    # SQLite (local dev / tests): ADD COLUMN IF NOT EXISTS isn't supported everywhere,
    # so check via PRAGMA (single connection, no lock hazard in SQLite).
    with engine.connect() as conn:
        if not conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='submittals'")
        ).fetchone():
            print("✗ Table 'submittals' does not exist. Run the base schema first.")
            return False

        if _sqlite_has_column(conn, "submittals", "linked_release_id"):
            print("• submittals.linked_release_id already exists — skipped")
        else:
            conn.execute(text("ALTER TABLE submittals ADD COLUMN linked_release_id INTEGER"))
            print("✓ submittals.linked_release_id column")

        if _sqlite_has_column(conn, "submittals", "link_status"):
            print("• submittals.link_status already exists — skipped")
        else:
            conn.execute(
                text("ALTER TABLE submittals ADD COLUMN link_status VARCHAR(16) NOT NULL DEFAULT ''")
            )
            print("✓ submittals.link_status column")

        conn.execute(text(_ADD_INDEX))
        print("✓ ix_submittals_linked_release_id index")
        conn.commit()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override the inferred database URL")
    args = parser.parse_args()

    url = infer_database_url(args.database_url)
    print(f"→ migrating {_mask(url)}")

    engine = create_engine(url)
    try:
        if url.startswith("sqlite"):
            ok = _migrate_sqlite(engine)
        else:
            ok = _migrate_postgres(engine)
    finally:
        engine.dispose()

    print("done." if ok else "aborted.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
