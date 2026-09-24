"""
Rename the release stage string 'Paint Complete' -> 'Paint QC' everywhere it is stored
as data (app-code renames of the stage itself are a separate, concurrent change).

The Trello list name 'Paint complete' (lowercase c, `releases.trello_list_name` /
`jobs.trello_list_name`) is NOT part of this rename and must never be touched here.

Touches, all idempotent (re-running finds 0 rows):
  1. releases.stage
  2. release_photos.stage  (the optional stage-gate photo tag)
  3. release_events.payload — for action='update_stage' rows, the top-level 'from',
     'to' and 'via' keys, when their value is exactly 'Paint Complete'. `payload` is
     `db.JSON` (plain `json`, not `jsonb`, on Postgres — see app/models.py
     ReleaseEvents), so this can't use `jsonb_set` directly against the column. Rows
     are loaded and rewritten in Python (bounded to the 'update_stage' action rows
     whose payload actually mentions the old value — ~232 in sandbox as of 2026-09-23,
     a few thousand in prod) and written back per-row, either as a `json` cast
     (Postgres) or a plain string (SQLite, which has no native JSON column type).
  4. job_change_logs.from_value / job_change_logs.to_value (legacy audit table)

Usage:
    python migrations/rename_paint_complete_to_paint_qc.py
    python migrations/rename_paint_complete_to_paint_qc.py --database-url postgresql://...
    python migrations/rename_paint_complete_to_paint_qc.py --dry-run

Safety properties (Postgres):
  - One AUTOCOMMIT connection; every write is its own implicit transaction, so any
    row/table lock is held only for the instant that statement runs.
  - `lock_timeout` makes a blocked statement FAIL FAST instead of queueing behind live
    traffic, and it auto-retries with backoff.
  - No schema reflection — table presence is checked with `to_regclass`, a catalog
    lookup that never blocks, not `inspect()`/`get_columns()`.
  - Every WHERE clause names the exact old value, so a second run touches 0 rows.
"""

import argparse
import json
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

OLD_STAGE = "Paint Complete"
NEW_STAGE = "Paint QC"

# The three top-level payload keys update_stage events carry that can hold a stage name.
PAYLOAD_STAGE_KEYS = ("from", "to", "via")

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


def _run_with_retry(conn, stmt, label: str):
    """Execute one idempotent statement, retrying on lock_timeout with backoff. Prints."""
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


def _execute_with_retry(conn, stmt):
    """Same retry policy as _run_with_retry but silent on success — used in the
    per-row payload loop so a few thousand rows don't spam a few thousand print lines."""
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            return conn.execute(stmt)
        except OperationalError as exc:
            if _is_lock_timeout(exc) and attempt < LOCK_RETRIES:
                delay = RETRY_BASE_SECONDS * attempt
                print(
                    f"  ⏳ release_events row update couldn't get the lock "
                    f"(attempt {attempt}/{LOCK_RETRIES}); retrying in {delay}s"
                )
                time.sleep(delay)
                continue
            raise


def _rename_column_value(conn, table: str, column: str, dry_run: bool) -> int:
    """UPDATE <table> SET <column> = NEW_STAGE WHERE <column> = OLD_STAGE. Idempotent."""
    count_sql = text(f"SELECT count(*) FROM {table} WHERE {column} = :old").bindparams(old=OLD_STAGE)
    pending = conn.execute(count_sql).scalar() or 0
    print(f"{table}.{column} = {OLD_STAGE!r}: {pending} row(s)")
    if pending == 0:
        return 0
    if dry_run:
        print("  dry run: no rows written")
        return pending

    update_sql = text(
        f"UPDATE {table} SET {column} = :new WHERE {column} = :old"
    ).bindparams(old=OLD_STAGE, new=NEW_STAGE)
    result = _run_with_retry(conn, update_sql, f"{table}.{column} -> {NEW_STAGE!r}")
    print(f"  {result.rowcount} row(s) updated")
    return result.rowcount


def _load_payload(raw):
    """release_events.payload comes back as a dict on Postgres (psycopg2 adapts json/
    jsonb automatically) and as a JSON-text string on SQLite (no native JSON column
    type — flask-sqlalchemy's JSON type only (de)serializes through the ORM, not on a
    raw SQL read)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None
    return None


def _find_payload_rewrites(conn):
    """Return [(id, new_payload_dict), ...] for update_stage rows whose payload has
    'from'/'to'/'via' == OLD_STAGE. Scoped to action='update_stage' to keep the
    candidate set bounded (~232 rows in sandbox, a few thousand in prod)."""
    rows = conn.execute(
        text("SELECT id, payload FROM release_events WHERE action = 'update_stage'")
    ).all()

    rewrites = []
    for row in rows:
        payload = _load_payload(row.payload)
        if not isinstance(payload, dict):
            continue
        changed = False
        for key in PAYLOAD_STAGE_KEYS:
            if payload.get(key) == OLD_STAGE:
                payload[key] = NEW_STAGE
                changed = True
        if changed:
            rewrites.append((row.id, payload))
    return rewrites


def _rewrite_release_event_payloads(conn, dialect_name: str, dry_run: bool) -> int:
    rewrites = _find_payload_rewrites(conn)
    print(
        f"release_events.payload (action=update_stage, from/to/via = {OLD_STAGE!r}): "
        f"{len(rewrites)} row(s)"
    )
    if not rewrites:
        return 0
    if dry_run:
        print("  dry run: no rows written")
        return len(rewrites)

    if dialect_name == "postgresql":
        update_sql = text("UPDATE release_events SET payload = CAST(:payload AS JSON) WHERE id = :id")
    else:
        update_sql = text("UPDATE release_events SET payload = :payload WHERE id = :id")

    updated = 0
    for event_id, payload in rewrites:
        stmt = update_sql.bindparams(payload=json.dumps(payload), id=event_id)
        _execute_with_retry(conn, stmt)
        updated += 1
    print(f"  {updated} row(s) updated")
    return updated


def _run_all(conn, dialect_name: str, dry_run: bool) -> None:
    _rename_column_value(conn, "releases", "stage", dry_run)
    _rename_column_value(conn, "release_photos", "stage", dry_run)
    _rewrite_release_event_payloads(conn, dialect_name, dry_run)
    _rename_column_value(conn, "job_change_logs", "from_value", dry_run)
    _rename_column_value(conn, "job_change_logs", "to_value", dry_run)


def _migrate_postgres(engine, dry_run: bool) -> bool:
    # AUTOCOMMIT: every write above is its own transaction, so any lock it takes is
    # released the instant that statement finishes — never held across the script.
    # to_regclass is a catalog lookup, not reflection: it can't self-deadlock.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        for table in ("releases", "release_photos", "release_events", "job_change_logs"):
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar() is None:
                print(f"✗ Table '{table}' does not exist. Run the base schema first.")
                return False

        try:
            _run_all(conn, "postgresql", dry_run)
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get a lock — "
                    "a table is under sustained load. Nothing further was committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine, dry_run: bool) -> bool:
    # SQLite is single-writer with no concurrent prod traffic, so lock contention isn't
    # a concern here; a plain inspector check is fine (this path never touches Postgres).
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in ("releases", "release_photos", "release_events", "job_change_logs"):
        if table not in existing_tables:
            print(f"✗ Table '{table}' does not exist. Run the base schema first.")
            return False

    with engine.begin() as conn:
        _run_all(conn, "sqlite", dry_run)
    return True


def migrate(database_url: str = None, dry_run: bool = False) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {_mask(db_url)}")
    if dry_run:
        print("Dry run: counting only, no writes.")

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
        description=(
            "Rename release stage 'Paint Complete' -> 'Paint QC' in releases.stage, "
            "release_photos.stage, release_events.payload (update_stage from/to/via) "
            "and job_change_logs.from_value/to_value. Never touches trello_list_name."
        )
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
