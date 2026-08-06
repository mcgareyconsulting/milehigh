"""Nightly retry worker for collecting Final PDF Pack (FC drawing) viewer URLs.

Procore's Final PDF Pack can be created up to ~24 hours after a release lands
in our job log, so the first-attempt fetch during card creation often misses
it and `Releases.viewer_url` stays NULL/empty. This worker re-runs the lookup
once a night for recently-released rows that still lack a viewer_url (BUG-1).

Recency is gated primarily on the Excel `released` date (no created_at on
Releases). LOOKBACK_DAYS (30) covers Procore lag plus FC set updates that
re-open the gap; rows with no released date use last_updated_at instead.

Procore calls are batched the same way `backfill_fc_drawing_viewer_urls.py`
does: company_id once, project listing once, submittals once per unique
project; per-submittal workflow_data / detail fetch is unavoidable.
"""

import time
from collections import defaultdict
from datetime import datetime, timedelta, date

from sqlalchemy import or_

from app.api.helpers import active_releases_filter
from app.logging_config import get_logger
from app.models import db, Releases, FcCollectionRun
from app.procore.procore import (
    get_companies_list,
    fetch_all_projects,
    fetch_all_submittals,
    submittals_for_release,
    get_final_pdf_viewers,
)
from app.trello.api import add_procore_link

logger = get_logger(__name__)

# Procore can lag ~24h on Final PDF Pack; FC set updates can re-open the gap.
# 30 days covers multi-burst projects that stay gray after the first week.
LOOKBACK_DAYS = 30
RETENTION_RUNS = 30
PER_RELEASE_SLEEP_SECONDS = 0.5


def _safe_rollback():
    """Clear a broken transaction state without raising. A rollback can itself
    fail when the underlying psycopg2 connection has dropped; in that case the
    next session use will re-establish the connection automatically."""
    try:
        db.session.rollback()
    except Exception:
        pass


def _candidate_snapshot():
    """Snapshot of (id, job, release, trello_card_id) for releases the worker
    should retry. Plain identifiers only — mid-run DB errors must not poison
    later iterations via lazy attribute loads.

    Missing viewer_url includes NULL *and* empty string (UI treats both as
    gray). Active filter matches active_releases_filter (NULL is_active counts
    as active). Prefer released-date recency; also pick up rows with no
    released date if last_updated_at is recent so they are not stuck gray forever.
    """
    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    cutoff_dt = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    missing_url = or_(
        Releases.viewer_url.is_(None),
        Releases.viewer_url == "",
    )
    recent = or_(
        (Releases.released.isnot(None) & (Releases.released >= cutoff)),
        (
            Releases.released.is_(None)
            & Releases.last_updated_at.isnot(None)
            & (Releases.last_updated_at >= cutoff_dt)
        ),
    )
    rows = (
        db.session.query(
            Releases.id, Releases.job, Releases.release, Releases.trello_card_id
        )
        .filter(active_releases_filter())
        .filter(missing_url)
        .filter(recent)
        .order_by(Releases.id.desc())
        .all()
    )
    return [
        (rid, job, release, card_id) for rid, job, release, card_id in rows
    ]


def _persist_viewer_url(release_id, job, release, viewer_url, card_id, submittal_id=None):
    """Write viewer_url (and submittal_id) to the Releases row and add the FC
    Drawing link to Trello, mirroring the original first-attempt flow in
    `add_procore_link_to_trello_card`.

    Prefer primary key when provided so job# wrap (same job-release, different
    project name) does not update the wrong row.
    """
    record = None
    if release_id is not None:
        record = Releases.query.get(release_id)
    if record is None:
        record = Releases.resolve(job, release)
    if record is None:
        return
    record.viewer_url = viewer_url
    if submittal_id is not None:
        record.procore_submittal_id = str(submittal_id)
    db.session.commit()
    if card_id:
        try:
            add_procore_link(card_id, viewer_url)
        except Exception as link_err:
            logger.warning(
                "FC retry: persisted viewer_url but failed to add Trello link",
                job=job, release=release, error=str(link_err),
            )


def _process_release(project_id, release_id, job, release, card_id, all_submittals):
    base = {"job": job, "release": release, "release_id": release_id}
    matching = submittals_for_release(all_submittals, job, release)
    if not matching:
        return "still_missing", {**base, "reason": "no matching For Construction submittal"}
    try:
        final_pdfs = get_final_pdf_viewers(project_id, matching)
    except Exception as exc:
        logger.exception("FC retry: final_pdf_viewers raised", job=job, release=release)
        _safe_rollback()
        return "errored", {**base, "error": f"final pdf fetch raised: {exc}"}
    if not final_pdfs:
        return "still_missing", {**base, "reason": "no Final PDF Pack on submittal yet"}

    viewer_url = final_pdfs[0]["viewer_url"]
    submittal_id = final_pdfs[0].get("submittal_id")
    try:
        _persist_viewer_url(
            release_id, job, release, viewer_url, card_id, submittal_id=submittal_id
        )
    except Exception as exc:
        logger.exception("FC retry: persist failed", job=job, release=release)
        _safe_rollback()
        return "errored", {**base, "error": f"persist failed: {exc}"}
    return "succeeded", {**base, "viewer_url": viewer_url, "submittal_id": submittal_id}


def _process_candidates(candidates, project_map, buckets):
    by_project = defaultdict(list)
    for release_id, job, release, card_id in candidates:
        pid = project_map.get(str(job))
        if pid is None:
            buckets["still_missing"].append({
                "job": job, "release": release,
                "reason": "no Procore project for job",
            })
        else:
            by_project[pid].append((release_id, job, release, card_id))

    for project_id, group in by_project.items():
        try:
            all_submittals = fetch_all_submittals(project_id)
        except Exception as exc:
            logger.exception("FC retry: submittals fetch raised", project_id=project_id)
            for release_id, job, release, _ in group:
                buckets["errored"].append({
                    "job": job, "release": release,
                    "error": f"submittals fetch raised: {exc}",
                })
            continue

        for idx, (release_id, job, release, card_id) in enumerate(group):
            bucket, entry = _process_release(
                project_id, release_id, job, release, card_id, all_submittals
            )
            buckets[bucket].append(entry)
            logger.debug("FC retry per-release", job=job, release=release, bucket=bucket)
            if idx < len(group) - 1:
                time.sleep(PER_RELEASE_SLEEP_SECONDS)


def _prune_runs():
    """Keep only the most recent RETENTION_RUNS rows. Two-step (fetch IDs to
    keep, then delete the rest) avoids a nested-subquery DELETE."""
    keep_ids = [
        row.id for row in
        db.session.query(FcCollectionRun.id)
        .order_by(FcCollectionRun.run_at.desc())
        .limit(RETENTION_RUNS)
        .all()
    ]
    if not keep_ids:
        return
    (db.session.query(FcCollectionRun)
        .filter(~FcCollectionRun.id.in_(keep_ids))
        .delete(synchronize_session=False))


def retry_missing_fc_viewer_urls(trigger="cron"):
    """Run one pass: retry Procore FC fetch for eligible releases, persist a
    FcCollectionRun row, prune to the last RETENTION_RUNS rows.

    Returns a dict with run_id and the bucket counts.
    """
    started_at = datetime.utcnow()
    started_perf = time.perf_counter()

    candidates = _candidate_snapshot()
    logger.info(
        "FC retry worker starting",
        trigger=trigger, candidates=len(candidates), lookback_days=LOOKBACK_DAYS,
    )

    buckets = {"succeeded": [], "still_missing": [], "errored": []}

    if candidates:
        try:
            company_id = get_companies_list()
        except Exception as exc:
            logger.exception("FC retry: company lookup raised")
            company_id = None
            company_error = f"company lookup raised: {exc}"
        else:
            company_error = None if company_id else "Procore returned no company_id"

        if company_error:
            for _rid, job, release, _ in candidates:
                buckets["errored"].append({"job": job, "release": release, "error": company_error})
        else:
            try:
                project_map = fetch_all_projects(company_id)
            except Exception as exc:
                logger.exception("FC retry: project listing raised")
                for _rid, job, release, _ in candidates:
                    buckets["errored"].append({
                        "job": job, "release": release,
                        "error": f"project listing raised: {exc}",
                    })
            else:
                _process_candidates(candidates, project_map, buckets)

    duration_ms = int((time.perf_counter() - started_perf) * 1000)

    _safe_rollback()

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
        trigger=trigger, run_id=run.id, candidates=run.candidates,
        succeeded=run.succeeded, still_missing=run.still_missing,
        errored=run.errored, duration_ms=duration_ms,
    )

    return {
        "run_id": run.id,
        "candidates": run.candidates,
        "succeeded": run.succeeded,
        "still_missing": run.still_missing,
        "errored": run.errored,
        "duration_ms": duration_ms,
    }
