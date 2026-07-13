"""REST endpoints for Banana Boy PDF review (admin-only).

Registered on brain_bp under /brain:
  POST /releases/<release_id>/drawing/versions/<vid>/bb-review  — enqueue a review (202)
  GET  /releases/<release_id>/drawing/versions/<vid>/bb-review  — latest review status + findings

Admin-only, matching the "admin-only Banana Boy" decision. The POST returns immediately
(202) with a `pending` row; the review runs on a background thread (worker.py). The
frontend panel polls the GET until status is `complete` or `error`.
"""
from flask import jsonify, current_app

from app.brain import brain_bp
from app.auth.utils import admin_required, login_required, get_current_user
from flask import request

from app.models import (
    ReleaseDrawingVersion, BBDrawingReview, BBReviewFeedback, Releases, db,
)
from app.logging_config import get_logger

from app.brain.pdf_review.worker import start_review
from app.brain.pdf_review.report import build_report
from app.brain.meetings.owner_match import release_owner_user

logger = get_logger(__name__)


def _load_version(release_id, version_id):
    version = db.session.get(ReleaseDrawingVersion, version_id)
    if not version or version.release_id != release_id or version.is_deleted:
        return None
    return version


@brain_bp.route(
    '/releases/<int:release_id>/drawing/versions/<int:version_id>/bb-review',
    methods=['POST'],
)
@admin_required
def request_bb_review(release_id, version_id):
    version = _load_version(release_id, version_id)
    if not version:
        return jsonify({'error': 'Version not found'}), 404

    # Don't stack duplicate work: if a review is already running for this version,
    # return it instead of kicking off a second Claude call.
    pending = (BBDrawingReview.query
               .filter(BBDrawingReview.drawing_version_id == version_id,
                       BBDrawingReview.status == 'pending')
               .order_by(BBDrawingReview.created_at.desc())
               .first())
    if pending:
        return jsonify(pending.to_dict()), 202

    user = get_current_user()
    review = BBDrawingReview(
        drawing_version_id=version_id,
        release_id=release_id,
        status='pending',
        requested_by_user_id=user.id if user else None,
    )
    db.session.add(review)
    db.session.commit()

    start_review(current_app._get_current_object(), review.id)
    logger.info("bb_review_requested", review_id=review.id, version_id=version_id,
                release_id=release_id)
    return jsonify(review.to_dict()), 202


@brain_bp.route(
    '/releases/<int:release_id>/drawing/versions/<int:version_id>/bb-review',
    methods=['GET'],
)
@admin_required
def get_bb_review(release_id, version_id):
    version = _load_version(release_id, version_id)
    if not version:
        return jsonify({'error': 'Version not found'}), 404

    review = (BBDrawingReview.query
              .filter(BBDrawingReview.drawing_version_id == version_id)
              .order_by(BBDrawingReview.created_at.desc())
              .first())
    if not review:
        return jsonify({'review': None}), 200
    payload = review.to_dict()
    # Carry any PM accept/deny (+ notes) so the panel renders its controls pre-filled.
    # Keyed by finding_index = the finding's slot in review.findings (raw order).
    payload['feedback'] = _feedback_map(review.id)
    return jsonify({'review': payload}), 200


def _feedback_map(review_id):
    """{finding_index: {decision, notes}} for a review's stored PM feedback."""
    return {
        fb.finding_index: {'decision': fb.decision, 'notes': fb.notes or ''}
        for fb in BBReviewFeedback.query.filter_by(review_id=review_id)
    }


def _job_release(release):
    if not release:
        return "unknown"
    return f"{str(release.job or '').strip()}-{str(release.release or '').strip()}".strip("-") or "unknown"


def _release_if_authorized(release_id):
    """(release, None) if the current user may see this release's BB report/feedback,
    else (None, (json, status)). Visible to an admin OR the release's resolved PM."""
    release = db.session.get(Releases, release_id)
    if not release:
        return None, (jsonify({'error': 'Release not found'}), 404)
    user = get_current_user()
    if not (user and (user.is_admin or user.id == release_owner_user(release))):
        return None, (jsonify({'error': 'Not authorized for this release'}), 403)
    return release, None


@brain_bp.route('/releases/<int:release_id>/bb-review/report', methods=['GET'])
@login_required
def get_bb_review_report(release_id):
    """PM-facing report: the latest complete BB review for the release, ranked by urgency.

    Read-only and visible to an admin OR the release's resolved PM (Releases.pm initials →
    User). Unlike the per-version endpoints this is release-scoped, so a PM sees one report
    for the job regardless of how many drawing versions were reviewed. Carries any existing
    PM feedback (keyed by finding_index) so the accept/deny controls render pre-filled.
    """
    release, err = _release_if_authorized(release_id)
    if err:
        return err

    review = (BBDrawingReview.query
              .filter(BBDrawingReview.release_id == release_id,
                      BBDrawingReview.status == 'complete')
              .order_by(BBDrawingReview.created_at.desc())
              .first())
    if not review:
        return jsonify({'report': None}), 200

    report = build_report(review.findings or [], _job_release(release))
    report.update({
        'review_id': review.id,
        'drawing_version_id': review.drawing_version_id,
        'model': review.model,
        'completed_at': review.to_dict().get('completed_at'),
        'feedback': _feedback_map(review.id),
    })
    return jsonify({'report': report}), 200


_VALID_DECISIONS = {'accepted', 'rejected'}


@brain_bp.route(
    '/releases/<int:release_id>/bb-review/<int:review_id>/feedback', methods=['POST'],
)
@login_required
def save_bb_review_feedback(release_id, review_id):
    """Upsert a PM's accept/deny (+ optional notes) for one finding of a BB review.

    Body: {finding_index:int, decision:'accepted'|'rejected', rule_id?:str, notes?:str,
           finding?:object}. One row per (review, finding_index); re-posting updates it.
    Same visibility gate as the report (admin OR the release's PM). We store the finding
    snapshot so the training data stays meaningful if the rule library later changes.
    """
    release, err = _release_if_authorized(release_id)
    if err:
        return err

    review = db.session.get(BBDrawingReview, review_id)
    if not review or review.release_id != release_id:
        return jsonify({'error': 'Review not found'}), 404

    data = request.get_json(silent=True) or {}
    decision = data.get('decision')
    finding_index = data.get('finding_index')
    if decision not in _VALID_DECISIONS:
        return jsonify({'error': "decision must be 'accepted' or 'rejected'"}), 400
    if not isinstance(finding_index, int):
        return jsonify({'error': 'finding_index (int) is required'}), 400

    user = get_current_user()
    fb = (BBReviewFeedback.query
          .filter_by(review_id=review_id, finding_index=finding_index)
          .first())
    if fb is None:
        fb = BBReviewFeedback(review_id=review_id, finding_index=finding_index)
        db.session.add(fb)

    fb.release_id = release_id
    fb.drawing_version_id = review.drawing_version_id
    fb.rule_id = (data.get('rule_id') or None)
    fb.decision = decision
    fb.notes = (data.get('notes') or None)
    fb.finding_snapshot = data.get('finding')
    fb.user_id = user.id if user else None
    db.session.commit()

    logger.info("bb_review_feedback_saved", review_id=review_id, release_id=release_id,
                finding_index=finding_index, decision=decision)
    return jsonify({'feedback': fb.to_dict()}), 200
