"""
Add the supplier-order extractor columns to `material_orders`:
  - supplier_order_no  VARCHAR(64)  — the supplier's own order/confirmation number
                                      (e.g. Dencol Order #2296464)
  - event_type         VARCHAR(16)  — 'placed' | 'confirmed' (seeds the future
                                      request↔confirm lifecycle)
  - unit_price         DOUBLE PRECISION — per-line price from a supplier confirm table
  - extended_price     DOUBLE PRECISION — per-line extended price

All four are nullable with no default, so each ADD COLUMN is metadata-only and
instant. Nothing is backfilled — existing rows keep NULLs.

Usage:
    python migrations/add_material_order_extractor_columns.py
    python migrations/add_material_order_extractor_columns.py --database-url postgresql://...

Safety properties (Postgres) — see migrations/add_start_install_to_dwl.py for the
full rationale; the same rules apply here:
  - Idempotent `ADD COLUMN IF NOT EXISTS` only — NO schema reflection on Postgres.
  - One AUTOCOMMIT connection: each ALTER is its own implicit transaction, so the
    ACCESS EXCLUSIVE lock is held only for the instant the statement runs.
  - `lock_timeout` makes a blocked ALTER fail fast (then auto-retries with backoff)
    instead of queueing behind live traffic.
  - The DB URL is masked in logs.
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

# (column, postgres type, sqlite type) — keep names in sync with app/models.py MaterialOrder.
COLUMNS = [
    ("supplier_order_no", "VARCHAR(64)", "VARCHAR(64)"),
    ("event_type", "VARCHAR(16)", "VARCHAR(16)"),
    ("unit_price", "DOUBLE PRECISION", "FLOAT"),
    ("extended_price", "DOUBLE PRECISION", "FLOAT"),
]


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

        if conn.execute(text("SELECT to_regclass('material_orders')")).scalar() is None:
            print("✗ Table 'material_orders' does not exist. Run the base schema first.")
            return False

        try:
            for name, pg_type, _ in COLUMNS:
                _run_with_retry(
                    conn,
                    f"ALTER TABLE material_orders ADD COLUMN IF NOT EXISTS {name} {pg_type}",
                    f"material_orders.{name}",
                )
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock on "
                    "'material_orders' — the table is under sustained load. Nothing was committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # Older SQLite lacks ADD COLUMN IF NOT EXISTS, so guard columns by inspection.
    inspector = inspect(engine)
    if "material_orders" not in inspector.get_table_names():
        print("✗ Table 'material_orders' does not exist. Run the base schema first.")
        return False
    existing = {c["name"] for c in inspector.get_columns("material_orders")}

    with engine.begin() as conn:
        for name, _, sqlite_type in COLUMNS:
            if name in existing:
                print(f"material_orders.{name} already exists, skipping")
                continue
            conn.execute(text(f"ALTER TABLE material_orders ADD COLUMN {name} {sqlite_type}"))
            print(f"✓ material_orders.{name}")
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
        description="Add supplier-order extractor columns to material_orders."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
