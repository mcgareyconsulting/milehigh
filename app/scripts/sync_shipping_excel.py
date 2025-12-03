"""
Utilities for keeping OneDrive Excel shipping columns aligned with database state.

This script scans for jobs that should be in shipping-related Trello lists (Shipping
planning, Store at MHMW for shipping) and ensures the Excel sheet reflects the
expected status pattern (fitup/welded/paint = X and ship = RS or ST).

Two entry points are provided:
    - scan_shipping_excel(...) to preview mismatches
    - run_shipping_excel_sync(...) to apply updates (with optional dry-run)

Usage from command line:
    python sync_shipping_excel.py scan [--limit N] [--include-all]
    python sync_shipping_excel.py run [--limit N] [--dry-run] [--include-all]
"""

from __future__ import annotations

import argparse
import math
import sys
from typing import Dict, List, Optional

from app.logging_config import get_logger
from app.models import Job
from app.config import Config as cfg
from app.onedrive.api import get_excel_dataframe, update_excel_cell
from app.sync.services.trello_list_mapper import TrelloListMapper


logger = get_logger(__name__)


TARGET_TRELLO_LISTS = {"Shipping planning", "Store at MHMW for shipping"}

SHIP_STATUS_CONFIG = {
    "RS": {
        "expected_list": "Shipping planning",
        "status": {
            "fitup_comp": "X",
            "welded": "X",
            "paint_comp": "X",
            "ship": "RS",
        },
    },
    "ST": {
        "expected_list": "Store at MHMW for shipping",
        "status": {
            "fitup_comp": "X",
            "welded": "X",
            "paint_comp": "X",
            "ship": "ST",
        },
    },
}

EXCEL_COLUMN_MAP = {
    "fitup_comp": {"column": "M", "header": "Fitup comp"},
    "welded": {"column": "N", "header": "Welded"},
    "paint_comp": {"column": "O", "header": "Paint Comp"},
    "ship": {"column": "P", "header": "Ship"},
}

STATUS_FIELDS = ["fitup_comp", "welded", "paint_comp", "ship"]


def _build_excel_lookup(df) -> Dict[tuple, tuple]:
    """
    Build a lookup map from (job, release) to (excel_row_number, row_series).
    """
    lookup: Dict[tuple, tuple] = {}
    for idx, row in df.iterrows():
        job_val = row.get("Job #")
        release_val = row.get("Release #")

        if job_val is None:
            continue
        if isinstance(job_val, float) and math.isnan(job_val):
            continue
        if release_val is None:
            continue
        if isinstance(release_val, float) and math.isnan(release_val):
            continue

        try:
            job_key = int(job_val)
        except (TypeError, ValueError):
            continue

        release_key = str(release_val).strip()
        if not release_key:
            continue

        excel_row = idx + cfg.EXCEL_INDEX_ADJ
        lookup[(job_key, release_key)] = (excel_row, row)

        # Also support release values that may appear without trailing .0
        if release_key.endswith(".0"):
            trimmed = release_key[:-2]
            if trimmed:
                lookup[(job_key, trimmed)] = (excel_row, row)

    return lookup


def _load_excel_lookup() -> Optional[Dict[tuple, tuple]]:
    """
    Download the Excel data once and create a lookup dictionary.
    """
    try:
        df = get_excel_dataframe()
    except Exception as exc:
        logger.error("Failed to download Excel data for shipping sync", error=str(exc))
        return None

    return _build_excel_lookup(df)


def _normalize(value: Optional[str]) -> str:
    """
    Normalize status values for comparison.

    Converts None/NaN to empty string, strips whitespace, uppercases.
    """
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return str(value).strip().upper()
    return str(value).strip().upper()


def _normalize_list_name(value: Optional[str]) -> str:
    """Normalize Trello list names for comparison."""
    return (value or "").strip().lower()


def _expected_status_for_ship(ship_code: str) -> Optional[Dict[str, str]]:
    config = SHIP_STATUS_CONFIG.get(ship_code)
    return config.get("status") if config else None


def _expected_list_for_ship(ship_code: str) -> Optional[str]:
    config = SHIP_STATUS_CONFIG.get(ship_code)
    return config.get("expected_list") if config else None


def _extract_excel_status(row) -> Dict[str, str]:
    """Build a normalized status snapshot from a pandas Series row."""
    status = {}
    for field, details in EXCEL_COLUMN_MAP.items():
        status[field] = _normalize(row.get(details["header"]))
    return status


def _db_status_snapshot(job: Job) -> Dict[str, str]:
    return {
        "fitup_comp": _normalize(job.fitup_comp),
        "welded": _normalize(job.welded),
        "paint_comp": _normalize(job.paint_comp),
        "ship": _normalize(job.ship),
    }


def _build_job_identifier(job: Job) -> str:
    return f"{job.job}-{job.release}"


def evaluate_job_for_excel_sync(
    job: Job,
    excel_lookup: Optional[Dict[tuple, tuple]] = None,
) -> Dict[str, object]:
    """
    Evaluate a single job for Excel sync.

    Returns:
        dict containing:
            - job_release
            - job / release
            - trello_list_name (raw)
            - expected_trello_list
            - mapper_list (result of TrelloListMapper.determine_trello_list_from_db)
            - db_status (normalized)
            - expected_status
            - db_matches_expected (bool)
            - mapper_matches_expected (bool)
            - excel_row (int or None)
            - excel_status (normalized dict or None)
            - excel_needs_update (bool)
            - excel_missing (bool)
            - issues (list of strings)
    """
    ship_code = _normalize(job.ship)
    expected_status = _expected_status_for_ship(ship_code)
    job_release = _build_job_identifier(job)

    if not expected_status:
        return {
            "job_release": job_release,
            "job": job.job,
            "release": job.release,
            "ship": ship_code,
            "trello_list_name": job.trello_list_name,
            "expected_trello_list": None,
            "mapper_list": TrelloListMapper.determine_trello_list_from_db(job),
            "db_status": _db_status_snapshot(job),
            "expected_status": None,
            "db_matches_expected": False,
            "mapper_matches_expected": False,
            "excel_row": None,
            "excel_status": None,
            "excel_needs_update": False,
            "excel_missing": True,
            "issues": ["Ship code not in RS/ST"],
        }

    db_status = _db_status_snapshot(job)
    expected_list = _expected_list_for_ship(ship_code)
    mapper_list = TrelloListMapper.determine_trello_list_from_db(job)

    db_matches_expected = all(
        db_status[field] == expected_status[field] for field in STATUS_FIELDS
    )
    mapper_matches_expected = _normalize_list_name(mapper_list) == _normalize_list_name(
        expected_list
    )
    trello_matches_expected = _normalize_list_name(job.trello_list_name) == _normalize_list_name(
        expected_list
    )

    excel_row: Optional[int] = None
    excel_status = None
    excel_needs_update = True
    excel_missing = True
    issues: List[str] = []

    lookup_key = None
    try:
        job_key = int(job.job)
        release_key = str(job.release).strip()
        lookup_key = (job_key, release_key)
    except (TypeError, ValueError):
        issues.append("Invalid job or release identifiers")

    if lookup_key is not None and excel_lookup is not None:
        match = excel_lookup.get(lookup_key)
        if match is None and lookup_key[1].endswith(".0"):
            trimmed_key = (lookup_key[0], lookup_key[1][:-2])
            match = excel_lookup.get(trimmed_key)

        if match:
            row_number, row = match
            excel_row = row_number
            excel_status = _extract_excel_status(row)
            excel_missing = False
            excel_needs_update = any(
                excel_status[field] != expected_status[field] for field in STATUS_FIELDS
            )
        else:
            issues.append("Excel row not found")
    elif excel_lookup is None:
        issues.append("Excel lookup unavailable")

    if not db_matches_expected:
        issues.append("Database status does not match expected shipping pattern")
    if not mapper_matches_expected:
        issues.append("Mapper-derived list does not match expected list")
    if not trello_matches_expected:
        issues.append("Trello list name does not match expected shipping list")

    return {
        "job_release": job_release,
        "job": job.job,
        "release": job.release,
        "ship": ship_code,
        "trello_list_name": job.trello_list_name,
        "expected_trello_list": expected_list,
        "mapper_list": mapper_list,
        "db_status": db_status,
        "expected_status": expected_status,
        "db_matches_expected": db_matches_expected,
        "mapper_matches_expected": mapper_matches_expected,
        "trello_matches_expected": trello_matches_expected,
        "excel_row": excel_row,
        "excel_status": excel_status,
        "excel_needs_update": excel_needs_update,
        "excel_missing": excel_missing,
        "issues": issues,
    }


def _build_job_query(include_all_lists: bool = False):
    query = Job.query.filter(Job.ship.in_(SHIP_STATUS_CONFIG.keys()))
    if not include_all_lists:
        query = query.filter(Job.trello_list_name.in_(TARGET_TRELLO_LISTS))
    return query.order_by(Job.job.asc(), Job.release.asc())


def scan_shipping_excel(
    return_json: bool = False,
    limit: Optional[int] = None,
    include_all_lists: bool = False,
) -> Dict[str, object]:
    """
    Scan database records and Excel sheet for shipping mismatches.

    Args:
        return_json: if True, do not print; just return structured data.
        limit: optional limit on number of jobs inspected.
        include_all_lists: if True, do not filter by Trello list name.
    """
    query = _build_job_query(include_all_lists)
    if limit is not None and limit > 0:
        jobs = query.limit(limit).all()
    else:
        jobs = query.all()

    excel_lookup = _load_excel_lookup() if jobs else None

    logger.info(
        "Scanning jobs for shipping Excel alignment",
        total_candidates=len(jobs),
        include_all_lists=include_all_lists,
        limit=limit,
        excel_lookup_available=excel_lookup is not None,
    )

    evaluations = [
        evaluate_job_for_excel_sync(job, excel_lookup=excel_lookup) for job in jobs
    ]

    excel_missing = sum(1 for ev in evaluations if ev["excel_missing"])
    excel_needs_update = sum(
        1
        for ev in evaluations
        if ev["excel_needs_update"] and not ev["excel_missing"]
    )
    db_mismatches = sum(1 for ev in evaluations if not ev["db_matches_expected"])
    mapper_mismatches = sum(1 for ev in evaluations if not ev["mapper_matches_expected"])
    trello_mismatches = sum(1 for ev in evaluations if not ev["trello_matches_expected"])

    summary = {
        "total_jobs": len(jobs),
        "excel_rows_missing": excel_missing,
        "excel_rows_needing_update": excel_needs_update,
        "db_mismatches": db_mismatches,
        "mapper_mismatches": mapper_mismatches,
        "trello_mismatches": trello_mismatches,
        "jobs": evaluations,
        "excel_lookup_available": excel_lookup is not None,
    }

    if not return_json:
        print("=" * 70)
        print("Shipping Excel Sync - Scan Report")
        print("=" * 70)
        print(f"Total jobs inspected:        {len(jobs)}")
        print(f"Excel rows missing:          {excel_missing}")
        print(f"Excel rows needing updates:  {excel_needs_update}")
        print(f"DB status mismatches:        {db_mismatches}")
        print(f"Mapper mismatches:           {mapper_mismatches}")
        print(f"Trello list mismatches:      {trello_mismatches}")
        print("-" * 70)

        mismatched_jobs = [
            ev for ev in evaluations if ev["excel_needs_update"] or ev["issues"]
        ]
        if mismatched_jobs:
            print("Jobs requiring attention (up to 25 shown):")
            for ev in mismatched_jobs[:25]:
                print(
                    f"  - {ev['job_release']} "
                    f"(ship={ev['ship']}, trello='{ev['trello_list_name']}', excel_row={ev['excel_row']})"
                )
                if ev["excel_status"]:
                    excel_snapshot = ", ".join(
                        f"{field}={ev['excel_status'][field]}"
                        for field in STATUS_FIELDS
                    )
                else:
                    excel_snapshot = "missing"
                expected_snapshot = ", ".join(
                    f"{field}={ev['expected_status'][field]}"
                    for field in STATUS_FIELDS
                )
                print(f"      Excel:    {excel_snapshot}")
                print(f"      Expected: {expected_snapshot}")
                if ev["issues"]:
                    print(f"      Issues:   {', '.join(ev['issues'])}")
        else:
            print("No jobs require Excel updates.")
        print("=" * 70)

    return summary


def run_shipping_excel_sync(
    return_json: bool = False,
    limit: Optional[int] = None,
    dry_run: bool = False,
    include_all_lists: bool = False,
    batch_size: Optional[int] = None,
) -> Dict[str, object]:
    """
    Apply Excel updates for jobs whose shipping columns are out of sync.

    Args:
        return_json: if True, suppress print statements and return structured data.
        limit: optional limit on number of jobs inspected (same semantics as scan).
        dry_run: if True, only report what would change (no API calls).
        include_all_lists: if True, do not filter by Trello list name.
        batch_size: maximum number of jobs to update in this invocation.
    """
    scan_result = scan_shipping_excel(
        return_json=True, limit=limit, include_all_lists=include_all_lists
    )

    updates: List[Dict[str, object]] = []
    failed_updates: List[Dict[str, object]] = []

    jobs_needing_update = [
        job_info
        for job_info in scan_result["jobs"]
        if not job_info["excel_missing"] and job_info["excel_needs_update"]
    ]

    if batch_size is not None and batch_size > 0:
        jobs_to_update = jobs_needing_update[:batch_size]
    else:
        jobs_to_update = jobs_needing_update

    for job_info in jobs_to_update:
        job_update = {
            "job_release": job_info["job_release"],
            "excel_row": job_info["excel_row"],
            "expected_status": job_info["expected_status"],
            "previous_excel_status": job_info["excel_status"],
            "cells": [],
        }

        for field in STATUS_FIELDS:
            column_info = EXCEL_COLUMN_MAP[field]
            cell_value = job_info["expected_status"][field]
            cell_address = f"{column_info['column']}{job_info['excel_row']}"

            if dry_run:
                job_update["cells"].append(
                    {"field": field, "cell": cell_address, "value": cell_value, "dry_run": True}
                )
            else:
                success = update_excel_cell(cell_address, cell_value)
                job_update["cells"].append(
                    {"field": field, "cell": cell_address, "value": cell_value, "success": success}
                )
                if not success:
                    failed_updates.append(
                        {
                            "job_release": job_info["job_release"],
                            "field": field,
                            "cell": cell_address,
                            "value": cell_value,
                        }
                    )
        updates.append(job_update)

    summary = {
        "scan": scan_result,
        "dry_run": dry_run,
        "batch_size_used": batch_size,
        "jobs_considered": len(jobs_needing_update),
        "updates_attempted": len(updates),
        "cell_updates": sum(len(job_update["cells"]) for job_update in updates),
        "failed_updates": failed_updates,
    }

    if not return_json:
        print("=" * 70)
        print("Shipping Excel Sync - Run Summary")
        print("=" * 70)
        print(f"Dry run:                    {dry_run}")
        print(f"Batch size limit:           {batch_size or 'None'}")
        print(f"Jobs inspected:             {scan_result['total_jobs']}")
        print(f"Jobs needing Excel updates: {scan_result['excel_rows_needing_update']}")
        print(f"Jobs eligible this run:     {len(jobs_needing_update)}")
        print(f"Jobs updated this run:      {len(updates)}")
        print(f"Cell updates attempted:     {summary['cell_updates']}")
        if failed_updates:
            print("-" * 70)
            print("Failed cell updates:")
            for failure in failed_updates:
                print(
                    f"  - {failure['job_release']} {failure['field']} "
                    f"({failure['cell']} -> {failure['value']})"
                )
        else:
            print("No failed cell updates.")
        print("=" * 70)

    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync OneDrive Excel shipping columns with database state."
    )
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Preview mismatches without updating Excel")
    scan_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of jobs to inspect",
    )
    scan_parser.add_argument(
        "--include-all",
        action="store_true",
        help="Include jobs regardless of Trello list assignment",
    )

    run_parser = subparsers.add_parser("run", help="Update Excel to match shipping status")
    run_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of jobs to inspect",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report updates without calling OneDrive API",
    )
    run_parser.add_argument(
        "--include-all",
        action="store_true",
        help="Include jobs regardless of Trello list assignment",
    )
    run_parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Limit the number of jobs updated in a single run",
    )

    parser.set_defaults(command="scan")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    from app import create_app as create_app_factory

    app = create_app_factory()
    with app.app_context():
        limit = getattr(args, "limit", None)
        include_all = getattr(args, "include_all", False)
        if args.command == "run":
            dry_run = getattr(args, "dry_run", False)
            batch_size = getattr(args, "batch_size", None)
            run_shipping_excel_sync(
                limit=limit,
                dry_run=dry_run,
                include_all_lists=include_all,
                batch_size=batch_size,
            )
        else:
            scan_shipping_excel(
                limit=limit,
                include_all_lists=include_all,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

