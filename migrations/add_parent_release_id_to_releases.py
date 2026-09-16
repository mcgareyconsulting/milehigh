"""
Add ``releases.parent_release_id`` — the splice link (T9: 340.1, 340.2 child releases
that carry install hours drawn from the parent's pool) — and backfill it for any
dotted release numbers that already exist (the verbal "340.1" created 2026-09-15).

Usage:
    python migrations/add_parent_release_id_to_releases.py
    python migrations/add_parent_release_id_to_releases.py --database-url postgresql://...
    python migrations/add_parent_release_id_to_releases.py --no-backfill

Safety properties (Postgres) — per migrations/README.md:
  - Idempotent DDL only (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`), so
    no schema reflection is needed while a lock could be held.
  - One AUTOCOMMIT connection: each statement is its own implicit transaction, so the
    ACCESS EXCLUSIVE lock is held for an instant, never across the migration.
  - `lock_timeout` makes a blocked ALTER fail fast; it retries with backoff.
  - ADD COLUMN is metadata-only (nullable, no default) so it is instant. The FK is
    added NOT VALID (no full-table scan under lock) and validated separately, which
    takes only a SHARE UPDATE EXCLUSIVE lock.
  - The backfill is plain row UPDATEs by primary key, one autocommit statement each,
    and re-running it is a no-op (only rows with a NULL parent are touched).
"""

import argparse
import os
import re
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

SPLICE_RE = re.compile(r"^(\d+)\.(\d+)$")

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


def _norm(name) -> str:
    return str(name or "").strip().casefold()


def _backfill(conn, dry_run: bool) -> int:
    """Link existing dotted release numbers to their parent row.

    Parent = same job, release == the dotted number's base, same project name
    (case/whitespace-insensitive), preferring non-archived + active. Rows whose
    parent can't be found are reported and left NULL. Idempotent: only rows with
    parent_release_id IS NULL are considered.
    """
    rows = conn.execute(text(
        "SELECT id, job, release, job_name FROM releases "
        "WHERE parent_release_id IS NULL AND release LIKE '%.%'"
    )).fetchall()
    candidates = [(r[0], r[1], r[2], r[3]) for r in rows if SPLICE_RE.match(str(r[2] or "").strip())]
    if not candidates:
        print("backfill: no unlinked dotted release numbers found")
        return 0

    linked = 0
    for cid, job, release, job_name in candidates:
        base = SPLICE_RE.match(str(release).strip()).group(1)
        parents = conn.execute(text(
            "SELECT id, job_name, is_archived, is_active FROM releases "
            "WHERE job = :job AND release = :base AND id <> :cid"
        ), {"job": job, "base": base, "cid": cid}).fetchall()
        parents = [p for p in parents if _norm(p[1]) == _norm(job_name)]
        if not parents:
            print(f"  ! {job}-{release}: no parent {job}-{base} with the same project name; left unlinked")
            continue
        parents.sort(key=lambda p: (bool(p[2]), p[3] is False, -(p[0] or 0)))
        parent_id = parents[0][0]
        if dry_run:
            print(f"  [dry-run] would link {job}-{release} (id {cid}) -> parent id {parent_id}")
        else:
            conn.execute(text(
                "UPDATE releases SET parent_release_id = :pid WHERE id = :cid AND parent_release_id IS NULL"
            ), {"pid": parent_id, "cid": cid})
            print(f"  ✓ linked {job}-{release} (id {cid}) -> parent id {parent_id}")
        linked += 1
    return linked


def _migrate_postgres(engine, backfill: bool, dry_run: bool) -> bool:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

        if conn.execute(text("SELECT to_regclass('releases')")).scalar() is None:
            print("✗ Table 'releases' does not exist. Run the base schema first.")
            return False

        try:
            _run_with_retry(
                conn,
                "ALTER TABLE releases ADD COLUMN IF NOT EXISTS parent_release_id INTEGER",
                "releases.parent_release_id",
            )
            _run_with_retry(
                conn,
                "CREATE INDEX IF NOT EXISTS ix_releases_parent_release_id "
                "ON releases (parent_release_id)",
                "ix_releases_parent_release_id",
            )
            # FK: NOT VALID skips the full-table scan under ACCESS EXCLUSIVE; VALIDATE
            # then scans under a lock that doesn't block reads/writes. Guarded by name
            # because ADD CONSTRAINT has no IF NOT EXISTS.
            fk_exists = conn.execute(text(
                "SELECT 1 FROM pg_constraint WHERE conname = 'fk_releases_parent_release_id'"
            )).scalar()
            if fk_exists:
                print("fk_releases_parent_release_id already exists, skipping")
            else:
                _run_with_retry(
                    conn,
                    "ALTER TABLE releases ADD CONSTRAINT fk_releases_parent_release_id "
                    "FOREIGN KEY (parent_release_id) REFERENCES releases (id) NOT VALID",
                    "fk_releases_parent_release_id (NOT VALID)",
                )
                _run_with_retry(
                    conn,
                    "ALTER TABLE releases VALIDATE CONSTRAINT fk_releases_parent_release_id",
                    "fk_releases_parent_release_id validated",
                )
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

        if backfill:
            _backfill(conn, dry_run)
    return True


def _migrate_sqlite(engine, backfill: bool, dry_run: bool) -> bool:
    inspector = inspect(engine)
    if "releases" not in inspector.get_table_names():
        print("✗ Table 'releases' does not exist. Run the base schema first.")
        return False
    existing = {c["name"] for c in inspector.get_columns("releases")}

    with engine.begin() as conn:
        if "parent_release_id" not in existing:
            conn.execute(text(
                "ALTER TABLE releases ADD COLUMN parent_release_id INTEGER REFERENCES releases (id)"
            ))
            print("✓ releases.parent_release_id")
        else:
            print("releases.parent_release_id already exists, skipping")
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_releases_parent_release_id ON releases (parent_release_id)"
        ))
        print("✓ ix_releases_parent_release_id")
        if backfill:
            _backfill(conn, dry_run)
    return True


def migrate(database_url: str = None, backfill: bool = True, dry_run: bool = False) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {_mask(db_url)}")

    engine = create_engine(db_url)
    try:
        if engine.dialect.name == "sqlite":
            return _migrate_sqlite(engine, backfill, dry_run)
        return _migrate_postgres(engine, backfill, dry_run)
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
        description="Add releases.parent_release_id (splice link) and backfill dotted release numbers."
    )
    parser.add_argument("--database-url", help="Override database URL (otherwise inferred from env).")
    parser.add_argument("--no-backfill", action="store_true", help="Add the column/index/FK only.")
    parser.add_argument(
        "--dry-run-backfill", action="store_true",
        help="Run the DDL, then only print which dotted releases would be linked.",
    )
    args = parser.parse_args()

    success = migrate(args.database_url, backfill=not args.no_backfill, dry_run=args.dry_run_backfill)
    sys.exit(0 if success else 1)
