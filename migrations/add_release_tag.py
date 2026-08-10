"""
Add nullable `release_tag` on releases (N1 billing classifier).

Values: contracted | change_order | mhmw_cost. Nullable so existing rows stay
valid; create paths require a tag in app code. No backfill.

Usage:
    python migrations/add_release_tag.py
    python migrations/add_release_tag.py --database-url postgresql://...

Safety: idempotent IF NOT EXISTS DDL, AUTOCOMMIT, lock_timeout (see
migrations/add_start_install_to_dwl.py).
"""
import argparse
import os
import sys
import time
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
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
                    f"retrying in {delay}s"
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
            _run_with_retry(
                conn,
                "ALTER TABLE releases ADD COLUMN IF NOT EXISTS release_tag VARCHAR(32)",
                "releases.release_tag",
            )
        except OperationalError as exc:
            if _is_lock_timeout(exc):
                print(
                    f"✗ Gave up after {LOCK_RETRIES} attempts: could not lock 'releases'. "
                    "Nothing committed."
                )
                return False
            raise
    return True


def _migrate_sqlite(engine) -> bool:
    with engine.connect() as conn:
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(releases)")).fetchall()
        }
        if "release_tag" not in cols:
            conn.execute(text("ALTER TABLE releases ADD COLUMN release_tag VARCHAR(32)"))
            conn.commit()
            print("✓ releases.release_tag")
        else:
            print("✓ releases.release_tag (already present)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Add nullable release_tag on releases.")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    try:
        url = infer_database_url(args.database_url)
    except ValueError as exc:
        print(f"✗ {exc}")
        return 1

    print(f"Migrating: {_mask(url)}")
    engine = create_engine(url)

    if url.startswith("sqlite"):
        ok = _migrate_sqlite(engine)
    else:
        ok = _migrate_postgres(engine)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
