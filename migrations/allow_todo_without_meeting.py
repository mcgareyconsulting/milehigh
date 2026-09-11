"""
Allow a to-do to exist without a meeting: drop NOT NULL on `checklist_items.meeting_id`.

Every checklist item used to come from a meeting transcript, so the FK was mandatory.
Carmen can now create a to-do directly from a conversation ("leave a to-do for Gary to
follow up with Drexel on this order"), which has no meeting behind it. Extractor rows are
unchanged and still carry their meeting_id; a NULL means the to-do was raised by hand.

Nothing is backfilled and no data is rewritten — this is a constraint change only.

Usage:
    python migrations/allow_todo_without_meeting.py
    python migrations/allow_todo_without_meeting.py --database-url postgresql://...

Safety properties (Postgres):
  - `DROP NOT NULL` is a catalog-only change: no table rewrite, no scan, lock held for an
    instant. Re-running it on an already-nullable column is a no-op, so the script is
    idempotent WITHOUT any schema reflection — never call inspect() while holding a lock.
  - One AUTOCOMMIT connection, one statement per implicit transaction.
  - `lock_timeout` makes a blocked ALTER fail fast rather than queue behind live traffic
    and block every later query on checklist_items; it retries with backoff.
"""

import argparse
import os
import sys
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

from sqlalchemy import create_engine, inspect, text
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

        if conn.execute(text("SELECT to_regclass('checklist_items')")).scalar() is None:
            print("✗ Table 'checklist_items' does not exist. Run the base schema first.")
            return False

        try:
            # Idempotent by nature: dropping NOT NULL on an already-nullable column is a
            # no-op, so no reflection is needed to decide whether to run it.
            _run_with_retry(
                conn,
                "ALTER TABLE checklist_items ALTER COLUMN meeting_id DROP NOT NULL",
                "checklist_items.meeting_id is now nullable",
            )
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock on "
                    "'checklist_items'. Nothing was committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # SQLite can't ALTER a column's nullability. Local/test databases are rebuilt from
    # the models by db.create_all(), which already reflects the change, so there is
    # nothing to do here beyond reporting.
    inspector = inspect(engine)
    if "checklist_items" not in inspector.get_table_names():
        print("✗ Table 'checklist_items' does not exist. Run the base schema first.")
        return False
    cols = {c["name"]: c for c in inspector.get_columns("checklist_items")}
    col = cols.get("meeting_id")
    if col is None:
        print("✗ Column 'checklist_items.meeting_id' not found.")
        return False
    if col.get("nullable"):
        print("✓ checklist_items.meeting_id is already nullable")
        return True
    print(
        "! SQLite cannot ALTER column nullability in place.\n"
        "  This database predates the change. Recreate it from the models "
        "(db.create_all() on a fresh file) — no production data lives in SQLite."
    )
    return False


def migrate(database_url: str = None) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {_mask(db_url)}")

    engine = create_engine(db_url)
    try:
        if engine.dialect.name == "sqlite":
            return _migrate_sqlite(engine)
        return _migrate_postgres(engine)
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", dest="database_url", default=None,
                        help="Target database URL (defaults to env/.env resolution).")
    args = parser.parse_args()
    try:
        ok = migrate(args.database_url)
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"✗ Migration failed: {exc}")
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
