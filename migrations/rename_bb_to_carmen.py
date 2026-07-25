"""
Rename the BB / "Banana Boy" database objects to Carmen Miranda.

Part of the BB → Carmen Miranda rebrand (docs/carmen-miranda-rename-scope.md,
Tier C1). This renames SCHEMA OBJECTS ONLY — all metadata-only catalog updates,
no row rewrites — so it is effectively instant and holds locks only for an instant:

Tables:
    bb_chat_conversations  -> carmen_chat_conversations
    bb_chat_messages       -> carmen_chat_messages
    bb_drawing_reviews     -> carmen_drawing_reviews
    bb_review_feedback     -> carmen_review_feedback
Columns:
    users.is_bb_chat                    -> users.is_carmen_chat
    notifications.bb_drawing_review_id  -> notifications.carmen_drawing_review_id
Indexes (renamed to match; FK/PK constraint *names* keep their old prefix — cosmetic,
    they still work, and renaming them buys nothing).

NOT touched — deliberately: the opaque persisted STRING VALUES
`ai_usage.feature = 'bb_chat'`, `ai_usage.entity_type = 'bb_chat_message'`, and
`notifications.type = 'bb_review'`. Those are internal category strings, never shown
to a user and never branched on (only written), so renaming them would mean UPDATE-ing
every row (ai_usage grows with every AI call) for zero visible benefit. Keeping them
opaque is what keeps THIS migration metadata-only. If you ever want them backfilled,
that's a separate, batched data migration.

This migration must ship WITH the matching code (models.py table/column names, the
app/brain/carmen_chat/ module, the /carmen-* routes, the is_carmen_chat API field).
Running it against a deploy still on the old code will break the app — deploy the
branch and run this together (brief window; single-instance is fine).

Usage:
    python migrations/rename_bb_to_carmen.py
    python migrations/rename_bb_to_carmen.py --database-url postgresql://...

Safety properties (Postgres) — mirrors migrations/add_start_install_to_dwl.py:
  - Every statement is a guarded DO block / `ALTER ... IF EXISTS`, so the script is
    fully idempotent and needs NO Python-side schema reflection (which is what froze a
    table once: inspect() on a SECOND pooled connection while the FIRST held ACCESS
    EXCLUSIVE — an undetectable self-block).
  - One AUTOCOMMIT connection: each statement is its own transaction, so a rename's
    ACCESS EXCLUSIVE lock is held only for the instant it runs.
  - `lock_timeout` makes a blocked rename FAIL FAST instead of queueing behind live
    traffic; it then auto-retries with backoff, so transient contention self-heals.
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

# (old, new) — order doesn't matter; each is independently guarded. FKs track tables by
# OID, so renaming a referenced table (bb_drawing_reviews) needs no FK drop/recreate.
TABLE_RENAMES = [
    ("bb_chat_conversations", "carmen_chat_conversations"),
    ("bb_chat_messages", "carmen_chat_messages"),
    ("bb_drawing_reviews", "carmen_drawing_reviews"),
    ("bb_review_feedback", "carmen_review_feedback"),
]

# (table, old_column, new_column)
COLUMN_RENAMES = [
    ("users", "is_bb_chat", "is_carmen_chat"),
    ("notifications", "bb_drawing_review_id", "carmen_drawing_review_id"),
]

# (old, new) — every index the creation migrations made. Renaming is cosmetic (indexes
# keep working under the old name after a table rename) but keeps names matching the
# tables. Non-existent ones are skipped by the guard, so this list is safe to over-cover.
INDEX_RENAMES = [
    ("ix_bb_chat_conversations_user_id", "ix_carmen_chat_conversations_user_id"),
    ("ix_bb_chat_messages_conversation_id", "ix_carmen_chat_messages_conversation_id"),
    ("ix_bb_chat_messages_request_id", "ix_carmen_chat_messages_request_id"),
    ("ix_bb_drawing_reviews_drawing_version_id", "ix_carmen_drawing_reviews_drawing_version_id"),
    ("ix_bb_drawing_reviews_release_id", "ix_carmen_drawing_reviews_release_id"),
    ("ix_bb_drawing_reviews_submittal_id", "ix_carmen_drawing_reviews_submittal_id"),
    ("ix_bb_drawing_reviews_attachment_id", "ix_carmen_drawing_reviews_attachment_id"),
    ("ix_bb_review_feedback_review_id", "ix_carmen_review_feedback_review_id"),
    ("ix_bb_review_feedback_release_id", "ix_carmen_review_feedback_release_id"),
    ("ix_bb_review_feedback_submittal_id", "ix_carmen_review_feedback_submittal_id"),
    ("ix_bb_review_feedback_attachment_id", "ix_carmen_review_feedback_attachment_id"),
    ("_bb_review_feedback_finding_uc", "_carmen_review_feedback_finding_uc"),
    ("ix_notifications_bb_drawing_review_id", "ix_notifications_carmen_drawing_review_id"),
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


# --------------------------------------------------------------------------- #
# Guarded, idempotent DDL builders (Postgres)
# --------------------------------------------------------------------------- #
def _sql_rename_table(old: str, new: str) -> str:
    # to_regclass covers tables AND indexes (both live in pg_class). Rename only when the
    # old object still exists and the new one doesn't — so a re-run is a clean no-op.
    return (
        f"DO $$ BEGIN "
        f"IF to_regclass('{old}') IS NOT NULL AND to_regclass('{new}') IS NULL THEN "
        f"ALTER TABLE {old} RENAME TO {new}; "
        f"END IF; END $$;"
    )


def _sql_rename_index(old: str, new: str) -> str:
    return (
        f"DO $$ BEGIN "
        f"IF to_regclass('{old}') IS NOT NULL AND to_regclass('{new}') IS NULL THEN "
        f"ALTER INDEX {old} RENAME TO {new}; "
        f"END IF; END $$;"
    )


def _sql_rename_column(table: str, old: str, new: str) -> str:
    return (
        f"DO $$ BEGIN "
        f"IF EXISTS (SELECT 1 FROM information_schema.columns "
        f"           WHERE table_name='{table}' AND column_name='{old}') "
        f"AND NOT EXISTS (SELECT 1 FROM information_schema.columns "
        f"                WHERE table_name='{table}' AND column_name='{new}') THEN "
        f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}; "
        f"END IF; END $$;"
    )


def _is_lock_timeout(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "lock" in msg and ("timeout" in msg or "not available" in msg or "55p03" in msg)


def _run_with_retry(conn, sql: str, label: str) -> None:
    """Execute one idempotent statement, retrying on lock_timeout with backoff."""
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

        try:
            for old, new in TABLE_RENAMES:
                _run_with_retry(conn, _sql_rename_table(old, new), f"table {old} -> {new}")
            for table, old, new in COLUMN_RENAMES:
                _run_with_retry(conn, _sql_rename_column(table, old, new), f"column {table}.{old} -> {new}")
            for old, new in INDEX_RENAMES:
                _run_with_retry(conn, _sql_rename_index(old, new), f"index {old} -> {new}")
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get a lock — a table is "
                    "under sustained load. Nothing partial is left inconsistent (each rename is its "
                    "own transaction); just re-run during a quieter window. Find a blocker with:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # Local-dev convenience only (prod/sandbox are Postgres). SQLite has ALTER TABLE
    # RENAME TO / RENAME COLUMN but no ALTER INDEX RENAME — indexes follow the table
    # automatically, so we simply skip index renames here.
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for old, new in TABLE_RENAMES:
            if old in tables and new not in tables:
                conn.execute(text(f"ALTER TABLE {old} RENAME TO {new}"))
                print(f"✓ table {old} -> {new}")
            else:
                print(f"• table {old} -> {new} (skipped)")
        for table, old, new in COLUMN_RENAMES:
            cols = {c["name"] for c in inspector.get_columns(table)} if table in tables else set()
            if old in cols and new not in cols:
                conn.execute(text(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}"))
                print(f"✓ column {table}.{old} -> {new}")
            else:
                print(f"• column {table}.{old} -> {new} (skipped)")
    print("  (SQLite: index renames skipped — indexes follow the table automatically.)")
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
        description="Rename BB / Banana Boy DB objects to Carmen Miranda (schema-only, idempotent)."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
