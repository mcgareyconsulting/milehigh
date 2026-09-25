"""
Add agent-account columns to `users`: `is_agent` and `agent_sponsor_user_id`.

An external agent (e.g. a Grok bot) that performs actions in the Brain signs in with
its OWN user account, so every ReleaseEvents / SubmittalEvents / board / issue row it
writes carries the agent's users.id — never the sponsoring employee's. `is_agent`
marks the account (display names get an "(agent)" tag everywhere), and
`agent_sponsor_user_id` records which employee vouches for it (display-only).

This migration only adds the columns; nothing is backfilled. Create the account
afterwards with `scripts/create_agent_user.py`.

Usage:
    python migrations/add_agent_users.py
    python migrations/add_agent_users.py --database-url postgresql://...

Safety properties (Postgres) — mirrors migrations/add_start_install_to_dwl.py:
  - Every statement is idempotent (`ADD COLUMN IF NOT EXISTS`; the FK constraint is
    guarded by a pg_constraint lookup inside one DO block), so NO schema reflection.
  - One AUTOCOMMIT connection: each DDL is its own implicit transaction, so the
    ACCESS EXCLUSIVE lock is held only for the instant the statement runs.
  - `lock_timeout` makes a blocked ALTER fail fast and retry with backoff instead of
    queueing behind live traffic.
  - `ADD COLUMN ... DEFAULT false` on a non-volatile default is metadata-only on
    Postgres 11+, so it is instant even though it is NOT NULL.
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


# Idempotent DDL.
_PG_IS_AGENT = "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_agent BOOLEAN NOT NULL DEFAULT false"
_PG_SPONSOR = "ALTER TABLE users ADD COLUMN IF NOT EXISTS agent_sponsor_user_id INTEGER"
# The FK is added in its own guarded DO block so a re-run is a no-op. `users` is a
# tiny table, so the constraint validation scan is instant.
_PG_SPONSOR_FK = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_agent_sponsor_user_id'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT fk_users_agent_sponsor_user_id
            FOREIGN KEY (agent_sponsor_user_id) REFERENCES users (id);
    END IF;
END $$;
"""


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

        if conn.execute(text("SELECT to_regclass('users')")).scalar() is None:
            print("✗ Table 'users' does not exist. Run the base schema first.")
            return False

        try:
            _run_with_retry(conn, _PG_IS_AGENT, "users.is_agent")
            _run_with_retry(conn, _PG_SPONSOR, "users.agent_sponsor_user_id")
            _run_with_retry(conn, _PG_SPONSOR_FK, "users.agent_sponsor_user_id -> users.id FK")
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock on "
                    "'users' — the table is under sustained load. Nothing was committed.\n"
                    "  Re-run during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # SQLite is single-writer with no concurrent prod traffic. Older SQLite lacks
    # ADD COLUMN IF NOT EXISTS, so guard columns by inspection. No FK on SQLite:
    # SQLAlchemy does not need one at runtime and ALTER cannot add constraints there.
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        print("✗ Table 'users' does not exist. Run the base schema first.")
        return False
    existing = {c["name"] for c in inspector.get_columns("users")}

    with engine.begin() as conn:
        if "is_agent" not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_agent BOOLEAN NOT NULL DEFAULT 0"))
            print("✓ users.is_agent")
        else:
            print("users.is_agent already exists, skipping")
        if "agent_sponsor_user_id" not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN agent_sponsor_user_id INTEGER"))
            print("✓ users.agent_sponsor_user_id")
        else:
            print("users.agent_sponsor_user_id already exists, skipping")
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
        description="Add users.is_agent and users.agent_sponsor_user_id."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
