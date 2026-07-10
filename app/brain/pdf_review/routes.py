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
    ReleaseDrawingVersion, BBDrawingReview, BBReviewFeedback, Releases, Submittals, db,
)
from app.logging_config import get_logger

from app.brain.pdf_review import service
from app.brain.pdf_review.worker import start_review
from app.brain.pdf_review.report import build_report
from app.brain.meetings.owner_match import release_owner_user
from app.procore.attachments import (
    find_submittal_drawing_refs, download_submittal_drawing, download_markup_pdf,
)
from app.brain.job_log.features.pdf_markup.command import UploadInitialDrawingCommand

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


def _truthy(v):
    return str(v).lower() in ("1", "true", "yes", "on")


@brain_bp.route('/procore-submittals/<submittal_id>/bb-review', methods=['POST'])
@admin_required
def bb_review_procore_submittal(submittal_id):
    """Pull a submittal's drawing PDF from Procore and run a BB review on it (Track B v1).

    Test/manual endpoint for the "continuous compliance via Procore ingestion" work — keyed
    to the submittal (no release link required). `submittal_id` is the **Procore** submittal
    id (what the DWL submittal popup has), matched against `Submittals.submittal_id`.

    Query params:
      pull_only=true                 — download the PDF and return metadata only (fast; skips
                                       the multi-minute review). Use this first to confirm the
                                       Procore pull works before waiting on a review.
      model=sonnet|opus              — reviewing model: 'sonnet' for a lighter/faster pass,
                                       'opus' for the deep review (omit for the default).
      attach_to_release=<id>         — persist the pulled drawing as a ReleaseDrawingVersion
                                       on that release, so it shows in the release's
                                       attachments and is reviewable by the per-version flow
                                       (v1 only; errors if the release already has a drawing).
      item_id / item_type / attachment_id — target a specific attachment (bypasses auto-select),
                                       for probing which attachment kind find_or_create serves.

    NOTE: without pull_only the review runs INLINE and blocks for several minutes (the known
    Phase-0 latency). Fine for a manual sandbox test; the production path will background it.
    """
    submittal = (Submittals.query
                 .filter_by(submittal_id=str(submittal_id))
                 .first())
    if not submittal:
        return jsonify({'error': 'Submittal not found'}), 404

    project_id = submittal.procore_project_id
    procore_submittal_id = submittal.submittal_id
    if not project_id or not procore_submittal_id:
        return jsonify({'error': 'Submittal has no Procore project/submittal id'}), 400

    pull_only = _truthy(request.args.get('pull_only'))

    # Optional explicit attachment targeting (helps probe which attachment kind works).
    override = None
    if all(request.args.get(k) for k in ('item_id', 'item_type', 'attachment_id')):
        override = {
            'source': 'override',
            'name': None,
            'item_id': int(request.args['item_id']),
            'item_type': request.args['item_type'],
            'attachment_id': int(request.args['attachment_id']),
            'project_id': int(project_id),
            'company_id': None,
        }

    refs = find_submittal_drawing_refs(project_id, procore_submittal_id)
    if not refs and not override:
        return jsonify({'error': 'No drawing attachment found on this submittal',
                        'candidates': []}), 404

    pdf_bytes, filename, ref = download_submittal_drawing(
        project_id, procore_submittal_id, ref=override or refs[0],
    )
    if not pdf_bytes:
        return jsonify({
            'error': 'Could not download the drawing PDF from Procore',
            'tried': ref,
            'candidates': refs,
        }), 502

    logger.info("bb_review_procore_pulled", submittal_id=procore_submittal_id,
                project_id=project_id, filename=filename, size=len(pdf_bytes),
                source=(ref or {}).get('source'))

    # Optionally persist the pulled drawing as a release's drawing version, so it shows in
    # the release's attachments and becomes reviewable by the existing per-version BB flow.
    # v1 only for now (release has no drawing yet) — the common "pull the FC into the JL" case.
    attached = None
    attach_release_id = request.args.get('attach_to_release', type=int)
    if attach_release_id:
        user = get_current_user()
        try:
            version = UploadInitialDrawingCommand(
                release_id=attach_release_id,
                file_bytes=pdf_bytes,
                filename=filename or f"procore-{procore_submittal_id}.pdf",
                mime_type='application/pdf',
                uploaded_by_user_id=user.id if user else None,
                note=f"Pulled from Procore submittal {procore_submittal_id}",
            ).execute()
            attached = {'release_id': attach_release_id, 'version_id': version.id,
                        'version_number': version.version_number}
            logger.info("bb_review_procore_attached", submittal_id=procore_submittal_id,
                        release_id=attach_release_id, version_id=version.id)
        except ValueError as e:
            attached = {'error': str(e)}

    if pull_only:
        return jsonify({
            'ok': True,
            'pulled': {'filename': filename, 'size_bytes': len(pdf_bytes),
                       'ref': ref},
            'attached': attached,
            'candidates': refs,
        }), 200

    job_release = f"{submittal.project_number or ''}-{submittal.rel or ''}".strip('-') \
        or (submittal.title or 'unknown')
    # model: 'sonnet' (lighter/faster) | 'opus' (deep) | raw id | omit for the default.
    result = service.review(pdf_bytes, job_release, model=request.args.get('model'))
    if result is None:
        return jsonify({'error': 'Review call failed (see logs)',
                        'pulled': {'filename': filename, 'size_bytes': len(pdf_bytes)}}), 502

    return jsonify({
        'ok': True,
        'job_release': job_release,
        'pulled': {'filename': filename, 'size_bytes': len(pdf_bytes),
                   'source': (ref or {}).get('source')},
        'attached': attached,
        'findings': result['findings'],
        'model': result.get('model'),
        'input_tokens': result.get('input_tokens'),
        'output_tokens': result.get('output_tokens'),
    }), 200
