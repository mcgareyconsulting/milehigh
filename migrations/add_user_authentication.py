"""
Add user authentication system: create users table and add user_id columns to events tables.

Usage:
    python migrations/add_user_authentication.py

The script is idempotent and safe to run multiple times. It inspects the current
schema before attempting to alter tables.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")

# Load environment variables from a .env file if present
load_dotenv()


def normalize_sqlite_path(path: str) -> str:
    """Return a SQLAlchemy-friendly SQLite URL for the given path."""
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def infer_database_url(cli_url: str = None) -> str:
    """Figure out which database to hit, honoring CLI and environment defaults."""
    candidates = [
        cli_url,
        os.environ.get("DATABASE_URL"),
        os.environ.get("SQLALCHEMY_DATABASE_URI"),
        os.environ.get("JOBS_DB_URL"),
        os.environ.get("JOBS_SQLITE_PATH"),
        os.environ.get("SANDBOX_DATABASE_URL"),
    ]

    for value in candidates:
        if not value:
            continue

        value = value.strip()
        if value.startswith("postgres://"):
            # SQLAlchemy expects postgresql://
            return value.replace("postgres://", "postgresql://", 1)

        if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
            return value

        # Treat anything else as a filesystem path to a SQLite DB
        return normalize_sqlite_path(value)

    # Fall back to bundled SQLite file
    return normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def table_exists(engine, table_name: str) -> bool:
    """Check if a given table exists."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a given column exists on the specified table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def is_postgresql(engine) -> bool:
    """Check if the database is PostgreSQL."""
    return engine.dialect.name == "postgresql"


def migrate(database_url: str = None) -> bool:
    """Perform the migration, creating users table and adding user_id columns."""
    db_url = infer_database_url(database_url)
    print(f"Connecting to database: {db_url}")

    engine = create_engine(db_url)
    is_pg = is_postgresql(engine)

    try:
        with engine.begin() as conn:
            # Step 1: Create users table if it doesn't exist
            if not table_exists(engine, "users"):
                print("Creating 'users' table...")
                
                if is_pg:
                    # PostgreSQL syntax
                    conn.execute(text("""
                        CREATE TABLE users (
                            id SERIAL PRIMARY KEY,
                            username VARCHAR(80) UNIQUE NOT NULL,
                            password_hash VARCHAR(255) NOT NULL,
                            is_active BOOLEAN NOT NULL DEFAULT TRUE,
                            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            last_login TIMESTAMP
                        )
                    """))
                    conn.execute(text("CREATE INDEX ix_users_username ON users (username)"))
                else:
                    # SQLite syntax
                    conn.execute(text("""
                        CREATE TABLE users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username VARCHAR(80) UNIQUE NOT NULL,
                            password_hash VARCHAR(255) NOT NULL,
                            is_active BOOLEAN NOT NULL DEFAULT 0,
                            is_admin BOOLEAN NOT NULL DEFAULT 0,
                            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            last_login TIMESTAMP
                        )
                    """))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
                
                print("✓ Successfully created 'users' table.")
            else:
                print("✓ Table 'users' already exists.")

            # Step 2: Add user_id column to job_events table
            if not column_exists(engine, "job_events", "user_id"):
                print("Adding column 'user_id' to 'job_events' table...")
                
                if is_pg:
                    conn.execute(text("ALTER TABLE job_events ADD COLUMN user_id INTEGER"))
                    conn.execute(text("ALTER TABLE job_events ADD CONSTRAINT fk_job_events_user_id FOREIGN KEY (user_id) REFERENCES users(id)"))
                else:
                    # SQLite doesn't support adding foreign keys after table creation easily
                    # We'll add the column and note that FK constraint should be handled by SQLAlchemy
                    conn.execute(text("ALTER TABLE job_events ADD COLUMN user_id INTEGER"))
                
                print("✓ Successfully added 'user_id' column to 'job_events'.")
            else:
                print("✓ Column 'user_id' already exists on 'job_events'.")

            # Step 3: Add user_id column to submittal_events table
            if not column_exists(engine, "submittal_events", "user_id"):
                print("Adding column 'user_id' to 'submittal_events' table...")
                
                if is_pg:
                    conn.execute(text("ALTER TABLE submittal_events ADD COLUMN user_id INTEGER"))
                    conn.execute(text("ALTER TABLE submittal_events ADD CONSTRAINT fk_submittal_events_user_id FOREIGN KEY (user_id) REFERENCES users(id)"))
                else:
                    # SQLite doesn't support adding foreign keys after table creation easily
                    conn.execute(text("ALTER TABLE submittal_events ADD COLUMN user_id INTEGER"))
                
                print("✓ Successfully added 'user_id' column to 'submittal_events'.")
            else:
                print("✓ Column 'user_id' already exists on 'submittal_events'.")

        print("✓ Migration completed successfully.")
        return True

    except (OperationalError, ProgrammingError) as exc:
        print(f"✗ Database error during migration: {exc}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as exc:
        print(f"✗ Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add user authentication system: create users table and add user_id columns to events tables."
    )
    parser.add_argument(
        "--database-url",
        help="Override database URL (otherwise inferred from env or defaults).",
    )
    args = parser.parse_args()

    success = migrate(args.database_url)
    sys.exit(0 if success else 1)

