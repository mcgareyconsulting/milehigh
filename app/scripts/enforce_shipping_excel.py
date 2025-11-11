"""
Ensure Excel staging columns match database jobs in shipping lists.

For every job with ship value 'RS' or 'ST':
  * Ensure the database staging flags are X/X/X and ship matches.
  * Locate the corresponding Excel row and update Fitup/Welded/Paint/Ship columns
    to X/X/X/RS or X/X/X/ST as appropriate.

Outputs a JSON summary detailing updates, missing rows, and failures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from app.config import Config as cfg
from app.logging_config import get_logger
from app.models import Job, db
from app.onedrive.api import get_excel_dataframe, update_excel_cell

logger = get_logger(__name__)


ALLOWED_SHIP_VALUES = {"RS", "ST"}

# Excel ship column mapping (column letter, column name in DataFrame)
EXCEL_SHIP_COLUMN: Tuple[str, str] = ("P", "Ship")


def _normalize(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


@dataclass
class ExcelUpdateResult:
    cell: str
    old_value: Optional[str]
    new_value: str
    success: bool


@dataclass
class JobProcessingResult:
    job_release: str
    job_id: int
    expected_ship: str
    db_updated: bool
    excel_updates: List[ExcelUpdateResult] = field(default_factory=list)
    excel_missing: bool = False


def _build_excel_index(df: pd.DataFrame) -> Dict[Tuple[int, str], Tuple[int, pd.Series]]:
    """
    Build a lookup dictionary to map (job, release) -> (excel_row_number, row_series).
    """
    lookup: Dict[Tuple[int, str], Tuple[int, pd.Series]] = {}
    for df_index, row in df.iterrows():
        job_val = row.get("Job #")
        release_val = row.get("Release #")
        if pd.isna(job_val) or pd.isna(release_val):
            continue
        try:
            job_int = int(job_val)
        except (TypeError, ValueError):
            continue
        release_str = str(release_val).strip()
        excel_row_number = df_index + cfg.EXCEL_INDEX_ADJ
        lookup[(job_int, release_str)] = (excel_row_number, row)
    return lookup


def _stringify(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return str(value)


def enforce_shipping_excel(
    dry_run: bool = False,
    update_db: bool = True,
    batch_size: Optional[int] = None,
    include_details: bool = True,
) -> Dict[str, object]:
    """
    Ensure Excel staging columns align with database jobs marked as RS/ST.

    Args:
        dry_run: If True, do not perform Excel updates; only report.
        update_db: If True, normalize Job records before Excel updates.
        batch_size: If provided, stream jobs from the database in batches of this size.
        include_details: If False, omit per-job result details to minimize memory usage.

    Returns:
        Summary dictionary describing operations performed.
    """
    logger.info(
        "Starting shipping Excel enforcement",
        dry_run=dry_run,
        update_db=update_db,
        batch_size=batch_size,
        include_details=include_details,
    )

    query = Job.query.filter(Job.ship.in_(list(ALLOWED_SHIP_VALUES))).order_by(Job.id)
    total_jobs = query.count()
    logger.info("Jobs fetched for enforcement", total=total_jobs)

    if total_jobs == 0:
        return {
            "jobs_processed": 0,
            "db_updates": 0,
            "excel_updates": 0,
            "excel_missing": [],
            "results": [],
            "dry_run": dry_run,
            "update_db": update_db,
            "batch_size": batch_size,
            "include_details": include_details,
        }

    if batch_size and batch_size > 0:
        job_iterator: Iterable[Job] = query.yield_per(batch_size)
    else:
        job_iterator = query

    df = get_excel_dataframe()
    excel_lookup = _build_excel_index(df)

    db_updates = 0
    excel_updates_count = 0
    excel_missing: List[str] = []
    results: List[JobProcessingResult] = [] if include_details else []
    jobs_processed = 0
    jobs_with_excel_updates = 0

    for job in job_iterator:
        jobs_processed += 1
        expected_ship = _normalize(job.ship)
        job_release_key = f"{job.job}-{job.release}"

        if expected_ship not in ALLOWED_SHIP_VALUES:
            logger.warning(
                "Skipping job with unexpected ship value",
                job_release=job_release_key,
                ship_value=job.ship,
            )
            continue

        # Ensure DB ship value is correct when updates requested
        db_changed = False
        if update_db and _normalize(job.ship) != expected_ship:
            job.ship = expected_ship
            db_changed = True

            job.last_updated_at = datetime.utcnow()
            job.source_of_update = "System"
            db_updates += 1

        result: Optional[JobProcessingResult] = None
        if include_details:
            result = JobProcessingResult(
                job_release=job_release_key,
                job_id=job.id,
                expected_ship=expected_ship,
                db_updated=db_changed if update_db else False,
            )

        key = (int(job.job), str(job.release).strip())
        excel_entry = excel_lookup.get(key)
        if not excel_entry:
            logger.warning("Excel row not found", job_release=job_release_key)
            excel_missing.append(job_release_key)
            if include_details and result:
                result.excel_missing = True
                results.append(result)
            if not update_db:
                db.session.expunge(job)
            continue

        excel_row_number, excel_row = excel_entry
        job_had_excel_update = False

        column_letter, excel_column_name = EXCEL_SHIP_COLUMN
        expected_value = expected_ship
        current_excel_value = _normalize(excel_row.get(excel_column_name))

        if current_excel_value != expected_value:
            cell_address = f"{column_letter}{excel_row_number}"
            logger.info(
                "Excel ship value mismatch detected",
                job_release=job_release_key,
                current=current_excel_value,
                expected=expected_value,
                cell=cell_address,
            )

            success = True
            if not dry_run:
                success = update_excel_cell(cell_address, expected_value)
                if success:
                    excel_updates_count += 1
                else:
                    logger.error(
                        "Failed to update Excel ship cell",
                        job_release=job_release_key,
                        cell=cell_address,
                        expected=expected_value,
                    )
            else:
                excel_updates_count += 1

            job_had_excel_update = True

            if include_details and result:
                result.excel_updates.append(
                    ExcelUpdateResult(
                        cell=cell_address,
                        old_value=_stringify(excel_row.get(excel_column_name)),
                        new_value=expected_value,
                        success=success,
                    )
                )

        if job_had_excel_update:
            jobs_with_excel_updates += 1
            if include_details and result:
                results.append(result)
        elif include_details and result:
            # Only include jobs without updates if details requested
            results.append(result)

        if not update_db:
            db.session.expunge(job)

    if update_db:
        if db_updates:
            db.session.commit()
            logger.info("Database updates committed", count=db_updates)
        else:
            db.session.rollback()

    summary = {
        "jobs_processed": jobs_processed,
        "db_updates": db_updates if update_db else 0,
        "excel_updates": excel_updates_count,
        "excel_missing": excel_missing,
        "jobs_with_excel_updates": jobs_with_excel_updates,
        "dry_run": dry_run,
        "update_db": update_db,
        "batch_size": batch_size,
        "include_details": include_details,
    }

    if include_details:
        summary["results"] = [
            {
                "job_release": res.job_release,
                "job_id": res.job_id,
                "expected_ship": res.expected_ship,
                "db_updated": res.db_updated,
                "excel_missing": res.excel_missing,
                "excel_updates": [
                    {
                        "cell": upd.cell,
                        "old_value": upd.old_value,
                        "new_value": upd.new_value,
                        "success": upd.success,
                    }
                    for upd in res.excel_updates
                ],
            }
            for res in results
        ]

    logger.info(
        "Shipping Excel enforcement completed",
        jobs_processed=summary["jobs_processed"],
        db_updates=summary["db_updates"],
        excel_updates=summary["excel_updates"],
        missing=len(summary["excel_missing"]),
    )

    return summary


def main():
    from app import create_app

    app = create_app()
    with app.app_context():
        summary = enforce_shipping_excel(dry_run=False)
        print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()

