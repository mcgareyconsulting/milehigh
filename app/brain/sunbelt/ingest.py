"""The single ingestion seam for Sunbelt rental reports.

`ingest_snapshot` persists a parsed report as one snapshot plus reconciled rental
rows. The admin CSV upload calls it today; a future bb@mhmw.com email adapter
(the M365 Graph pipeline) will call the very same function with source='email'.
"""

from datetime import date

from app.models import db, SunbeltRentalSnapshot, SunbeltRental
from app.brain.sunbelt.matching import RentalMatcher
from app.logging_config import get_logger

logger = get_logger(__name__)


def ingest_snapshot(rows, snapshot_date=None, source="upload", filename=None, created_by=None):
    """Persist a parsed Sunbelt report as a new snapshot + reconciled rentals.

    Args:
        rows: output of app.brain.sunbelt.parser.parse_sunbelt_csv
        snapshot_date: effective report date (defaults to today)
        source: 'upload' | 'email'
        filename: original filename, for display/audit
        created_by: user email/identifier

    Returns the created SunbeltRentalSnapshot.
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    snapshot = SunbeltRentalSnapshot(
        snapshot_date=snapshot_date,
        source=source,
        filename=filename,
        row_count=len(rows),
        created_by=created_by,
    )
    db.session.add(snapshot)
    db.session.flush()  # assign snapshot.id before inserting children

    matcher = RentalMatcher()
    for row in rows:
        job_number, project_name, method = matcher.resolve(
            row.get("po_number"), row.get("job_location")
        )
        db.session.add(SunbeltRental(
            snapshot_id=snapshot.id,
            contract_number=row.get("contract_number"),
            sunbelt_job_label=row.get("sunbelt_job_label"),
            po_number=row.get("po_number"),
            job_location=row.get("job_location"),
            ordered_by=row.get("ordered_by"),
            equipment_type=row.get("equipment_type"),
            equipment_number=row.get("equipment_number"),
            make=row.get("make"),
            model=row.get("model"),
            quantity=row.get("quantity") or 1,
            est_return_date=row.get("est_return_date"),
            day_rate=row.get("day_rate"),
            week_rate=row.get("week_rate"),
            four_week_rate=row.get("four_week_rate"),
            billed_through=row.get("billed_through"),
            date_rented=row.get("date_rented"),
            matched_job_number=job_number,
            matched_project_name=project_name,
            match_method=method,
        ))

    db.session.commit()
    logger.info(
        "sunbelt_snapshot_ingested",
        snapshot_id=snapshot.id, rows=len(rows), source=source,
    )
    return snapshot
