"""Read side of the Sunbelt rental report.

Serves the latest (or a chosen) snapshot with each rental reconciled to our jobs,
computes discrepancy flags relative to today and current job state (overdue /
on-finished-job / cost-outlier), and diffs against the previous snapshot
(new / changed / unchanged / returned).
"""

from datetime import date

from flask import current_app

from app.models import (
    db, SunbeltRentalSnapshot, SunbeltRental, Releases, Submittals,
)

DEFAULT_COST_OUTLIER_USD = 12000
DEFAULT_DURATION_OUTLIER_DAYS = 150

COMPLETE_STAGES = ("Complete", "Install Complete")


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _thresholds():
    cost = current_app.config.get("SUNBELT_COST_OUTLIER_USD", DEFAULT_COST_OUTLIER_USD)
    days = current_app.config.get("SUNBELT_DURATION_OUTLIER_DAYS", DEFAULT_DURATION_OUTLIER_DAYS)
    return float(cost), int(days)


def finished_jobs_set():
    """Job numbers (int) whose work is effectively done but may still be renting.

    A job qualifies when either:
      - it has releases and ALL of them are archived, OR in the complete zone
        (stage in Complete/Install Complete AND job_comp='X' AND invoiced='X'); or
      - it has no release at all but has submittals and ALL are Closed.
    """
    finished = set()

    jobs = {}
    for job, is_archived, stage, job_comp, invoiced in db.session.query(
        Releases.job, Releases.is_archived, Releases.stage,
        Releases.job_comp, Releases.invoiced,
    ).all():
        if job is None:
            continue
        jobs.setdefault(int(job), []).append((is_archived, stage, job_comp, invoiced))

    def _row_done(is_archived, stage, job_comp, invoiced):
        if is_archived:
            return True
        return (
            stage in COMPLETE_STAGES
            and (job_comp or "").upper() == "X"
            and (invoiced or "").upper() == "X"
        )

    release_jobs = set(jobs.keys())
    for job, rows in jobs.items():
        if rows and all(_row_done(*r) for r in rows):
            finished.add(job)

    # Submittal-only jobs: no release, every submittal Closed.
    subs = {}
    for project_number, status in db.session.query(
        Submittals.project_number, Submittals.status,
    ).all():
        jn = _to_int(project_number)
        if jn is None:
            continue
        subs.setdefault(jn, []).append((status or "").strip().lower())
    for jn, statuses in subs.items():
        if jn in release_jobs:
            continue
        if statuses and all(s == "closed" for s in statuses):
            finished.add(jn)

    return finished


def _weeks_between(start, end):
    if not start or not end or end <= start:
        return 0.0
    return (end - start).days / 7.0


def compute_discrepancies(rental, today, finished_jobs, thresholds):
    """Return a list of discrepancy dicts for one rental.

    Each: {type, severity, label, detail}. Types: overdue, on_finished_job,
    cost_outlier. Computed relative to `today` and current job state.
    """
    cost_limit, duration_limit = thresholds
    flags = []

    est = rental.est_return_date
    if est and est < today:
        still_billing = rental.billed_through is None or rental.billed_through >= est
        if still_billing:
            days_over = (today - est).days
            flags.append({
                "type": "overdue",
                "severity": "high" if days_over >= 30 else "medium",
                "label": f"{days_over}d overdue",
                "detail": f"Est. return {est.isoformat()} has passed; still on rent.",
            })

    if rental.matched_job_number is not None and rental.matched_job_number in finished_jobs:
        flags.append({
            "type": "on_finished_job",
            "severity": "high",
            "label": "Job finished",
            "detail": "Job's releases are shipped/complete or submittals all closed, "
                      "but the unit is still on rent.",
        })

    week_rate = float(rental.week_rate) if rental.week_rate is not None else 0.0
    duration_days = (today - rental.date_rented).days if rental.date_rented else 0
    accrued = _weeks_between(rental.date_rented, today) * week_rate
    if (week_rate > 0 and accrued >= cost_limit) or (duration_days >= duration_limit):
        flags.append({
            "type": "cost_outlier",
            "severity": "medium",
            "label": f"~${accrued:,.0f} / {duration_days}d",
            "detail": "Long-running or high-accrued-cost rental.",
        })

    return flags


def _resolve_snapshot(snapshot_id):
    if snapshot_id is not None:
        return db.session.get(SunbeltRentalSnapshot, snapshot_id)
    return (
        SunbeltRentalSnapshot.query
        .order_by(SunbeltRentalSnapshot.snapshot_date.desc(),
                  SunbeltRentalSnapshot.id.desc())
        .first()
    )


def _previous_snapshot(snapshot):
    # Append-only ingest => id order is chronological.
    return (
        SunbeltRentalSnapshot.query
        .filter(SunbeltRentalSnapshot.id < snapshot.id)
        .order_by(SunbeltRentalSnapshot.id.desc())
        .first()
    )


def _list_snapshots(limit=52):
    return (
        SunbeltRentalSnapshot.query
        .order_by(SunbeltRentalSnapshot.snapshot_date.desc(),
                  SunbeltRentalSnapshot.id.desc())
        .limit(limit).all()
    )


def _rental_key(r):
    """Per-line identity. A single contract can carry several equipment lines
    (e.g. long forks + the telehandler they attach to), so the unit's equipment
    number is part of the key, not the contract alone."""
    return (r.contract_number, r.equipment_number)


def _change_vs_prev(current, previous):
    if previous is None:
        return "new"
    changed = (
        current.est_return_date != previous.est_return_date
        or current.week_rate != previous.week_rate
        or current.billed_through != previous.billed_through
    )
    return "changed" if changed else "unchanged"


def list_snapshots():
    """Snapshot metadata for the history dropdown (most recent first)."""
    return [s.to_dict() for s in _list_snapshots()]


def get_report(snapshot_id=None):
    """Build the full report payload for the latest (or chosen) snapshot."""
    snapshot = _resolve_snapshot(snapshot_id)
    if snapshot is None:
        return {
            "snapshot": None,
            "previous_snapshot": None,
            "rentals": [],
            "returned": [],
            "totals": {"rental_count": 0, "flagged_count": 0, "weekly_total": 0.0},
            "snapshots": list_snapshots(),
        }

    today = date.today()
    finished = finished_jobs_set()
    thresholds = _thresholds()

    prev = _previous_snapshot(snapshot)
    prev_map = {}
    if prev:
        for r in prev.rentals.all():
            prev_map[_rental_key(r)] = r

    current_keys = set()
    rentals_out = []
    weekly_total = 0.0
    flagged = 0

    for r in snapshot.rentals.order_by(
        SunbeltRental.matched_job_number.asc(),
        SunbeltRental.id.asc(),
    ).all():
        current_keys.add(_rental_key(r))
        d = r.to_dict()
        flags = compute_discrepancies(r, today, finished, thresholds)
        d["discrepancies"] = flags
        d["change"] = _change_vs_prev(r, prev_map.get(_rental_key(r)))
        if flags:
            flagged += 1
        if r.week_rate is not None:
            weekly_total += float(r.week_rate) * (r.quantity or 1)
        rentals_out.append(d)

    returned = []
    if prev:
        for key, r in prev_map.items():
            if key not in current_keys:
                returned.append({
                    "contract_number": r.contract_number,
                    "equipment_type": r.equipment_type,
                    "matched_job_number": r.matched_job_number,
                    "matched_project_name": r.matched_project_name,
                })

    return {
        "snapshot": snapshot.to_dict(),
        "previous_snapshot": prev.to_dict() if prev else None,
        "rentals": rentals_out,
        "returned": returned,
        "totals": {
            "rental_count": len(rentals_out),
            "flagged_count": flagged,
            "weekly_total": round(weekly_total, 2),
        },
        "snapshots": list_snapshots(),
    }
