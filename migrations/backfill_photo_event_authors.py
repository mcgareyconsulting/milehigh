"""
Backfill the author on photo/drawing release_events that were written with no user.

The bug: photo and PDF-markup features stamped `source = "Brain:<username>"` to record
who acted. JobEventService.create only resolved `internal_user_id` when `source == "Brain"`
— an exact match — so every one of those events failed the test, was written with
`internal_user_id = NULL`, and rendered with an em dash in the Change Log's user column.

The code is fixed (source is plain "Brain", and the author is passed explicitly), but the
rows already written still carry the composite source and no author. This script reads the
username back out of `source`, resolves it against `users`, and fills `internal_user_id` in.
It leaves `source` alone: a row's source is a historical fact, and the Change Log already
renders the prefix and keeps the full string in a tooltip.

Idempotent — only touches rows that still match 'Brain:%' AND have no author, so re-running
it is a no-op. Rows whose username no longer resolves to a user are reported and skipped.

Usage:
    python migrations/backfill_photo_event_authors.py --dry-run              # report only
    python migrations/backfill_photo_event_authors.py --dry-run --show-all   # every row
    python migrations/backfill_photo_event_authors.py
    python migrations/backfill_photo_event_authors.py --database-url postgresql://...

Safety properties (Postgres):
  - No DDL and no schema reflection: this is a narrow UPDATE on rows matched by a
    LIKE on `source`. It takes ROW locks only — never ACCESS EXCLUSIVE — so it cannot
    freeze release_events the way an unguarded ALTER can.
  - One AUTOCOMMIT connection, one statement per implicit transaction.
  - `lock_timeout` makes a blocked UPDATE fail fast rather than queueing behind live
    traffic, with bounded retries so transient contention self-heals.
"""

import argparse
import os
import sys
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

from sqlalchemy import create_engine, text
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

    # Mirror app/db_config.py exactly: FLASK_ENV wins over ENVIRONMENT, and the app
    # accepts BOTH "production" and "prod". The migration template only tested
    # "production", so ENVIRONMENT=prod fell through to the generic candidate list
    # and picked whatever DATABASE_URL happened to be — right or wrong.
    environment = (
        os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT") or "local"
    ).strip().lower()

    if environment in ("production", "prod"):
        value = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not value:
            raise ValueError(
                f"ENVIRONMENT={environment} but neither PRODUCTION_DATABASE_URL nor "
                "DATABASE_URL is set (refusing to guess; pass --database-url)."
            )
        return _coerce_url(value)

    if environment in ("sandbox", "staging"):
        value = os.environ.get("SANDBOX_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not value:
            raise ValueError(
                f"ENVIRONMENT={environment} but neither SANDBOX_DATABASE_URL nor "
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


# Orphan rows: composite source, no author. The LIKE is the whole selection criterion,
# so no reflection is needed and the statement is safe to re-run.
_SELECT_ORPHANS = """
    SELECT id, source, action, job, release, created_at
    FROM release_events
    WHERE source LIKE 'Brain:%'
      AND internal_user_id IS NULL
    ORDER BY id
"""

_UPDATE_ONE = """
    UPDATE release_events
    SET internal_user_id = :user_id
    WHERE id = :event_id
      AND internal_user_id IS NULL
"""


def _is_lock_timeout(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "lock" in msg and ("timeout" in msg or "not available" in msg or "55p03" in msg)


def _run_with_retry(conn, sql: str, params: dict, label: str):
    """Execute one statement, retrying on lock_timeout with backoff."""
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            return conn.execute(text(sql), params)
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


def _load_users(conn) -> dict:
    """username → (id, display name), lowercased so case can't lose a match."""
    rows = conn.execute(
        text("SELECT id, username, first_name, last_name FROM users")
    ).fetchall()
    users = {}
    for uid, username, first, last in rows:
        if not username:
            continue
        display = f"{(first or '').strip()} {(last or '').strip()}".strip() or username
        users[username.strip().lower()] = (uid, display)
    return users


def _print_preview(rows, users, show_all: bool) -> None:
    """Show exactly which author each event would get, and the totals per person."""
    by_user = {}
    by_action = {}
    for event_id, source, action, job, release, created_at in rows:
        username = (source or "").split(":", 1)[1].strip().lower()
        hit = users.get(username)
        key = f"{hit[1]} (id {hit[0]})" if hit else f"{username or '?'} — NO MATCH"
        by_user[key] = by_user.get(key, 0) + 1
        by_action[action] = by_action.get(action, 0) + 1

    print("\n  Author each event would be attributed to:")
    for key, n in sorted(by_user.items(), key=lambda kv: -kv[1]):
        print(f"    {n:5d}  →  {key}")

    print("\n  By action:")
    for action, n in sorted(by_action.items(), key=lambda kv: -kv[1]):
        print(f"    {n:5d}  {action}")

    shown = rows if show_all else rows[:15]
    print(f"\n  Row detail ({len(shown)} of {len(rows)}):")
    print(f"    {'event':>7}  {'job-release':<14} {'action':<22} {'when':<19} author")
    for event_id, source, action, job, release, created_at in shown:
        username = (source or "").split(":", 1)[1].strip().lower()
        hit = users.get(username)
        author = f"{hit[1]} (id {hit[0]})" if hit else "— NO MATCH, skipped"
        when = str(created_at)[:19] if created_at else "—"
        label = f"{job}-{release}" if release else str(job)
        print(f"    {event_id:>7}  {label:<14} {action:<22} {when:<19} {author}")
    if not show_all and len(rows) > len(shown):
        print(f"    … {len(rows) - len(shown)} more — re-run with --show-all to see every row")


def backfill(conn, dry_run: bool, show_all: bool = False) -> bool:
    orphans = conn.execute(text(_SELECT_ORPHANS)).fetchall()
    if not orphans:
        print("✓ Nothing to do — no 'Brain:<user>' events are missing an author.")
        return True

    users = _load_users(conn)
    print(f"Found {len(orphans)} event(s) with a composite source and no author.")

    if dry_run:
        _print_preview(orphans, users, show_all)

    filled, unmatched = 0, []
    for event_id, source, action, job, release, created_at in orphans:
        username = (source or "").split(":", 1)[1].strip().lower()
        hit = users.get(username)
        if hit is None:
            unmatched.append((event_id, source))
            continue
        if dry_run:
            filled += 1
            continue
        result = _run_with_retry(
            conn, _UPDATE_ONE, {"user_id": hit[0], "event_id": event_id},
            f"release_events.{event_id}",
        )
        filled += result.rowcount or 0

    verb = "Would set" if dry_run else "Set"
    print(f"\n✓ {verb} the author on {filled} event(s).")

    if unmatched:
        print(f"⚠ {len(unmatched)} event(s) name a username with no matching user — left as-is:")
        for event_id, source in unmatched[:10]:
            print(f"    id={event_id}  source={source!r}")
        if len(unmatched) > 10:
            print(f"    … and {len(unmatched) - 10} more")

    return True


def migrate(database_url: str = None, dry_run: bool = False,
            show_all: bool = False) -> bool:
    db_url = infer_database_url(database_url)
    env_label = "explicit --database-url" if database_url else (
        os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT") or "local"
    )
    print(f"Environment: {env_label}")
    print(f"Connecting to database: {_mask(db_url)}")
    if dry_run:
        print("DRY RUN — no rows will be written.")

    engine = create_engine(db_url)
    try:
        if engine.dialect.name == "sqlite":
            with engine.begin() as conn:
                return backfill(conn, dry_run, show_all)

        # AUTOCOMMIT so each UPDATE is its own transaction and row locks are released
        # immediately, never held across the whole run.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
            conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))
            if conn.execute(text("SELECT to_regclass('release_events')")).scalar() is None:
                print("✗ Table 'release_events' does not exist. Run the base schema first.")
                return False
            return backfill(conn, dry_run, show_all)
    except OperationalError as exc:
        if _is_lock_timeout(exc):
            print(
                f"✗ Gave up after {LOCK_RETRIES} attempts: could not get a row lock on "
                "'release_events'. Nothing further was committed; re-running is safe."
            )
            return False
        print(f"✗ Database error: {exc}")
        return False
    except ProgrammingError as exc:
        print(f"✗ Database error during backfill: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Attribute photo/drawing release_events that were written without an author."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything.",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="With --dry-run, print every row rather than the first 15.",
    )
    args = parser.parse_args()

    success = migrate(args.database_url, args.dry_run, args.show_all)
    sys.exit(0 if success else 1)
