"""
Scan all jobs in the database and create Trello cards for jobs that don't have them.

This script:
- Queries all jobs from the database
- Filters out jobs that already have trello_card_id (duplicates)
- Determines the appropriate list for each job based on stage
- Creates cards with all standard features (notes, fab order, FC drawing, num guys, etc.)
- Works across all tracked lists

Usage:
    python -m app.scripts.scan_and_create_cards          # Preview only (dry run)
    python -m app.scripts.scan_and_create_cards --execute  # Actually create cards
    python -m app.scripts.scan_and_create_cards --limit 10  # Limit to 10 jobs
"""

import argparse
from app.trello.scanner import scan_and_create_cards_for_all_jobs
from app.logging_config import get_logger

logger = get_logger(__name__)


if __name__ == "__main__":
    from app import create_app
    
    parser = argparse.ArgumentParser(description="Scan all jobs and create Trello cards for jobs without cards")
    parser.add_argument("--execute", action="store_true", 
                       help="Actually create cards (default: dry run only)")
    parser.add_argument("--limit", type=int, help="Maximum number of jobs to process")
    
    args = parser.parse_args()
    
    app = create_app()
    with app.app_context():
        results = scan_and_create_cards_for_all_jobs(dry_run=not args.execute, limit=args.limit)
        
        # Print summary
        print("=" * 80)
        print("SCAN AND CREATE CARDS RESULTS")
        print("=" * 80)
        print(f"\n📊 SUMMARY:")
        print(f"  Total jobs without cards: {results.get('total_jobs', 0)}")
        
        if args.execute:
            print(f"  ✅ Created: {results.get('created', 0)} cards")
            print(f"  ❌ Failed: {results.get('failed', 0)} jobs")
            print(f"  ⚠️  Skipped: {results.get('skipped', 0)} jobs")
        else:
            print(f"  Would create: {results.get('created', 0)} cards")
            print(f"\n💡 TIP: Run with --execute to actually create the cards")
        
        if results.get('failed_details'):
            print(f"\n❌ FAILED JOBS:")
            for item in results['failed_details'][:10]:  # Show first 10
                print(f"  - {item.get('identifier', 'Unknown')}: {item.get('error', 'Unknown error')}")
        
        print("\n" + "=" * 80)

