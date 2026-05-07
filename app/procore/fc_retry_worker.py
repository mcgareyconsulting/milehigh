"""Nightly retry worker for collecting Final PDF Pack (FC drawing) viewer URLs.

Procore's Final PDF Pack can be created up to ~24 hours after a release lands
in our job log. The first-attempt fetch during card creation often misses it,
leaving Releases.viewer_url NULL forever. This worker re-runs the lookup once
a night for recently-released rows that still don't have a viewer_url.

Recency is gated on the Excel `released` date (the Releases model has no
`created_at` column). 7 days is enough headroom past the 24h Procore lag and
keeps stale rows from getting retried indefinitely.
"""

import time
from datetime import datetime, timedelta, date

from app.logging_config import get_logger
from app.models import db, Releases, FcCollectionRun
from app.procore.procore import (
    add_procore_link_to_trello_card,
    get_viewer_url_for_job,
)

logger = get_logger(__name__)

LOOKBACK_DAYS = 7
RETENTION_RUNS = 30
PER_RELEASE_SLEEP_SECONDS = 0.5


def _candidate_identifiers():
    """Snapshot of (job, release) for releases the worker should retry.

    We pull plain identifiers — not ORM objects — so that a mid-run DB error
    can't poison later iterations via lazy attribute loads.
    """
    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    rows = (
        db.session.query(Releases.job, Releases.release)
        .filter(Releases.viewer_url.is_(None))
        .filter(Releases.is_active.is_(True))
        .filter(Releases.released.isnot(None))
        .filter(Releases.released >= cutoff)
        .order_by(Releases.released.desc())
        .all()
    )
    return [(job, release) for job, release in rows]


def _try_one(job, rel):
    """Run the existing per-release Procore→Trello flow and classify the result.

    Returns (bucket, entry) where bucket is 'succeeded'|'still_missing'|'errored'
    and entry is a dict suitable for FcCollectionRun.details. On exception we
    rollback the session so a broken transaction state can't leak into the
    next iteration.
    """
    base = {"job": job, "release": rel}
    try:
        result = add_procore_link_to_trello_card(job, rel)
    except Exception as exc:
        logger.exception("FC retry errored", job=job, release=rel)
        try:
            db.session.rollback()
        except Exception:
            pass
        return "errored", {**base, "error": str(exc)}

    if result and result.get("viewer_url"):
        return "succeeded", {**base, "viewer_url": result["viewer_url"]}

    # Helper returns None on any miss (no card_id, no project, no submittals,
    # no final pdfs). Re-run the read-only lookup to surface the real reason
    # for the run record, without retrying the Trello write.
    try:
        diag = get_viewer_url_for_job(job, rel)
        reason = (diag or {}).get("error") or "no viewer_url returned"
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        reason = f"diagnostic lookup raised: {exc}"
    return "still_missing", {**base, "reason": reason}


def _prune_runs():
    """Keep only the most recent RETENTION_RUNS rows in fc_collection_runs."""
    keepers = (
        db.session.query(FcCollectionRun.id)
        .order_by(FcCollectionRun.run_at.desc())
        .limit(RETENTION_RUNS)
        .subquery()
    )
    db.session.query(FcCollectionRun).filter(
        ~FcCollectionRun.id.in_(db.session.query(keepers))
    ).delete(synchronize_session=False)


def retry_missing_fc_viewer_urls(trigger="cron"):
    """Run one pass: retry Procore FC fetch for eligible releases, persist a
    FcCollectionRun row, prune to the last RETENTION_RUNS rows.

    Args:
        trigger: 'cron' for the nightly schedule, 'manual' when fired from the
                 admin endpoint.
    Returns:
        dict with run_id and the bucket counts.
    """
    started_at = datetime.utcnow()
    started_perf = time.perf_counter()

    candidates = _candidate_identifiers()
    logger.info(
        "FC retry worker starting",
        trigger=trigger,
        candidates=len(candidates),
        lookback_days=LOOKBACK_DAYS,
    )

    buckets = {"succeeded": [], "still_missing": [], "errored": []}

    for idx, (job, rel) in enumerate(candidates):
        bucket, entry = _try_one(job, rel)
        buckets[bucket].append(entry)
        logger.debug(
            "FC retry per-release",
            job=entry["job"],
            release=entry["release"],
            bucket=bucket,
        )
        if idx < len(candidates) - 1:
            time.sleep(PER_RELEASE_SLEEP_SECONDS)

    duration_ms = int((time.perf_counter() - started_perf) * 1000)

    # Defensive: if the session is in a broken transaction state from an
    # earlier per-release DB error, clear it before writing the run record.
    try:
        db.session.rollback()
    except Exception:
        pass

    run = FcCollectionRun(
        run_at=started_at,
        trigger=trigger,
        candidates=len(candidates),
        succeeded=len(buckets["succeeded"]),
        still_missing=len(buckets["still_missing"]),
        errored=len(buckets["errored"]),
        duration_ms=duration_ms,
        details=buckets,
    )
    db.session.add(run)
    db.session.flush()
    _prune_runs()
    db.session.commit()

    logger.info(
        "FC retry worker finished",
        trigger=trigger,
        run_id=run.id,
        candidates=len(candidates),
        succeeded=run.succeeded,
        still_missing=run.still_missing,
        errored=run.errored,
        duration_ms=duration_ms,
    )

    return {
        "run_id": run.id,
        "candidates": run.candidates,
        "succeeded": run.succeeded,
        "still_missing": run.still_missing,
        "errored": run.errored,
        "duration_ms": duration_ms,
    }
