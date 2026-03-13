"""
Compare prod and sandbox database schemas side-by-side.

This read-only script connects to both PRODUCTION_DATABASE_URL (or DATABASE_URL)
and SANDBOX_DATABASE_URL, inspects their schemas, and reports differences:
- Tables missing from prod (in sandbox only)
- Tables only in prod (not in sandbox)
- Per-table column/constraint/index diffs

Useful for tracking migration progress: run before migrations to see the gap,
run again after each migration to confirm progress.

Usage:
    python migrations/compare_prod_sandbox.py [--save] [--tables TABLE [TABLE ...]]

Options:
    --save: Save report to migrations/schema_snapshots/YYYY-MM-DD_HHMMSS.txt
    --tables TABLE [TABLE ...]: Limit comparison to specific tables
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Dict, List, Set, Tuple

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Add parent directory to path to import app modules
sys.path.insert(0, ROOT_DIR)

# Load environment variables from a .env file if present
load_dotenv()

# Import db_config for connection options
from app.db_config import get_database_engine_options


def get_production_database_url() -> str:
    """Get the production database URL."""
    database_url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "PRODUCTION_DATABASE_URL or DATABASE_URL must be set. "
            "Please set it in your .env file or environment variables."
        )

    # Convert postgres:// to postgresql:// if needed
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return database_url


def get_sandbox_database_url() -> str:
    """Get the sandbox database URL."""
    database_url = os.environ.get("SANDBOX_DATABASE_URL")
    if not database_url:
        raise ValueError(
            "SANDBOX_DATABASE_URL must be set. "
            "Please set it in your .env file or environment variables."
        )

    # Convert postgres:// to postgresql:// if needed
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return database_url


def create_db_engine(database_url: str) -> Engine:
    """Create a database engine with standard pool options."""
    engine_options = get_database_engine_options()
    return create_engine(database_url, **engine_options)


def get_all_tables(engine: Engine) -> Set[str]:
    """Get all table names in a database."""
    inspector = inspect(engine)
    return set(inspector.get_table_names())


def get_columns_info(engine: Engine, table_name: str) -> Dict[str, Dict]:
    """
    Get column info for a table.
    Returns dict mapping column name to {type, nullable, default, primary_key}.
    """
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)

    result = {}
    for col in columns:
        result[col["name"]] = {
            "type": str(col["type"]),
            "nullable": col["nullable"],
            "default": col.get("default"),
            "primary_key": col.get("primary_key", False),
        }
    return result


def get_unique_constraints(engine: Engine, table_name: str) -> List[Tuple[str, ...]]:
    """
    Get unique constraints for a table.
    Returns list of tuples, each tuple is the sorted column names of a constraint.
    """
    inspector = inspect(engine)
    unique_constraints = inspector.get_unique_constraints(table_name)
    # Sort columns in each constraint for consistent comparison
    return [tuple(sorted(uc["column_names"])) for uc in unique_constraints]


def get_indexes_info(engine: Engine, table_name: str) -> List[Dict]:
    """
    Get index info for a table.
    Returns list of dicts with {name, columns, unique}.
    """
    inspector = inspect(engine)
    indexes = inspector.get_indexes(table_name)

    result = []
    for idx in indexes:
        result.append({
            "name": idx["name"],
            "columns": tuple(idx["column_names"]),
            "unique": idx.get("unique", False),
        })
    return result


def format_column_type(col_info: Dict) -> str:
    """Format a column type with nullable flag for display."""
    nullable_str = "NULL" if col_info["nullable"] else "NOT NULL"
    return f"{col_info['type']:30} {nullable_str}"


def compare_schemas(
    prod_engine: Engine,
    sandbox_engine: Engine,
    specific_tables: List[str] = None
) -> Tuple[str, int, int, int]:
    """
    Compare prod and sandbox schemas.

    Returns:
        (report_text, tables_differ_count, columns_missing_count, constraints_missing_count)
    """
    prod_tables = get_all_tables(prod_engine)
    sandbox_tables = get_all_tables(sandbox_engine)

    # Determine which tables to compare
    if specific_tables:
        # Filter to only requested tables
        compare_tables = set(specific_tables) & (prod_tables | sandbox_tables)
        if not compare_tables:
            return "No matching tables found.", 0, 0, 0
    else:
        compare_tables = prod_tables | sandbox_tables

    tables_missing_from_prod = sandbox_tables - prod_tables
    tables_only_in_prod = prod_tables - sandbox_tables
    shared_tables = (prod_tables & sandbox_tables) & compare_tables

    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append(f"PROD vs SANDBOX SCHEMA DIFF  ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    report_lines.append("=" * 70)
    report_lines.append("")

    tables_differ = 0
    columns_missing_total = 0
    constraints_missing_total = 0

    # Report tables missing from prod
    if tables_missing_from_prod:
        report_lines.append("TABLES MISSING FROM PROD (in sandbox only):")
        for table in sorted(tables_missing_from_prod):
            report_lines.append(f"  - {table}")
        report_lines.append("")
        tables_differ += len(tables_missing_from_prod)

    # Report tables only in prod
    if tables_only_in_prod:
        report_lines.append("TABLES ONLY IN PROD (not in sandbox):")
        for table in sorted(tables_only_in_prod):
            report_lines.append(f"  - {table}")
        report_lines.append("")
        tables_differ += len(tables_only_in_prod)

    if not tables_missing_from_prod and not tables_only_in_prod and shared_tables:
        report_lines.append("(all tables present in both databases)")
        report_lines.append("")

    # Compare shared tables
    for table_name in sorted(shared_tables):
        prod_cols = get_columns_info(prod_engine, table_name)
        sandbox_cols = get_columns_info(sandbox_engine, table_name)

        prod_constraints = get_unique_constraints(prod_engine, table_name)
        sandbox_constraints = get_unique_constraints(sandbox_engine, table_name)

        prod_indexes = get_indexes_info(prod_engine, table_name)
        sandbox_indexes = get_indexes_info(sandbox_engine, table_name)

        missing_cols = set(sandbox_cols.keys()) - set(prod_cols.keys())
        extra_cols = set(prod_cols.keys()) - set(sandbox_cols.keys())
        type_mismatches = [
            col for col in (set(prod_cols.keys()) & set(sandbox_cols.keys()))
            if prod_cols[col]["type"] != sandbox_cols[col]["type"] or
               prod_cols[col]["nullable"] != sandbox_cols[col]["nullable"]
        ]

        missing_constraints = set(sandbox_constraints) - set(prod_constraints)
        extra_constraints = set(prod_constraints) - set(sandbox_constraints)

        missing_indexes = [
            idx for idx in sandbox_indexes
            if idx not in prod_indexes
        ]
        extra_indexes = [
            idx for idx in prod_indexes
            if idx not in sandbox_indexes
        ]

        # Only report if there are differences
        has_diffs = (missing_cols or extra_cols or type_mismatches or
                    missing_constraints or extra_constraints or
                    missing_indexes or extra_indexes)

        if has_diffs:
            report_lines.append(f"TABLE: {table_name}")

            if missing_cols:
                report_lines.append("  Missing columns in prod:")
                for col_name in sorted(missing_cols):
                    col_info = sandbox_cols[col_name]
                    report_lines.append(f"    - {col_name:25} {format_column_type(col_info)}")
                columns_missing_total += len(missing_cols)

            if extra_cols:
                report_lines.append("  Extra columns in prod (not in sandbox):")
                for col_name in sorted(extra_cols):
                    col_info = prod_cols[col_name]
                    report_lines.append(f"    - {col_name:25} {format_column_type(col_info)}")

            if type_mismatches:
                report_lines.append("  Type mismatches:")
                for col_name in sorted(type_mismatches):
                    prod_type = format_column_type(prod_cols[col_name])
                    sandbox_type = format_column_type(sandbox_cols[col_name])
                    report_lines.append(f"    - {col_name}")
                    report_lines.append(f"        prod:    {prod_type}")
                    report_lines.append(f"        sandbox: {sandbox_type}")

            if missing_constraints:
                report_lines.append("  Constraints missing in prod:")
                for constraint_cols in sorted(missing_constraints):
                    cols_str = ", ".join(constraint_cols)
                    report_lines.append(f"    - UNIQUE ({cols_str})")
                constraints_missing_total += len(missing_constraints)

            if extra_constraints:
                report_lines.append("  Extra constraints in prod (not in sandbox):")
                for constraint_cols in sorted(extra_constraints):
                    cols_str = ", ".join(constraint_cols)
                    report_lines.append(f"    - UNIQUE ({cols_str})")

            if missing_indexes:
                report_lines.append("  Indexes missing in prod:")
                for idx in missing_indexes:
                    cols_str = ", ".join(idx["columns"])
                    unique_str = " UNIQUE" if idx["unique"] else ""
                    report_lines.append(f"    - {idx['name']}: ({cols_str}){unique_str}")

            if extra_indexes:
                report_lines.append("  Extra indexes in prod (not in sandbox):")
                for idx in extra_indexes:
                    cols_str = ", ".join(idx["columns"])
                    unique_str = " UNIQUE" if idx["unique"] else ""
                    report_lines.append(f"    - {idx['name']}: ({cols_str}){unique_str}")

            report_lines.append("")
            tables_differ += 1

    # Summary
    report_lines.append("=" * 70)
    if tables_differ == 0 and columns_missing_total == 0 and constraints_missing_total == 0:
        report_lines.append("SUMMARY: Schemas are in sync!")
    else:
        summary_parts = []
        if tables_differ > 0:
            summary_parts.append(f"{tables_differ} table(s) differ")
        if columns_missing_total > 0:
            summary_parts.append(f"{columns_missing_total} column(s) missing from prod")
        if constraints_missing_total > 0:
            summary_parts.append(f"{constraints_missing_total} constraint(s) missing from prod")

        summary_line = "SUMMARY: " + ", ".join(summary_parts)
        report_lines.append(summary_line)
    report_lines.append("=" * 70)

    report_text = "\n".join(report_lines)
    return report_text, tables_differ, columns_missing_total, constraints_missing_total


def save_snapshot(report_text: str) -> str:
    """
    Save report to a timestamped file in migrations/schema_snapshots/.
    Returns the path to the saved file.
    """
    snapshots_dir = os.path.join(ROOT_DIR, "migrations", "schema_snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filepath = os.path.join(snapshots_dir, f"{timestamp}.txt")

    with open(filepath, "w") as f:
        f.write(report_text)

    return filepath


def compare(save: bool = False, specific_tables: List[str] = None) -> bool:
    """Perform the comparison."""
    print("=" * 70)
    print("PROD vs SANDBOX SCHEMA COMPARISON")
    print("=" * 70)

    # Get database URLs
    try:
        prod_url = get_production_database_url()
        sandbox_url = get_sandbox_database_url()
    except ValueError as e:
        print(f"✗ Configuration error: {e}")
        return False

    print(f"\nProd: {prod_url.split('@')[1] if '@' in prod_url else '***'}")
    print(f"Sandbox: {sandbox_url.split('@')[1] if '@' in sandbox_url else '***'}\n")

    # Create engines
    try:
        print("Connecting to databases...")
        prod_engine = create_db_engine(prod_url)
        sandbox_engine = create_db_engine(sandbox_url)

        # Test connections
        with prod_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Prod database connection successful")

        with sandbox_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Sandbox database connection successful\n")

        # Compare schemas
        print("Comparing schemas...")
        report_text, tables_differ, cols_missing, constraints_missing = compare_schemas(
            prod_engine, sandbox_engine, specific_tables
        )

        # Print report
        print(report_text)

        # Save if requested
        if save:
            filepath = save_snapshot(report_text)
            print(f"\n✓ Snapshot saved to: {filepath}")

        return True

    except OperationalError as e:
        print(f"✗ Database connection error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'prod_engine' in locals():
            prod_engine.dispose()
        if 'sandbox_engine' in locals():
            sandbox_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare prod and sandbox database schemas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python migrations/compare_prod_sandbox.py\n"
            "  python migrations/compare_prod_sandbox.py --save\n"
            "  python migrations/compare_prod_sandbox.py --tables releases users\n"
        )
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save report to migrations/schema_snapshots/YYYY-MM-DD_HHMMSS.txt"
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        metavar="TABLE",
        help="Limit comparison to specific tables"
    )
    args = parser.parse_args()

    success = compare(save=args.save, specific_tables=args.tables)
    sys.exit(0 if success else 1)
