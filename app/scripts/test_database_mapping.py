"""
Test script demonstrating database mapping functionality.

This script shows various ways to use the DatabaseMappingService.
It runs in dry-run mode by default and doesn't make actual changes.

Usage:
    python app/scripts/test_database_mapping.py
    python app/scripts/test_database_mapping.py --apply  # Makes actual changes
"""

import os
import sys
import argparse
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine

# Add parent directory to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

from app.services.database_mapping import (
    DatabaseMappingService,
    FieldMapping,
    map_production_fab_order_to_sandbox
)

# Load environment variables
load_dotenv()


def get_engines():
    """Get production and sandbox database engines."""
    prod_url = os.environ.get("PRODUCTION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    sandbox_url = os.environ.get("SANDBOX_DATABASE_URL")
    
    if not prod_url or not sandbox_url:
        print("❌ Error: Missing database URLs")
        print("   Set PRODUCTION_DATABASE_URL and SANDBOX_DATABASE_URL")
        return None, None
    
    # Fix postgres:// URLs
    if prod_url.startswith("postgres://"):
        prod_url = prod_url.replace("postgres://", "postgresql://", 1)
    if sandbox_url.startswith("postgres://"):
        sandbox_url = sandbox_url.replace("postgres://", "postgresql://", 1)
    
    prod_engine = create_engine(prod_url, echo=False)
    sandbox_engine = create_engine(sandbox_url, echo=False)
    
    return prod_engine, sandbox_engine


def test_basic_fab_order_mapping(apply: bool = False):
    """Test 1: Basic fab_order mapping."""
    print("\n" + "=" * 80)
    print("TEST 1: Basic fab_order Mapping")
    print("=" * 80)
    
    prod_engine, sandbox_engine = get_engines()
    if not prod_engine:
        return False
    
    try:
        print("\n📊 Running mapping...")
        stats = map_production_fab_order_to_sandbox(
            prod_engine,
            sandbox_engine,
            dry_run=not apply
        )
        
        print(f"\n✅ Results:")
        print(f"   Total Production Jobs: {stats.total_source}")
        print(f"   Total Sandbox Jobs: {stats.total_target}")
        print(f"   Matched: {stats.matched}")
        print(f"   Not Found: {stats.not_found}")
        print(f"   Updated: {stats.updated}")
        print(f"   Errors: {stats.errors}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        prod_engine.dispose()
        sandbox_engine.dispose()


def test_custom_field_mapping(apply: bool = False):
    """Test 2: Custom field mapping with multiple fields."""
    print("\n" + "=" * 80)
    print("TEST 2: Custom Multi-Field Mapping")
    print("=" * 80)
    
    prod_engine, sandbox_engine = get_engines()
    if not prod_engine:
        return False
    
    try:
        print("\n📊 Fetching data with custom columns...")
        
        # Fetch additional columns
        prod_jobs = DatabaseMappingService.fetch_jobs(
            prod_engine,
            ["job", "release", "fab_order", "paint_color"]
        )
        sandbox_jobs = DatabaseMappingService.fetch_jobs(
            sandbox_engine,
            ["job", "release", "fab_order", "paint_color"]
        )
        
        print(f"   Production: {len(prod_jobs)} jobs")
        print(f"   Sandbox: {len(sandbox_jobs)} jobs")
        
        # Define field mappings
        field_mappings = [
            FieldMapping("fab_order", "fab_order"),
            FieldMapping("paint_color", "paint_color"),
        ]
        
        print("\n🔗 Mapping jobs...")
        results, stats = DatabaseMappingService.map_jobs_by_key(
            prod_jobs,
            sandbox_jobs,
            field_mappings=field_mappings
        )
        
        print(f"\n✅ Mapping Results:")
        print(f"   Matched: {stats.matched}")
        print(f"   Not Found: {stats.not_found}")
        print(f"   fab_order updates: {stats.field_updates.get('fab_order', 0)}")
        print(f"   paint_color updates: {stats.field_updates.get('paint_color', 0)}")
        
        # Show sample updates
        updates_needed = [r for r in results if r.matched and r.fields_updated]
        if updates_needed:
            print(f"\n📋 Sample Updates (first 3):")
            for result in updates_needed[:3]:
                for field, (old_val, new_val) in result.fields_updated.items():
                    print(f"   Job {result.job_id}-{result.release}: {field}")
                    print(f"      {old_val} → {new_val}")
            if len(updates_needed) > 3:
                print(f"   ... and {len(updates_needed) - 3} more")
        
        # Apply if requested
        if apply and updates_needed:
            print("\n⚙️  Applying updates...")
            updated = DatabaseMappingService.apply_field_updates(
                sandbox_engine,
                results,
                dry_run=False
            )
            print(f"   ✅ Updated {updated} jobs")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        prod_engine.dispose()
        sandbox_engine.dispose()


def test_single_job_lookup(apply: bool = False):
    """Test 3: Single job lookup and update."""
    print("\n" + "=" * 80)
    print("TEST 3: Single Job Lookup and Update")
    print("=" * 80)
    
    prod_engine, sandbox_engine = get_engines()
    if not prod_engine:
        return False
    
    try:
        # Find a sample job to test with
        print("\n🔍 Finding a sample job...")
        prod_df = DatabaseMappingService.fetch_jobs(
            prod_engine,
            ["job", "release", "fab_order"],
            where_clause="fab_order IS NOT NULL LIMIT 1"
        )
        
        if prod_df.empty:
            print("   ℹ️  No jobs with fab_order found in production")
            return True
        
        sample_job = prod_df.iloc[0]
        job_id = int(sample_job['job'])
        release = sample_job['release']
        
        print(f"   Found: Job {job_id}-{release}")
        print(f"   Production fab_order: {sample_job['fab_order']}")
        
        # Look it up in sandbox
        print(f"\n🔎 Looking up in sandbox...")
        sandbox_job = DatabaseMappingService.get_job_by_key(
            sandbox_engine,
            job_id,
            release,
            columns=["job", "release", "fab_order"]
        )
        
        if not sandbox_job:
            print(f"   ℹ️  Job {job_id}-{release} not found in sandbox")
            return True
        
        print(f"   Found in sandbox")
        print(f"   Current fab_order: {sandbox_job.get('fab_order')}")
        
        # Update if different
        new_fab_order = sample_job['fab_order']
        old_fab_order = sandbox_job.get('fab_order')
        
        if old_fab_order != new_fab_order:
            print(f"\n✏️  Updating fab_order...")
            print(f"   {old_fab_order} → {new_fab_order}")
            
            if apply:
                success = DatabaseMappingService.update_job_fields(
                    sandbox_engine,
                    job_id,
                    release,
                    {"fab_order": new_fab_order},
                    dry_run=False
                )
                if success:
                    print("   ✅ Update successful")
                else:
                    print("   ❌ Update failed")
            else:
                print("   [DRY RUN MODE - no actual update]")
        else:
            print(f"   ✅ fab_order already matches ({old_fab_order})")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        prod_engine.dispose()
        sandbox_engine.dispose()


def test_with_logging_callback(apply: bool = False):
    """Test 4: Using custom logging callback."""
    print("\n" + "=" * 80)
    print("TEST 4: Mapping with Custom Logging")
    print("=" * 80)
    
    prod_engine, sandbox_engine = get_engines()
    if not prod_engine:
        return False
    
    # Define custom logger
    def custom_logger(level: str, message: str):
        icons = {
            "error": "❌",
            "warning": "⚠️",
            "info": "ℹ️",
            "debug": "📝"
        }
        icon = icons.get(level, "•")
        print(f"   {icon} [{level.upper()}] {message}")
    
    try:
        print("\n📊 Running mapping with logging...")
        
        prod_jobs = DatabaseMappingService.fetch_jobs(
            prod_engine,
            ["job", "release", "fab_order"]
        )
        sandbox_jobs = DatabaseMappingService.fetch_jobs(
            sandbox_engine,
            ["job", "release", "fab_order"]
        )
        
        field_mappings = [
            FieldMapping("fab_order", "fab_order")
        ]
        
        results, stats = DatabaseMappingService.map_jobs_by_key(
            prod_jobs,
            sandbox_jobs,
            field_mappings=field_mappings
        )
        
        print(f"\n📋 Applying updates with logging:")
        updated = DatabaseMappingService.apply_field_updates(
            sandbox_engine,
            results,
            dry_run=not apply,
            log_callback=custom_logger
        )
        
        print(f"\n✅ Summary:")
        print(f"   Updated: {updated}")
        print(f"   Matched: {stats.matched}")
        print(f"   Not Found: {stats.not_found}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        prod_engine.dispose()
        sandbox_engine.dispose()


def main(apply: bool = False):
    """Run all tests."""
    print("=" * 80)
    print("DATABASE MAPPING TEST SUITE")
    print("=" * 80)
    
    mode = "APPLY" if apply else "DRY RUN"
    print(f"\n🔧 Mode: {mode}")
    print("   Set --apply flag to make actual changes\n")
    
    tests = [
        ("Basic fab_order Mapping", test_basic_fab_order_mapping),
        ("Custom Field Mapping", test_custom_field_mapping),
        ("Single Job Lookup", test_single_job_lookup),
        ("Custom Logging", test_with_logging_callback),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func(apply=apply)
            results.append((test_name, "✅ PASS" if success else "❌ FAIL"))
        except Exception as e:
            results.append((test_name, f"❌ ERROR: {e}"))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    for test_name, result in results:
        print(f"{test_name:.<50} {result}")
    
    passed = sum(1 for _, r in results if "PASS" in r)
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    
    return all("PASS" in r for _, r in results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test database mapping functionality"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (otherwise runs in dry-run mode)"
    )
    args = parser.parse_args()
    
    success = main(apply=args.apply)
    sys.exit(0 if success else 1)

