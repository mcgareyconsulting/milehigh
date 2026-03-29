"""Run the unified fab_order renumbering migration.

Usage:
    python run_renumber.py              # dry run (default)
    python run_renumber.py --commit     # actually commit changes
"""
import sys
from app import create_app
from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders

app = create_app()

dry_run = "--commit" not in sys.argv

with app.app_context():
    if dry_run:
        print("=== DRY RUN (pass --commit to apply) ===\n")
    stats = renumber_fab_orders(dry_run=dry_run)
    print(f"\nResults: {stats}")
