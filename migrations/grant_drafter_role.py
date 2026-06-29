"""
Grant the drafter role (users.is_drafter = true) to a fixed set of drafters.

Why this exists: the Drafting Work Load "Assign Rel" (release-number) endpoint is gated
by @drafter_or_admin_required, which already permits drafters — but in production NO user
had is_drafter = true, so in practice only admins could assign release numbers. This flips
the flag for the real drafters so they get access. No code change or deploy is involved.

Idempotent: re-running is a no-op for rows already set to true. The script reports the
before state, the rows it would change, and (with --apply) the after state.

Usage:
    python migrations/grant_drafter_role.py                      # DRY RUN (default) — shows what would change
    python migrations/grant_drafter_role.py --apply              # commit the change
    python migrations/grant_drafter_role.py --apply --database-url postgresql://...

Safety properties (Postgres):
  - Targets a fixed, hard-coded username allow-list — never touches anyone else.
  - One AUTOCOMMIT connection; the UPDATE takes only brief ROW EXCLUSIVE locks on the
    matched rows, never a table-level ACCESS EXCLUSIVE lock.
  - SET lock_timeout so a blocked statement fails fast instead of queueing.
  - Masks the DB URL in all log output — never prints credentials.
  - No schema reflection.
"""

import argparse
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

LOCK_TIMEOUT = "5s"
STATEMENT_TIMEOUT = "30s"

# Drafters to grant is_drafter = true. Email/username is the stable key.
TARGET_USERNAMES = [
    "ralvarado@mhmw.com",  # Rourke Alvarado
    "carendt@mhmw.com",    # Colton Arendt
    "drauer@mhmw.com",     # Dalton Rauer
    "dpauley@mhmw.com",    # Dustin Pauley
    "galmeida@mhmw.com",   # Gary Almeida
    "rlosasso@mhmw.com",   # Rich Losasso
    "driddell@mhmw.com",   # Danny Riddell
]

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

    if environment in ("production", "prod"):
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


def _report(conn) -> list:
    """Print current state of the target users; return the rows found."""
    rows = conn.execute(
        text(
            "SELECT username, first_name, last_name, is_admin, is_drafter "
            "FROM users WHERE username IN :names ORDER BY username"
        ).bindparams(names=tuple(TARGET_USERNAMES))
    ).fetchall()

    found = {r[0] for r in rows}
    missing = [u for u in TARGET_USERNAMES if u not in found]

    print(f"{'username':24} {'name':22} admin drafter")
    for r in rows:
        name = f"{r[1] or ''} {r[2] or ''}".strip()
        print(f"{r[0]:24} {name:22} {str(r[3]):5} {str(r[4])}")
    if missing:
        print("\n⚠ Not found in users (skipped — check the spelling):")
        for u in missing:
            print(f"   {u}")
    return rows


def run(database_url: str = None, apply: bool = False) -> bool:
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {_mask(db_url)}")
    print(f"Mode: {'APPLY (will commit)' if apply else 'DRY RUN (no changes)'}\n")

    engine = create_engine(db_url)
    is_pg = engine.dialect.name == "postgresql"
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            if is_pg:
                conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
                conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'"))

            print("BEFORE:")
            before = _report(conn)
            to_change = [r[0] for r in before if not r[4]]  # is_drafter currently false

            print()
            if not to_change:
                print("Nothing to do — every found target already has is_drafter = true.")
                return True

            print(f"Will set is_drafter = true for {len(to_change)} user(s):")
            for u in to_change:
                print(f"   {u}")

            if not apply:
                print("\nDRY RUN — no changes committed. Re-run with --apply to commit.")
                return True

            result = conn.execute(
                text(
                    "UPDATE users SET is_drafter = true "
                    "WHERE username IN :names AND is_drafter = false"
                ).bindparams(names=tuple(TARGET_USERNAMES))
            )
            print(f"\n✓ Updated {result.rowcount} row(s).\n")

            print("AFTER:")
            _report(conn)
        return True
    except ProgrammingError as exc:
        print(f"✗ Database error: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Grant is_drafter = true to the fixed drafter allow-list (dry-run by default)."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the change. Without this flag the script only reports what it would do.",
    )
    args = parser.parse_args()

    success = run(args.database_url, apply=args.apply)
    sys.exit(0 if success else 1)
