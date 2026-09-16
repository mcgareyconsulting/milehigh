"""
Add the Release Issue & Error Register (roadmap T11): four new tables plus two nullable
columns on `notifications` so @mentions on issues reach the bell.

  release_issues             — one row per issue on a release
  release_issue_comments     — timestamped comments (@mentions notify)
  release_issue_changes      — field-level edit history (who / when / old → new)
  release_issue_attachments  — photos + PDFs belonging to one issue
  notifications.release_issue_id, notifications.release_issue_comment_id

Nothing is backfilled.

Usage:
    python migrations/add_release_issues.py
    python migrations/add_release_issues.py --database-url postgresql://...

Safety properties (Postgres) — follows migrations/README.md and
migrations/add_start_install_to_dwl.py:
  - Every statement is idempotent (`CREATE TABLE/INDEX IF NOT EXISTS`, `ADD COLUMN IF
    NOT EXISTS`, constraints guarded by a pg_constraint check on the SAME connection),
    so there is NO SQLAlchemy reflection.
  - One AUTOCOMMIT connection: each statement is its own implicit transaction, so any
    lock is held only for the instant the statement runs.
  - `lock_timeout` makes a blocked statement fail fast and retry with backoff instead of
    queueing behind live traffic.
  - The notifications columns are nullable with no default (metadata-only). Their foreign
    keys are added NOT VALID (no table scan under the exclusive lock), then VALIDATEd
    separately, which only takes a SHARE UPDATE EXCLUSIVE lock and does not block writes.
  - The notifications index is built CONCURRENTLY so the table stays writable.
  - The DB URL is masked in output.
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


# --- Idempotent DDL. {pk} / {ts} / {bool_false} are filled per dialect. --------------

_TABLES = [
    ("release_issues table", """
        CREATE TABLE IF NOT EXISTS release_issues (
            id {pk},
            release_id INTEGER NOT NULL REFERENCES releases (id),
            seq INTEGER NOT NULL,
            title VARCHAR(200) NOT NULL,
            description TEXT NOT NULL,
            original_description TEXT NOT NULL,
            department VARCHAR(32) NOT NULL,
            category VARCHAR(40) NOT NULL,
            priority VARCHAR(16) NOT NULL DEFAULT 'normal',
            status VARCHAR(24) NOT NULL DEFAULT 'open',
            estimated_cost NUMERIC(12, 2),
            accountable_user_id INTEGER REFERENCES users (id),
            created_by_user_id INTEGER NOT NULL REFERENCES users (id),
            created_by_name VARCHAR(160),
            created_at {ts} NOT NULL,
            updated_at {ts} NOT NULL,
            CONSTRAINT uq_release_issues_release_seq UNIQUE (release_id, seq)
        )
    """),
    ("release_issue_comments table", """
        CREATE TABLE IF NOT EXISTS release_issue_comments (
            id {pk},
            issue_id INTEGER NOT NULL REFERENCES release_issues (id) ON DELETE CASCADE,
            release_id INTEGER NOT NULL REFERENCES releases (id),
            body TEXT NOT NULL,
            author_id INTEGER NOT NULL REFERENCES users (id),
            author_name VARCHAR(160) NOT NULL,
            created_at {ts} NOT NULL
        )
    """),
    ("release_issue_changes table", """
        CREATE TABLE IF NOT EXISTS release_issue_changes (
            id {pk},
            issue_id INTEGER NOT NULL REFERENCES release_issues (id) ON DELETE CASCADE,
            field VARCHAR(32) NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by_user_id INTEGER NOT NULL REFERENCES users (id),
            changed_by_name VARCHAR(160),
            changed_at {ts} NOT NULL
        )
    """),
    ("release_issue_attachments table", """
        CREATE TABLE IF NOT EXISTS release_issue_attachments (
            id {pk},
            issue_id INTEGER NOT NULL REFERENCES release_issues (id) ON DELETE CASCADE,
            comment_id INTEGER REFERENCES release_issue_comments (id) ON DELETE SET NULL,
            storage_key VARCHAR(512) NOT NULL,
            original_filename VARCHAR(256),
            mime_type VARCHAR(64) NOT NULL,
            file_size_bytes BIGINT NOT NULL,
            uploaded_by_user_id INTEGER NOT NULL REFERENCES users (id),
            uploaded_by_name VARCHAR(160),
            uploaded_at {ts} NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT {bool_false}
        )
    """),
]

_TABLE_INDEXES = [
    ("release_issues.release_id index",
     "CREATE INDEX IF NOT EXISTS ix_release_issues_release_id ON release_issues (release_id)"),
    ("release_issues.status index",
     "CREATE INDEX IF NOT EXISTS ix_release_issues_status ON release_issues (status)"),
    ("release_issue_comments.issue_id index",
     "CREATE INDEX IF NOT EXISTS ix_release_issue_comments_issue_id ON release_issue_comments (issue_id)"),
    ("release_issue_changes.issue_id index",
     "CREATE INDEX IF NOT EXISTS ix_release_issue_changes_issue_id ON release_issue_changes (issue_id)"),
    ("release_issue_attachments.issue_id index",
     "CREATE INDEX IF NOT EXISTS ix_release_issue_attachments_issue_id ON release_issue_attachments (issue_id)"),
]

_NOTIFICATION_COLUMNS = [
    ("notifications.release_issue_id",
     "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS release_issue_id INTEGER"),
    ("notifications.release_issue_comment_id",
     "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS release_issue_comment_id INTEGER"),
]

# (constraint name, column, referenced table)
_NOTIFICATION_FKS = [
    ("fk_notifications_release_issue_id", "release_issue_id", "release_issues"),
    ("fk_notifications_release_issue_comment_id", "release_issue_comment_id", "release_issue_comments"),
]


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

        for required in ("releases", "users", "notifications"):
            if conn.execute(text(f"SELECT to_regclass('{required}')")).scalar() is None:
                print(f"✗ Table '{required}' does not exist. Run the base schema first.")
                return False

        try:
            for label, sql in _TABLES:
                _run_with_retry(
                    conn,
                    sql.format(pk="SERIAL PRIMARY KEY", ts="TIMESTAMP", bool_false="FALSE"),
                    label,
                )
            for label, sql in _TABLE_INDEXES:
                _run_with_retry(conn, sql, label)

            for label, sql in _NOTIFICATION_COLUMNS:
                _run_with_retry(conn, sql, label)

            for name, column, ref in _NOTIFICATION_FKS:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_constraint WHERE conname = :name"), {"name": name}
                ).scalar()
                if exists:
                    print(f"{name} already exists, skipping")
                else:
                    _run_with_retry(
                        conn,
                        f"ALTER TABLE notifications ADD CONSTRAINT {name} FOREIGN KEY ({column}) "
                        f"REFERENCES {ref} (id) ON DELETE CASCADE NOT VALID",
                        f"{name} (NOT VALID)",
                    )
                _run_with_retry(conn, f"ALTER TABLE notifications VALIDATE CONSTRAINT {name}",
                                f"{name} validated")

            # CONCURRENTLY cannot run inside a transaction block — AUTOCOMMIT satisfies that.
            _run_with_retry(
                conn,
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_notifications_release_issue_id "
                "ON notifications (release_issue_id)",
                "notifications.release_issue_id index",
            )
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get a lock — a table is "
                    "under sustained load. Statements already applied are idempotent; re-run "
                    "during a quieter window, or find an idle-in-transaction blocker:\n"
                    "    SELECT pid, pg_blocking_pids(pid), state, left(query,80) "
                    "FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;"
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    # SQLite is single-writer with no concurrent prod traffic. Older SQLite lacks
    # ADD COLUMN IF NOT EXISTS, so guard the notifications columns by inspection.
    # SQLite cannot add a FK to an existing table; the columns are added plain.
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for required in ("releases", "users", "notifications"):
        if required not in tables:
            print(f"✗ Table '{required}' does not exist. Run the base schema first.")
            return False
    existing = {c["name"] for c in inspector.get_columns("notifications")}

    with engine.begin() as conn:
        for label, sql in _TABLES:
            conn.execute(text(sql.format(
                pk="INTEGER PRIMARY KEY AUTOINCREMENT", ts="DATETIME", bool_false="0",
            )))
            print(f"✓ {label}")
        for label, sql in _TABLE_INDEXES:
            conn.execute(text(sql))
            print(f"✓ {label}")
        for column in ("release_issue_id", "release_issue_comment_id"):
            if column in existing:
                print(f"notifications.{column} already exists, skipping")
            else:
                conn.execute(text(f"ALTER TABLE notifications ADD COLUMN {column} INTEGER"))
                print(f"✓ notifications.{column}")
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_notifications_release_issue_id "
            "ON notifications (release_issue_id)"
        ))
        print("✓ notifications.release_issue_id index")
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
        description="Add the Release Issue Register tables and notification columns."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)
