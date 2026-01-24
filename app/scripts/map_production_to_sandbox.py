"""
Map job-release and fab_order from production database to sandbox database.

This script matches jobs in the production database with corresponding jobs
in the sandbox database using the (job, release) tuple as the primary key,
and maps the fab_order field from production to sandbox.

Features:
- Matches jobs by (job, release) tuple
- Handles missing jobs gracefully
- Provides detailed reporting
- Supports dry-run mode
- Includes field mapping capabilities

Usage:
    python -m app.scripts.map_production_to_sandbox [--dry-run]
    python app/scripts/map_production_to_sandbox.py [--dry-run]

Options:
    --dry-run: Show what would be done without making changes
"""

import argparse
import os
import sys
from typing import Dict, List, Tuple, Set, Optional
from dataclasses import dataclass

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add parent directory to path to import app modules
sys.path.insert(0, ROOT_DIR)

# Load environment variables
load_dotenv()


@dataclass
class MappingResult:
    """Result of mapping a single job."""
    job_id: int
    release: str
    matched: bool
    fab_order_updated: bool
    old_fab_order: Optional[float] = None
    new_fab_order: Optional[float] = None
    error: Optional[str] = None


def get_production_database_url() -> str:
    """Get the production database URL."""
    database_url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "PRODUCTION_DATABASE_URL or DATABASE_URL must be set."
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
            "SANDBOX_DATABASE_URL must be set."
        )
    
    # Convert postgres:// to postgresql:// if needed
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    return database_url


def fetch_jobs_from_database(engine: Engine, db_name: str) -> pd.DataFrame:
    """
    Fetch jobs from a database.
    
    Args:
        engine: SQLAlchemy engine
        db_name: Name of the database (for logging)
    
    Returns:
        DataFrame with job, release, and fab_order columns
    """
    try:
        df = pd.read_sql_query(
            "SELECT id, job, release, fab_order FROM jobs ORDER BY job, release",
            engine
        )
        print(f"✓ Fetched {len(df)} jobs from {db_name} database")
        return df
    except Exception as e:
        print(f"✗ Error fetching jobs from {db_name}: {e}")
        raise


def map_jobs(
    production_df: pd.DataFrame,
    sandbox_df: pd.DataFrame
) -> Tuple[List[MappingResult], Dict[str, int]]:
    """
    Map production jobs to sandbox jobs by (job, release) tuple.
    
    Args:
        production_df: DataFrame from production database
        sandbox_df: DataFrame from sandbox database
    
    Returns:
        Tuple of (mapping results list, statistics dict)
    """
    stats = {
        "total_production": len(production_df),
        "total_sandbox": len(sandbox_df),
        "matched": 0,
        "fab_order_differences": 0,
        "not_found_in_sandbox": 0,
        "fab_order_updates": 0,
    }
    
    results = []
    
    # Create lookup dict for sandbox jobs by (job, release)
    sandbox_lookup: Dict[Tuple[int, str], Dict] = {}
    for _, row in sandbox_df.iterrows():
        key = (row['job'], row['release'])
        sandbox_lookup[key] = {
            'id': row['id'],
            'fab_order': row['fab_order']
        }
    
    # Match each production job to sandbox
    for _, prod_row in production_df.iterrows():
        job_key = (prod_row['job'], prod_row['release'])
        
        if job_key in sandbox_lookup:
            sandbox_job = sandbox_lookup[job_key]
            old_fab_order = sandbox_job['fab_order']
            new_fab_order = prod_row['fab_order']
            
            fab_order_updated = old_fab_order != new_fab_order
            
            if fab_order_updated:
                stats["fab_order_differences"] += 1
            
            result = MappingResult(
                job_id=prod_row['job'],
                release=prod_row['release'],
                matched=True,
                fab_order_updated=fab_order_updated,
                old_fab_order=old_fab_order,
                new_fab_order=new_fab_order
            )
            stats["matched"] += 1
        else:
            result = MappingResult(
                job_id=prod_row['job'],
                release=prod_row['release'],
                matched=False,
                fab_order_updated=False,
                error=f"Job not found in sandbox database"
            )
            stats["not_found_in_sandbox"] += 1
        
        results.append(result)
    
    return results, stats


def apply_mappings(
    engine: Engine,
    results: List[MappingResult],
    dry_run: bool = False
) -> int:
    """
    Apply fab_order updates to sandbox database.
    
    Args:
        engine: SQLAlchemy engine for sandbox database
        results: List of mapping results
        dry_run: If True, don't make actual changes
    
    Returns:
        Number of successful updates
    """
    updates_count = 0
    failed_count = 0
    
    # Filter for jobs that need fab_order updates
    jobs_to_update = [r for r in results if r.matched and r.fab_order_updated]
    
    if not jobs_to_update:
        print("No fab_order updates needed.")
        return 0
    
    print(f"\n{'Applying Updates' if not dry_run else 'Simulating Updates'}...")
    print(f"Total updates to apply: {len(jobs_to_update)}")
    
    if dry_run:
        for result in jobs_to_update:
            print(
                f"  [DRY RUN] Job {result.job_id}-{result.release}: "
                f"fab_order {result.old_fab_order} → {result.new_fab_order}"
            )
        return len(jobs_to_update)
    
    # Apply updates in batches
    try:
        with engine.begin() as conn:
            for result in jobs_to_update:
                try:
                    conn.execute(
                        text(
                            "UPDATE jobs SET fab_order = :fab_order "
                            "WHERE job = :job AND release = :release"
                        ),
                        {
                            "fab_order": result.new_fab_order,
                            "job": result.job_id,
                            "release": result.release
                        }
                    )
                    updates_count += 1
                    print(
                        f"  ✓ Job {result.job_id}-{result.release}: "
                        f"fab_order {result.old_fab_order} → {result.new_fab_order}"
                    )
                except Exception as e:
                    failed_count += 1
                    print(
                        f"  ✗ Job {result.job_id}-{result.release}: {e}"
                    )
        
        print(f"✓ Successfully updated {updates_count} jobs")
        if failed_count > 0:
            print(f"⚠ Failed to update {failed_count} jobs")
        
        return updates_count
        
    except Exception as e:
        print(f"✗ Error applying updates: {e}")
        return 0


def print_summary(results: List[MappingResult], stats: Dict[str, int]) -> None:
    """Print a detailed summary of the mapping results."""
    print("\n" + "=" * 80)
    print("MAPPING SUMMARY")
    print("=" * 80)
    
    print(f"\nDatabase Stats:")
    print(f"  Production Jobs: {stats['total_production']}")
    print(f"  Sandbox Jobs: {stats['total_sandbox']}")
    
    print(f"\nMapping Results:")
    print(f"  Matched: {stats['matched']}")
    print(f"  Not Found in Sandbox: {stats['not_found_in_sandbox']}")
    print(f"  fab_order Differences: {stats['fab_order_differences']}")
    
    # Show details of jobs not found
    not_found = [r for r in results if not r.matched]
    if not_found:
        print(f"\nJobs Not Found in Sandbox ({len(not_found)}):")
        for result in not_found[:10]:  # Show first 10
            print(f"  - {result.job_id}-{result.release}")
        if len(not_found) > 10:
            print(f"  ... and {len(not_found) - 10} more")
    
    # Show details of fab_order updates needed
    fab_order_updates = [r for r in results if r.matched and r.fab_order_updated]
    if fab_order_updates:
        print(f"\nfab_order Updates Needed ({len(fab_order_updates)}):")
        for result in fab_order_updates[:10]:  # Show first 10
            print(
                f"  - {result.job_id}-{result.release}: "
                f"{result.old_fab_order} → {result.new_fab_order}"
            )
        if len(fab_order_updates) > 10:
            print(f"  ... and {len(fab_order_updates) - 10} more")


def map_production_to_sandbox(dry_run: bool = False) -> bool:
    """
    Main function to map production jobs to sandbox.
    
    Args:
        dry_run: If True, don't make actual changes
    
    Returns:
        True if successful, False otherwise
    """
    print("=" * 80)
    print("MAP PRODUCTION → SANDBOX")
    print("=" * 80)
    
    if dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")
    
    # Get database URLs
    try:
        production_url = get_production_database_url()
        sandbox_url = get_sandbox_database_url()
    except ValueError as e:
        print(f"✗ Configuration error: {e}")
        return False
    
    print(f"Source (Production): {production_url.split('@')[1] if '@' in production_url else '***'}")
    print(f"Target (Sandbox): {sandbox_url.split('@')[1] if '@' in sandbox_url else '***'}\n")
    
    # Create engines
    try:
        production_engine = create_engine(production_url, echo=False)
        sandbox_engine = create_engine(sandbox_url, echo=False)
        
        # Test connections
        print("Testing database connections...")
        with production_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Production database connection successful")
        
        with sandbox_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Sandbox database connection successful\n")
        
        # Fetch jobs
        print("Fetching jobs from databases...")
        production_df = fetch_jobs_from_database(production_engine, "Production")
        sandbox_df = fetch_jobs_from_database(sandbox_engine, "Sandbox")
        
        # Map jobs
        print("\nMapping jobs...")
        results, stats = map_jobs(production_df, sandbox_df)
        
        # Print summary
        print_summary(results, stats)
        
        # Apply mappings
        if stats["fab_order_differences"] > 0:
            print(f"\n{'=' * 80}")
            updated = apply_mappings(sandbox_engine, results, dry_run=dry_run)
            stats["fab_order_updates"] = updated
        
        # Final status
        print("\n" + "=" * 80)
        if dry_run:
            print("✓ Dry run completed successfully")
        else:
            print(f"✓ Successfully updated {stats['fab_order_updates']} fab_order values")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'production_engine' in locals():
            production_engine.dispose()
        if 'sandbox_engine' in locals():
            sandbox_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Map job-release and fab_order from production to sandbox database."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()
    
    success = map_production_to_sandbox(dry_run=args.dry_run)
    sys.exit(0 if success else 1)

