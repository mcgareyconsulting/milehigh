"""
Database comparison script for sandbox vs production.

This script:
1. Connects to both sandbox and production databases
2. Queries all jobs from each database
3. Compares them to find jobs in one but not the other (both directions)
4. Returns a comprehensive report

Usage:
    python -m app.scripts.db_comparison          # Run comparison
    Or call via Flask endpoint: /db-comparison
"""

import os
import sys
from typing import Dict, List, Set, Tuple, Optional
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

# Add parent directory to path to import app modules
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

# Load environment variables
load_dotenv()

from app.db_config import get_sandbox_database_config, get_production_database_config
from app.logging_config import get_logger

logger = get_logger(__name__)


def get_jobs_from_database(database_url: str, engine_options: Optional[Dict] = None, label: str = "database"):
    """
    Query all jobs from a database.
    
    Args:
        database_url: Database connection URL
        engine_options: Optional SQLAlchemy engine options
        label: Label for logging (e.g., "sandbox" or "production")
    
    Returns:
        Tuple of (list of job dicts, set of (job, release) tuples):
        - List of job dictionaries with job details
        - Set of (job, release) tuples for quick lookup
    """
    try:
        # Create engine
        if engine_options:
            engine = create_engine(database_url, **engine_options)
        else:
            engine = create_engine(database_url)
        
        # Create session
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # Query all jobs - using raw SQL for compatibility
            query = text("""
                SELECT job, release, job_name, description, 
                       trello_card_id, trello_card_name, trello_list_name,
                       stage, last_updated_at, source_of_update
                FROM jobs
                ORDER BY job, release
            """)
            
            result = session.execute(query)
            rows = result.fetchall()
            
            # Convert to list of dicts for easier handling
            jobs = []
            job_releases = set()
            
            for row in rows:
                job_num = row[0]
                release = str(row[1]) if row[1] else ""
                job_key = (job_num, release)
                job_releases.add(job_key)
                
                jobs.append({
                    'job': job_num,
                    'release': release,
                    'job_name': row[2] if row[2] else '',
                    'description': row[3] if row[3] else '',
                    'trello_card_id': row[4] if row[4] else None,
                    'trello_card_name': row[5] if row[5] else None,
                    'trello_list_name': row[6] if row[6] else None,
                    'stage': row[7] if row[7] else None,
                    'last_updated_at': row[8].isoformat() if row[8] else None,
                    'source_of_update': row[9] if row[9] else None,
                })
            
            logger.info(f"Retrieved {len(jobs)} jobs from {label}")
            return jobs, job_releases
            
        finally:
            session.close()
            engine.dispose()
            
    except OperationalError as e:
        logger.error(f"Database connection error for {label}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error querying {label} database: {e}")
        raise


def compare_databases(return_json: bool = False) -> Dict:
    """
    Compare sandbox and production databases to find differences.
    
    Args:
        return_json: If True, returns a dictionary. If False, prints results.
    
    Returns:
        Dictionary with comparison results
    """
    try:
        # Get database configurations
        sandbox_url, sandbox_options = get_sandbox_database_config()
        production_url, production_options = get_production_database_config()
        
        logger.info("Starting database comparison: sandbox vs production")
        
        # Get jobs from both databases
        sandbox_jobs, sandbox_keys = get_jobs_from_database(
            sandbox_url, sandbox_options, "sandbox"
        )
        production_jobs, production_keys = get_jobs_from_database(
            production_url, production_options, "production"
        )
        
        # Find differences
        # Jobs in sandbox but not in production
        only_in_sandbox_keys = sandbox_keys - production_keys
        only_in_sandbox = [
            job for job in sandbox_jobs 
            if (job['job'], job['release']) in only_in_sandbox_keys
        ]
        
        # Jobs in production but not in sandbox
        only_in_production_keys = production_keys - sandbox_keys
        only_in_production = [
            job for job in production_jobs 
            if (job['job'], job['release']) in only_in_production_keys
        ]
        
        # Jobs in both (for reference)
        in_both_keys = sandbox_keys & production_keys
        
        # Build result
        result = {
            'timestamp': datetime.utcnow().isoformat(),
            'summary': {
                'sandbox_total': len(sandbox_jobs),
                'production_total': len(production_jobs),
                'in_both': len(in_both_keys),
                'only_in_sandbox': len(only_in_sandbox),
                'only_in_production': len(only_in_production),
            },
            'only_in_sandbox': only_in_sandbox,
            'only_in_production': only_in_production,
            'only_in_sandbox_identifiers': [
                f"{job['job']}-{job['release']}" for job in only_in_sandbox
            ],
            'only_in_production_identifiers': [
                f"{job['job']}-{job['release']}" for job in only_in_production
            ],
        }
        
        if not return_json:
            # Print results
            print("=" * 80)
            print("DATABASE COMPARISON: Sandbox vs Production")
            print("=" * 80)
            print(f"\nTimestamp: {result['timestamp']}")
            print("\nSUMMARY:")
            print(f"  Sandbox total jobs:     {result['summary']['sandbox_total']}")
            print(f"  Production total jobs:  {result['summary']['production_total']}")
            print(f"  Jobs in both:           {result['summary']['in_both']}")
            print(f"  Only in sandbox:        {result['summary']['only_in_sandbox']}")
            print(f"  Only in production:     {result['summary']['only_in_production']}")
            
            if only_in_sandbox:
                print("\n" + "=" * 80)
                print("JOBS ONLY IN SANDBOX:")
                print("=" * 80)
                for job in only_in_sandbox:
                    print(f"  {job['job']}-{job['release']}: {job['job_name']}")
                    if job['description']:
                        print(f"    Description: {job['description']}")
                    if job['trello_list_name']:
                        print(f"    Trello List: {job['trello_list_name']}")
                    if job['stage']:
                        print(f"    Stage: {job['stage']}")
                    print()
            
            if only_in_production:
                print("=" * 80)
                print("JOBS ONLY IN PRODUCTION:")
                print("=" * 80)
                for job in only_in_production:
                    print(f"  {job['job']}-{job['release']}: {job['job_name']}")
                    if job['description']:
                        print(f"    Description: {job['description']}")
                    if job['trello_list_name']:
                        print(f"    Trello List: {job['trello_list_name']}")
                    if job['stage']:
                        print(f"    Stage: {job['stage']}")
                    print()
        
        return result
        
    except ValueError as e:
        error_msg = f"Configuration error: {e}"
        logger.error(error_msg)
        if return_json:
            return {'error': error_msg}
        else:
            print(f"ERROR: {error_msg}")
            return None
    except Exception as e:
        error_msg = f"Comparison failed: {e}"
        logger.error(error_msg, exc_info=True)
        if return_json:
            return {'error': error_msg}
        else:
            print(f"ERROR: {error_msg}")
            return None


if __name__ == "__main__":
    # Run comparison when executed directly
    compare_databases(return_json=False)

