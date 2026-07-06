"""
Add the BB (Banana Boy) read-only chat feature:
  - `users.is_bb_chat` — per-user access flag for the phase-1 rollout
  - `bb_chat_conversations` — one row per chat thread, owned by a user
  - `bb_chat_messages` — one row per turn, with per-turn spend telemetry
    (Anthropic request-id, model, token counts, USD cost, duration) on assistant turns
  - seeds the two pilot users (boneill@mhmw.com, mcgareyconsulting@gmail.com) to
    is_bb_chat = true so they have access immediately after the migration runs

Nothing else is backfilled. Re-running is safe (idempotent DDL; the seed UPDATE just
re-asserts the flag).

Usage:
    python migrations/add_bb_chat.py
    python migrations/add_bb_chat.py --database-url postgresql://...

Safety properties mirror migrations/add_start_install_to_dwl.py exactly:
  - Idempotent DDL only (ADD COLUMN / CREATE TABLE / CREATE INDEX IF NOT EXISTS) — no
    schema reflection on Postgres, so no self-deadlock against our own ACCESS EXCLUSIVE lock.
  - One AUTOCOMMIT connection: each DDL is its own implicit transaction; the exclusive
    lock is held for only an instant.
  - lock_timeout makes a blocked ALTER fail fast, then auto-retry with backoff.
  - ADD COLUMN is metadata-only (nullable, no volatile default) so it's instant.
  - The connection URL is masked in logs.
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

# Pilot users granted access at migration time. Usernames are stored lowercased.
SEED_USERS = ["boneill@mhmw.com", "mcgareyconsulting@gmail.com"]

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
_CONVERSATIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS bb_chat_conversations (
        id {pk},
        user_id INTEGER NOT NULL,
        title VARCHAR(255),
        anchor_kind VARCHAR(16),
        anchor_job INTEGER,
        anchor_release VARCHAR(16),
        anchor_submittal_id VARCHAR(255),
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    )
"""
_CONVERSATIONS_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_bb_chat_conversations_user_id "
    "ON bb_chat_conversations (user_id)"
)
_MESSAGES_TABLE = """
    CREATE TABLE IF NOT EXISTS bb_chat_messages (
        id {pk},
        conversation_id INTEGER NOT NULL,
        role VARCHAR(16) NOT NULL,
        content TEXT,
        created_at TIMESTAMP,
        anthropic_request_id VARCHAR(64),
        model VARCHAR(64),
        input_tokens INTEGER,
        output_tokens INTEGER,
        cache_read_tokens INTEGER,
        cache_write_tokens INTEGER,
        cost_usd DOUBLE PRECISION,
        duration_ms INTEGER,
        tool_calls INTEGER
    )
"""
_MESSAGES_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_bb_chat_messages_conversation_id "
    "ON bb_chat_messages (conversation_id)"
)
_MESSAGES_REQID_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_bb_chat_messages_request_id "
    "ON bb_chat_messages (anthropic_request_id)"
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


def _seed_sql():
    # SQLite has no DOUBLE PRECISION quirks; both dialects accept this UPDATE.
    placeholders = ", ".join(f":u{i}" for i in range(len(SEED_USERS)))
    params = {f"u{i}": u for i, u in enumerate(SEED_USERS)}
    sql = (
        f"UPDATE users SET is_bb_chat = {{true}} "
        f"WHERE lower(username) IN ({placeholders})"
    )
    return sql, params


def _migrate_postgres(engine) -> bool:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        if conn.execute(text("SELECT to_regclass('users')")).scalar() is None:
            print("✗ Table 'users' does not exist. Run the base schema first.")
            return False

        try:
            _run_with_retry(
                conn,
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_bb_chat BOOLEAN NOT NULL DEFAULT false",
                "users.is_bb_chat",
            )
            _run_with_retry(conn, _CONVERSATIONS_TABLE.format(pk="SERIAL PRIMARY KEY"), "bb_chat_conversations table")
            _run_with_retry(conn, _CONVERSATIONS_INDEX, "bb_chat_conversations.user_id index")
            _run_with_retry(conn, _MESSAGES_TABLE.format(pk="SERIAL PRIMARY KEY"), "bb_chat_messages table")
            _run_with_retry(conn, _MESSAGES_INDEX, "bb_chat_messages.conversation_id index")
            _run_with_retry(conn, _MESSAGES_REQID_INDEX, "bb_chat_messages.request_id index")
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

        sql, params = _seed_sql()
        result = conn.execute(text(sql.format(true="true")), params)
        print(f"✓ seeded is_bb_chat for pilot users ({result.rowcount} row(s) matched)")
    return True


def _migrate_sqlite(engine) -> bool:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        print("✗ Table 'users' does not exist. Run the base schema first.")
        return False
    existing = {c["name"] for c in inspector.get_columns("users")}

    with engine.begin() as conn:
        if "is_bb_chat" not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_bb_chat BOOLEAN NOT NULL DEFAULT 0"))
            print("✓ users.is_bb_chat")
        else:
            print("users.is_bb_chat already exists, skipping")

        conn.execute(text(_CONVERSATIONS_TABLE.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT")))
        conn.execute(text(_CONVERSATIONS_INDEX))
        conn.execute(text(_MESSAGES_TABLE.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT")))
        conn.execute(text(_MESSAGES_INDEX))
        conn.execute(text(_MESSAGES_REQID_INDEX))
        print("✓ bb_chat_conversations + bb_chat_messages tables + indexes")

        sql, params = _seed_sql()
        result = conn.execute(text(sql.format(true="1")), params)
        print(f"✓ seeded is_bb_chat for pilot users ({result.rowcount} row(s) matched)")
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
        description="Add the BB chat access flag, conversation/message tables, and seed pilot users."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
