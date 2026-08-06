"""
Widen releases uniqueness from (job, release) to (job, release, job_name).

Job numbers wrap/reuse. The same release digits may belong to a different
project (e.g. archived 410-108 Columbine must not block a new 410-108 Alta
Metro). Same job # + release # + project name must remain unique forever
(including archived rows).

Drops constraint/index ``_job_release_uc`` and creates
``uq_releases_job_release_name`` on (job, release, job_name).

Usage:
    python migrations/releases_unique_job_release_name.py
    python migrations/releases_unique_job_release_name.py --database-url postgresql://...

Safety (Postgres): AUTOCOMMIT + lock_timeout + IF EXISTS / IF NOT EXISTS, no
schema reflection while holding a lock.
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

OLD_CONSTRAINT = "_job_release_uc"
NEW_CONSTRAINT = "uq_releases_job_release_name"

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

    for key in (
        "LOCAL_DATABASE_URL",
        "DATABASE_URL",
        "SQLALCHEMY_DATABASE_URI",
        "JOBS_DB_URL",
        "JOBS_SQLITE_PATH",
    ):
        value = os.environ.get(key)
        if value:
            return _coerce_url(value)

    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def _mask(url: str) -> str:
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

        if conn.execute(text("SELECT to_regclass('releases')")).scalar() is None:
            print("✗ Table 'releases' does not exist. Run the base schema first.")
            return False

        try:
            # Drop the old (job, release)-only unique constraint on *releases*.
            # Do NOT bare DROP INDEX on the constraint name: the legacy `jobs`
            # table also has UniqueConstraint name `_job_release_uc`, and
            # `DROP INDEX _job_release_uc` will hit that table and fail with
            # DependentObjectsStillExist. DROP CONSTRAINT on releases removes
            # its backing index; that is enough.
            _run_with_retry(
                conn,
                f"ALTER TABLE releases DROP CONSTRAINT IF EXISTS {OLD_CONSTRAINT}",
                f"drop releases constraint {OLD_CONSTRAINT}",
            )

            # Add the wider unique only if it is not already present (re-runnable
            # after a partial run that dropped the old constraint then failed).
            exists = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = :name
                      AND conrelid = 'releases'::regclass
                    """
                ),
                {"name": NEW_CONSTRAINT},
            ).scalar()
            if exists:
                print(f"✓ {NEW_CONSTRAINT} already present on releases")
            else:
                _run_with_retry(
                    conn,
                    f"""
                    ALTER TABLE releases
                    ADD CONSTRAINT {NEW_CONSTRAINT}
                    UNIQUE (job, release, job_name)
                    """.strip(),
                    f"add releases constraint {NEW_CONSTRAINT}",
                )
        except OperationalError as exc:
            msg = str(exc).lower()
            if "already exists" in msg:
                print(f"✓ {NEW_CONSTRAINT} already present")
                return True
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not get the lock on "
                    "'releases'. Nothing was committed. Re-run during a quieter window."
                )
                return False
            raise
        except ProgrammingError as exc:
            msg = str(exc).lower()
            if "already exists" in msg:
                print(f"✓ {NEW_CONSTRAINT} already present")
                return True
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    """
    SQLite cannot DROP CONSTRAINT easily; rebuild via a unique index when
    possible. Local/dev only — prod is Postgres.
    """
    inspector = inspect(engine)
    if "releases" not in inspector.get_table_names():
        print("✗ Table 'releases' does not exist.")
        return False

    with engine.begin() as conn:
        # Only create the new unique index. Do not DROP INDEX by the shared
        # legacy name — it can refer to the `jobs` table in shared-name setups.
        conn.execute(
            text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {NEW_CONSTRAINT} "
                f"ON releases (job, release, job_name)"
            )
        )
        print(f"✓ unique index {NEW_CONSTRAINT} on (job, release, job_name)")
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
    except Exception as exc:  # pragma: no cover
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Unique (job, release, job_name) on releases; drop old (job, release) unique."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()
    sys.exit(0 if migrate(args.database_url) else 1)
