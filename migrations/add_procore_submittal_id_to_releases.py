"""
Add the procore_submittal_id column to the releases table.

Captures the Procore submittal_id at FC-drawing lookup time so the Job Log
modal can deep-link to the submittal page (the viewer_url alone does not
encode the submittal_id).

Reads the same .env and ENVIRONMENT selection the app uses (via app.config
and app.db_config), so this script targets the same database the running
Flask app would.

Usage:
    # uses ENVIRONMENT from .env (defaults to local)
    python migrations/add_procore_submittal_id_to_releases.py

    # override the env explicitly
    python migrations/add_procore_submittal_id_to_releases.py --environment sandbox

The script is idempotent and safe to run multiple times.
"""

import argparse
import os
import sys

# Make the repo root importable regardless of CWD so `app.*` resolves.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Importing app.config triggers load_dotenv() against the project .env, and
# get_database_config() applies the same env-based DB-URL selection used by
# the Flask app factory.
from app.config import get_config  # noqa: F401,E402  (side-effect: load .env)
from app.db_config import get_database_config  # noqa: E402

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError


def column_exists(engine, table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def migrate(environment: str = None) -> bool:
    db_url, engine_options = get_database_config(environment)
    # Resolve the env name used so the log line is honest about it.
    resolved_env = (environment or os.environ.get("FLASK_ENV")
                    or os.environ.get("ENVIRONMENT", "local")).lower()
    print(f"Environment: {resolved_env}")
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url, **(engine_options or {}))
    try:
        if column_exists(engine, "releases", "procore_submittal_id"):
            print("✓ Column 'procore_submittal_id' already exists on 'releases'. Nothing to do.")
            return True

        print("Adding column 'procore_submittal_id' to 'releases' table...")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE releases ADD COLUMN procore_submittal_id VARCHAR(64)"))

        if column_exists(engine, "releases", "procore_submittal_id"):
            print("✓ Successfully added 'procore_submittal_id' column to 'releases'.")
            return True

        print("✗ Column addition did not succeed. Please verify manually.")
        return False

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error while adding column: {exc}")
        return False
    except Exception as exc:
        print(f"✗ Unexpected error: {exc}")
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add procore_submittal_id column to releases table.")
    parser.add_argument(
        "--environment",
        choices=["local", "sandbox", "production"],
        help="Override environment (otherwise read from FLASK_ENV / ENVIRONMENT in .env).",
    )
    args = parser.parse_args()

    success = migrate(args.environment)
    sys.exit(0 if success else 1)
