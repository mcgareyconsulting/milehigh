#!/usr/bin/env python3
"""
Command-line script to preview scheduling changes.

Usage:
    python app/scripts/preview_scheduling.py [--reference-date YYYY-MM-DD] [--show-all] [--summary-only]
    
Options:
    --reference-date YYYY-MM-DD  Reference date for calculations (defaults to today)
    --show-all                   Show all jobs, not just those with changes
    --summary-only               Show only summary, not detailed diffs
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app, db
from app.brain.job_log.scheduling.preview import run_preview_script
import argparse


def main():
    parser = argparse.ArgumentParser(
        description='Preview scheduling changes without updating the database'
    )
    parser.add_argument(
        '--reference-date',
        type=str,
        help='Reference date for calculations (YYYY-MM-DD format, defaults to today)'
    )
    parser.add_argument(
        '--show-all',
        action='store_true',
        help='Show all jobs, not just those with changes'
    )
    parser.add_argument(
        '--summary-only',
        action='store_true',
        help='Show only summary statistics, not detailed diffs'
    )
    
    args = parser.parse_args()
    
    # Create Flask app context
    app = create_app()
    
    with app.app_context():
        try:
            preview_results = run_preview_script(
                reference_date_str=args.reference_date,
                show_all=args.show_all,
                detailed=not args.summary_only
            )
            
            # Exit with appropriate code
            if preview_results.get('jobs_with_changes', 0) > 0:
                sys.exit(0)  # Success, but there are changes
            else:
                sys.exit(0)  # Success, no changes
                
        except Exception as e:
            print(f"\nFatal error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()

