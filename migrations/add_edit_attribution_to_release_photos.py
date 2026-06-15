"""
Add note-edit attribution columns to the release_photos table.

Adds `last_edited_by_user_id` (FK to users.id) and `last_edited_at` so we can
track who last changed a photo's note after upload. Both are nullable and stay
null until a photo's note is first edited.

Usage:
    ENVIRONMENT=sandbox python migrations/add_edit_attribution_to_release_photos.py
    ENVIRONMENT=sandbox python migrations/add_edit_attribution_to_release_photos.py --yes
    python migrations/add_edit_attribution_to_release_photos.py --database-url postgresql://...

The script is idempotent and safe to run multiple times.
"""

import argparse
import os
import sys

# Make the repo root importable so `import app.config` works regardless of CWD.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError


def resolve_database_url(cli_url: str | None) -> tuple[str, str]:
    """Pick the DB URL to migrate against. Returns (url, environment_label)."""
    if cli_url:
        return cli_url.strip(), "explicit --database-url"

    import app.config  # noqa: F401  (triggers load_dotenv)

    from app.db_config import get_database_config

    environment = (
        os.environ.get("FLASK_ENV")
        or os.environ.get("ENVIRONMENT", "local")
    ).lower()

    database_url, _engine_options = get_database_config(environment)
    return database_url, environment


def confirm_target(environment: str, database_url: str, assume_yes: bool) -> bool:
    """Prompt before mutating sandbox/production. Local DBs require no prompt."""
    redacted = database_url
    if "@" in redacted:
        scheme_split = redacted.split("://", 1)
        if len(scheme_split) == 2:
            scheme, rest = scheme_split
            if "@" in rest:
                creds, host = rest.split("@", 1)
                user = creds.split(":", 1)[0]
                redacted = f"{scheme}://{user}:***@{host}"

    print(f"Environment: {environment}")
    print(f"Database:    {redacted}")

    is_local = environment in ("local", "development", "dev") or database_url.startswith("sqlite")
    if is_local or assume_yes:
        return True

    answer = input("Proceed with migration? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def column_exists(engine, table_name: str, column_name: str) -> bool:
    if table_name not in inspect(engine).get_table_names():
        return False
    cols = [c["name"] for c in inspect(engine).get_columns(table_name)]
    return column_name in cols


def migrate(database_url: str) -> bool:
    engine = create_engine(database_url)

    # (column_name, DDL type) for each column we add.
    columns = [
        ("last_edited_by_user_id", "INTEGER"),
        ("last_edited_at", "TIMESTAMP"),
    ]

    try:
        if "release_photos" not in inspect(engine).get_table_names():
            print("✗ Table 'release_photos' does not exist. Run add_release_photos_table.py first.")
            return False

        pending = [(name, ddl) for name, ddl in columns
                   if not column_exists(engine, "release_photos", name)]

        if not pending:
            print("✓ Columns already exist. Nothing to do.")
            return True

        with engine.begin() as conn:
            for name, ddl in pending:
                print(f"Adding column '{name}' to 'release_photos'...")
                conn.execute(text(f"ALTER TABLE release_photos ADD COLUMN {name} {ddl}"))

        still_missing = [name for name, _ddl in columns
                         if not column_exists(engine, "release_photos", name)]
        if still_missing:
            print(f"✗ Column add did not succeed for: {', '.join(still_missing)}. Please verify manually.")
            return False

        print("✓ Successfully added note-edit attribution columns to 'release_photos'.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error while adding columns: {exc}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add note-edit attribution columns to release_photos.")
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise resolved from ENVIRONMENT/FLASK_ENV).",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt for sandbox/production.",
    )
    args = parser.parse_args()

    try:
        database_url, environment = resolve_database_url(args.database_url)
    except ValueError as exc:
        print(f"✗ {exc}")
        sys.exit(2)

    if not confirm_target(environment, database_url, args.yes):
        print("Aborted by user.")
        sys.exit(1)

    success = migrate(database_url)
    sys.exit(0 if success else 1)
