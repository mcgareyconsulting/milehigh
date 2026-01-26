#!/usr/bin/env python3
"""Test script for preview_csv_jobs_data function."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.seed import preview_csv_jobs_data

if __name__ == "__main__":
    try:
        result = preview_csv_jobs_data(max_rows_to_display=10)
        print(f"\n✅ Function completed successfully!")
        print(f"Summary: {result.get('summary')}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)



