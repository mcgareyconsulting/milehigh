#!/usr/bin/env python3
"""
Standalone script to run incremental seeding.
This script can be run outside of the main Flask app to update the database
with missing jobs from the Trello/Excel cross-check.

Usage:
    python run_incremental_seed.py
"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.seed import incremental_seed_missing_jobs, run_incremental_seed_example

def main():
    """Main function to run incremental seeding."""
    print("🚀 Starting Incremental Seeding Script")
    print("=" * 50)
    
    # Create Flask app context
    app = create_app()
    
    with app.app_context():
        try:
            # Run the incremental seeding
            result = run_incremental_seed_example()
            
            print("\n" + "=" * 50)
            print("✅ Incremental seeding completed successfully!")
            print(f"📊 Operation ID: {result['operation_id']}")
            print(f"🆕 New jobs added: {result['new_jobs_created']}")
            
            return 0
            
        except Exception as e:
            print(f"\n❌ Incremental seeding failed: {e}")
            return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
