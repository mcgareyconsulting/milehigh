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
from app.models import ReleaseDrawingVersion, BBDrawingReview, Releases, db
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
    return jsonify({'review': review.to_dict()}), 200


def _job_release(release):
    if not release:
        return "unknown"
    return f"{str(release.job or '').strip()}-{str(release.release or '').strip()}".strip("-") or "unknown"


@brain_bp.route('/releases/<int:release_id>/bb-review/report', methods=['GET'])
@login_required
def get_bb_review_report(release_id):
    """PM-facing report: the latest complete BB review for the release, ranked by urgency.

    Read-only and visible to an admin OR the release's resolved PM (Releases.pm initials →
    User). Unlike the per-version endpoints this is release-scoped, so a PM sees one report
    for the job regardless of how many drawing versions were reviewed.
    """
    release = db.session.get(Releases, release_id)
    if not release:
        return jsonify({'error': 'Release not found'}), 404

    user = get_current_user()
    if not (user and (user.is_admin or user.id == release_owner_user(release))):
        return jsonify({'error': 'Not authorized for this release'}), 403

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
    })
    return jsonify({'report': report}), 200
