"""Background execution for Banana Boy PDF reviews.

The Claude call takes minutes, so the review runs off-request on a small thread pool.
Mirrors app/brain/meetings/learn.py: a module-level pool, a `start_review(app, id)`
entry point, and a job that pushes an app context, does the work, and always cleans up
the session. Never crashes the worker — any failure is recorded on the row as `error`.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.models import db, BBDrawingReview, ReleaseDrawingVersion, Releases, Notification
from app.logging_config import get_logger
from app.brain.job_log.features.pdf_markup.storage import read_pdf
from app.brain.pdf_review import service
from app.brain.pdf_review.report import build_report, notification_message
from app.brain.meetings.owner_match import release_owner_user

logger = get_logger(__name__)

_REVIEW_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bb-pdf-review")


def start_review(app, review_id: int) -> None:
    """Queue a background BB review job for a pending BBDrawingReview row."""
    _REVIEW_POOL.submit(_run_review_job, app, review_id)


def start_submittal_review(app, review_id: int, *, procore_submittal_id: str,
                           attachment_id, job_release: str, model=None) -> None:
    """Queue a background BB review for a submittal-keyed (Procore drawing) review row.

    The drawing bytes must already be in the per-attachment pull cache (the endpoint
    pulls-if-needed before enqueuing). Mirrors start_review but for the submittal path,
    which has no release/PM so it skips the PM notification.
    """
    _REVIEW_POOL.submit(_run_submittal_review_job, app, review_id,
                        procore_submittal_id, attachment_id, job_release, model)


def _run_submittal_review_job(app, review_id, procore_submittal_id, attachment_id,
                              job_release, model) -> None:
    with app.app_context():
        try:
            review = db.session.get(BBDrawingReview, review_id)
            if not review:
                logger.error("bb_review_row_missing", review_id=review_id)
                return

            from app.brain.pdf_review import cache as procore_pdf_cache
            pdf_bytes = procore_pdf_cache.read(procore_submittal_id, attachment_id)
            if not pdf_bytes:
                _fail(review, "drawing missing from cache — pull it again")
                return

            result = service.review(pdf_bytes, job_release, model=model)
            if result is None:
                _fail(review, "review call failed (no API key or request error) — see logs")
                return

            review.status = "complete"
            review.findings = result["findings"]
            review.model = result.get("model")
            review.input_tokens = result.get("input_tokens")
            review.output_tokens = result.get("output_tokens")
            review.completed_at = datetime.utcnow()
            db.session.commit()
            logger.info("bb_submittal_document_reviewed", review_id=review_id,
                        submittal_id=procore_submittal_id, attachment_id=attachment_id,
                        findings=len(result["findings"]), model=result.get("model"))

            # Ledger the review spend (own transaction, post-commit). No PM notification:
            # the submittal path is release-less, so there's no owner to notify.
            from app.services import ai_usage
            ai_usage.record(
                "pdf_review",
                model=result.get("model"),
                input_tokens=result.get("input_tokens") or 0,
                output_tokens=result.get("output_tokens") or 0,
                user_id=review.requested_by_user_id,
                entity_type="drawing_review",
                entity_id=review.id,
            )
        except Exception as e:  # noqa: BLE001 — record + log, never crash the worker
            logger.error("bb_submittal_review_job_failed", review_id=review_id,
                         error=str(e), exc_info=True)
            db.session.rollback()
            _safe_fail(review_id, str(e))
        finally:
            db.session.remove()


def _job_release(release: Releases) -> str:
    if not release:
        return "unknown"
    job = str(release.job or "").strip()
    rel = str(release.release or "").strip()
    return f"{job}-{rel}".strip("-") or "unknown"


def _run_review_job(app, review_id: int) -> None:
    with app.app_context():
        try:
            review = db.session.get(BBDrawingReview, review_id)
            if not review:
                logger.error("bb_review_row_missing", review_id=review_id)
                return

            version = db.session.get(ReleaseDrawingVersion, review.drawing_version_id)
            if not version or version.is_deleted:
                _fail(review, "drawing version not found or deleted")
                return

            try:
                pdf_bytes = read_pdf(version.storage_key)
            except FileNotFoundError:
                _fail(review, "drawing file missing on disk")
                return

            release = db.session.get(Releases, review.release_id)
            result = service.review(pdf_bytes, _job_release(release))

            if result is None:
                _fail(review, "review call failed (no API key or request error) — see logs")
                return

            review.status = "complete"
            review.findings = result["findings"]
            review.model = result.get("model")
            review.input_tokens = result.get("input_tokens")
            review.output_tokens = result.get("output_tokens")
            review.completed_at = datetime.utcnow()
            db.session.commit()
            logger.info("bb_review_complete", review_id=review_id,
                        findings=len(result["findings"]))

            # Ledger the review spend (cost computed from tokens — the review row
            # stores no cost column). Own transaction, post-commit.
            from app.services import ai_usage
            ai_usage.record(
                "pdf_review",
                model=result.get("model"),
                input_tokens=result.get("input_tokens") or 0,
                output_tokens=result.get("output_tokens") or 0,
                user_id=review.requested_by_user_id,
                entity_type="drawing_review",
                entity_id=review.id,
            )

            _notify_pm(review, release, result["findings"])
        except Exception as e:  # noqa: BLE001 — record + log, never crash the worker
            logger.error("bb_review_job_failed", review_id=review_id, error=str(e), exc_info=True)
            db.session.rollback()
            _safe_fail(review_id, str(e))
        finally:
            db.session.remove()


def _notify_pm(review: BBDrawingReview, release: Releases, findings) -> None:
    """Drop a bell notification for the job's PM once a review completes.

    Best-effort: a missing/unmapped PM or a notification failure must never fail the
    review itself (it's already committed complete). Only fires when there's something
    for the PM to act on — a fully-cleared review stays quiet.
    """
    try:
        report = build_report(findings, _job_release(release))
        actionable = sum(v for k, v in report["tally"].items() if k != "cleared")
        if not actionable:
            return
        pm_id = release_owner_user(release)
        if not pm_id:
            logger.info("bb_review_pm_unresolved", review_id=review.id,
                        pm=getattr(release, "pm", None))
            return
        db.session.add(Notification(
            user_id=pm_id,
            type="bb_review",
            message=notification_message(report),
            bb_drawing_review_id=review.id,
        ))
        db.session.commit()
        logger.info("bb_review_pm_notified", review_id=review.id, pm_user_id=pm_id,
                    actionable=actionable)
    except Exception as e:  # noqa: BLE001 — never let notification failure fail the review
        logger.error("bb_review_notify_failed", review_id=review.id, error=str(e))
        db.session.rollback()


def _fail(review: BBDrawingReview, message: str) -> None:
    review.status = "error"
    review.error = message
    review.completed_at = datetime.utcnow()
    db.session.commit()
    logger.info("bb_review_error", review_id=review.id, error=message)


def _safe_fail(review_id: int, message: str) -> None:
    """Mark a review errored after an unexpected exception (fresh session)."""
    try:
        review = db.session.get(BBDrawingReview, review_id)
        if review and review.status == "pending":
            review.status = "error"
            review.error = message[:2000]
            review.completed_at = datetime.utcnow()
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()
