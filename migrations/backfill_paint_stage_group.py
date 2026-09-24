"""
Backfill `releases.stage_group = 'PAINT'` for the two Paint-department stages.

On 2026-09-23 (T13, the department photo gate) PAINT was split out of READY_TO_SHIP in
`app/api/helpers.py STAGE_TO_GROUP`: `Welded QC` and `Paint Start` now map to PAINT so the
Fab → Paint and Paint → Ship handoffs are both department boundaries. `stage_group` is a
stored, derived column — every stage write recomputes it — so rows already sitting at those
two stages keep the old value until they next change stage. This script brings them in
line. DB-side readers of the column (the installer-timeline query, the FABRICATION-scoped
scheduling recalc) are what need it; the API already serializes the group from the stage.

Data only: no DDL, no schema reflection, one idempotent UPDATE. Re-running is a no-op.

Usage:
    python migrations/backfill_paint_stage_group.py
    python migrations/backfill_paint_stage_group.py --database-url postgresql://...
    python migrations/backfill_paint_stage_group.py --dry-run

Safety properties (Postgres):
  - One AUTOCOMMIT connection; the UPDATE is its own transaction, so its row locks are
    held only for the instant the statement runs.
  - `lock_timeout` makes a blocked statement FAIL FAST instead of queueing behind live
    traffic, and it auto-retries with backoff.
  - The WHERE clause names the exact stages and skips rows already at PAINT, so the
    write touches only what it has to (43 rows in sandbox on 2026-09-23).
"""

import argparse
import os
import sys
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

LOCK_TIMEOUT = "5s"
STATEMENT_TIMEOUT = "30s"
LOCK_RETRIES = 4
RETRY_BASE_SECONDS = 3

# Must match app/api/helpers.py STAGE_TO_GROUP — the two stages whose group is PAINT.
PAINT_STAGES = ("Welded QC", "Paint Start")

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


_STAGES_PARAM = bindparam("stages", value=list(PAINT_STAGES), expanding=True)

_COUNT_SQL = text(
    "SELECT count(*) FROM releases "
    "WHERE stage IN :stages AND (stage_group IS NULL OR stage_group <> 'PAINT')"
).bindparams(_STAGES_PARAM)

_UPDATE_SQL = text(
    "UPDATE releases SET stage_group = 'PAINT' "
    "WHERE stage IN :stages AND (stage_group IS NULL OR stage_group <> 'PAINT')"
).bindparams(_STAGES_PARAM)


def _is_lock_timeout(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "lock" in msg and ("timeout" in msg or "not available" in msg or "55p03" in msg)


def _run_with_retry(conn, stmt, label: str):
    """Execute one idempotent statement, retrying on lock_timeout with backoff."""
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            result = conn.execute(stmt)
            print(f"✓ {label}")
            return result
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


def _backfill(conn, dry_run: bool) -> bool:
    pending = conn.execute(_COUNT_SQL).scalar() or 0
    print(f"Rows at {' / '.join(PAINT_STAGES)} not yet in PAINT: {pending}")
    if pending == 0:
        print("Nothing to do — already backfilled.")
        return True
    if dry_run:
        print("Dry run: no rows written.")
        return True
    result = _run_with_retry(conn, _UPDATE_SQL, "releases.stage_group → PAINT")
    print(f"  {result.rowcount} row(s) updated")
    return True


def _migrate_postgres(engine, dry_run: bool) -> bool:
    # AUTOCOMMIT: the UPDATE is its own transaction, row locks released the instant it
    # finishes — never held across the script, and no schema reflection anywhere.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        if conn.execute(text("SELECT to_regclass('releases')")).scalar() is None:
            print("✗ Table 'releases' does not exist. Run the base schema first.")
            return False
        try:
            return _backfill(conn, dry_run)
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


def _migrate_sqlite(engine, dry_run: bool) -> bool:
    with engine.begin() as conn:
        return _backfill(conn, dry_run)


def migrate(database_url: str = None, dry_run: bool = False) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {_mask(db_url)}")

    engine = create_engine(db_url)
    try:
        if engine.dialect.name == "sqlite":
            return _migrate_sqlite(engine, dry_run)
        return _migrate_postgres(engine, dry_run)
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
        description="Backfill releases.stage_group='PAINT' for Welded QC / Paint Start rows."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count the rows that would change and exit without writing.",
    )
    args = parser.parse_args()

    success = migrate(args.database_url, dry_run=args.dry_run)
    sys.exit(0 if success else 1)
