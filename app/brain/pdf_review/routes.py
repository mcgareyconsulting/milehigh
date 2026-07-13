"""REST endpoints for Banana Boy PDF review (admin-only).

Registered on brain_bp under /brain:
  POST /releases/<release_id>/drawing/versions/<vid>/bb-review  — enqueue a review (202)
  GET  /releases/<release_id>/drawing/versions/<vid>/bb-review  — latest review status + findings

Admin-only, matching the "admin-only Banana Boy" decision. The POST returns immediately
(202) with a `pending` row; the review runs on a background thread (worker.py). The
frontend panel polls the GET until status is `complete` or `error`.
"""
import io
from datetime import datetime

from flask import jsonify, current_app, send_file

from app.brain import brain_bp
from app.auth.utils import admin_required, login_required, get_current_user
from flask import request

from app.models import (
    ReleaseDrawingVersion, BBDrawingReview, BBReviewFeedback, Releases, Submittals,
    is_gc_approval_type, db,
)
from app.logging_config import get_logger

from app.brain.pdf_review import service
from app.brain.pdf_review import cache as procore_pdf_cache
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
                                       Procore pull works before waiting on a review. Every
                                       pull is cached server-side (see review_only).
      review_only=true               — review the already-downloaded (cached) drawing without
                                       re-pulling from Procore; 409 if nothing is cached yet.
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

    review_only = _truthy(request.args.get('review_only'))
    pull_only = _truthy(request.args.get('pull_only')) and not review_only

    refs, ref = [], None
    if review_only:
        # Review the already-downloaded drawing without re-pulling from Procore. The cache
        # is per-attachment now; this legacy endpoint doesn't target one, so read the first
        # cached attachment for the submittal (filesystem-only, no Procore call).
        cached = procore_pdf_cache.list_cached(procore_submittal_id)
        pdf_bytes = procore_pdf_cache.read(procore_submittal_id, cached[0]) if cached else None
        if not pdf_bytes:
            return jsonify({'error': 'No downloaded drawing for this submittal — pull it first'}), 409
        filename = f"procore-{procore_submittal_id}.pdf"
    else:
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

        # Cache the pulled bytes so a later review (or re-review on another model) can run
        # without re-pulling — that's the review_only path above. Keyed per-attachment.
        procore_pdf_cache.save(procore_submittal_id, (ref or {}).get('attachment_id'), pdf_bytes)
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


@brain_bp.route('/procore-submittals/<submittal_id>/bb-review', methods=['GET'])
@admin_required
def bb_review_procore_submittal_status(submittal_id):
    """Whether a drawing for this submittal has already been pulled and cached, so the UI
    can offer a 'Review downloaded' button that skips the Procore pull."""
    submittal = (Submittals.query
                 .filter_by(submittal_id=str(submittal_id))
                 .first())
    if not submittal:
        return jsonify({'error': 'Submittal not found'}), 404
    # Per-attachment cache now; report the first cached attachment for this submittal.
    cached = procore_pdf_cache.list_cached(submittal.submittal_id)
    meta = procore_pdf_cache.meta(submittal.submittal_id, cached[0]) if cached else None
    return jsonify({'cached': meta is not None,
                    'size_bytes': (meta or {}).get('size_bytes')}), 200


# ---------------------------------------------------------------------------
# BB review workspace — per-submittal-document endpoints (Track B).
#
# These key a review to a Procore submittal drawing (submittal_id + prostore
# attachment_id) with no job-log release involved. One submittal can carry several
# reviewable drawings, so everything is addressed by (submittal_id, attachment_id).
# ---------------------------------------------------------------------------

# Procore web-app company for the deep link (mirrors the frontend submittal modals).
_PROCORE_COMPANY_ID = "18521"


def _submittal_phase(type_value):
    """Bucket a submittal's Procore type into the drafting phase the workspace shows."""
    from app.procore.procore import DRR_TYPE
    t = (type_value or "").strip()
    if t == DRR_TYPE:
        return "DRR"
    if t == "For Construction":
        return "FC"
    if is_gc_approval_type(type_value):
        return "GC"
    return "other"


def _submittal_procore_url(submittal):
    pid = submittal.procore_project_id
    sid = submittal.submittal_id
    if not pid or not sid:
        return None
    return (f"https://app.procore.com/webclients/host/companies/{_PROCORE_COMPANY_ID}"
            f"/projects/{pid}/tools/submittals/{sid}")


def _submittal_job_release(submittal):
    """The job-release label used for BB reports: '<project_number>-<rel>'."""
    return (f"{submittal.project_number or ''}-{submittal.rel or ''}".strip('-')
            or (submittal.title or 'unknown'))


def _load_submittal_or_404(submittal_id):
    """(submittal, None) or (None, (json, status)). Also validates it has Procore ids."""
    submittal = Submittals.query.filter_by(submittal_id=str(submittal_id)).first()
    if not submittal:
        return None, (jsonify({'error': 'Submittal not found'}), 404)
    if not submittal.procore_project_id or not submittal.submittal_id:
        return None, (jsonify({'error': 'Submittal has no Procore project/submittal id'}), 400)
    return submittal, None


def _coerce_attachment_id(attachment_id):
    """The attachment_id arrives as a URL string; store/query it as the int it is."""
    try:
        return int(attachment_id)
    except (TypeError, ValueError):
        return attachment_id


def _find_ref(project_id, procore_submittal_id, attachment_id):
    """(ref, refs) for a target attachment_id, or (None, refs) if it's not on the submittal."""
    refs = find_submittal_drawing_refs(project_id, procore_submittal_id)
    ref = next((r for r in refs if str(r.get('attachment_id')) == str(attachment_id)), None)
    return ref, refs


@brain_bp.route('/procore-submittals/<submittal_id>/documents', methods=['GET'])
@admin_required
def list_submittal_documents(submittal_id):
    """The BB review workspace for one submittal: its header + every reviewable drawing.

    Merges three sources: the Procore drawing refs (list), the server-side pull cache
    (downloaded/size per attachment), and the latest persisted BB review per attachment
    (status + tally). One grouped review query — no per-document DB round trips.
    """
    submittal, err = _load_submittal_or_404(submittal_id)
    if err:
        return err
    project_id = submittal.procore_project_id
    procore_submittal_id = submittal.submittal_id

    refs = find_submittal_drawing_refs(project_id, procore_submittal_id)

    # Latest review per attachment_id for this submittal, in one query.
    reviews = (BBDrawingReview.query
               .filter(BBDrawingReview.submittal_id == str(procore_submittal_id))
               .order_by(BBDrawingReview.created_at.desc())
               .all())
    latest_by_attachment = {}
    for r in reviews:
        if r.attachment_id is not None and r.attachment_id not in latest_by_attachment:
            latest_by_attachment[r.attachment_id] = r

    job_release = _submittal_job_release(submittal)
    documents = []
    for ref in refs:
        attachment_id = ref.get('attachment_id')
        m = (procore_pdf_cache.meta(procore_submittal_id, attachment_id)
             if attachment_id is not None else None)
        review = latest_by_attachment.get(attachment_id)
        review_payload = None
        if review is not None:
            report = build_report(review.findings or [], job_release)
            review_payload = {
                'review_id': review.id,
                'status': review.status,
                'model': review.model,
                'completed_at': review.to_dict().get('completed_at'),
                'tally': report['tally'],
                'hold_recommended': report['hold_recommended'],
            }
        documents.append({
            'attachment_id': attachment_id,
            'item_id': ref.get('item_id'),
            'item_type': ref.get('item_type'),
            'name': ref.get('name'),
            'source': ref.get('source'),
            'downloaded': m is not None,
            'size_bytes': (m or {}).get('size_bytes'),
            'review': review_payload,
        })

    return jsonify({
        'submittal': {
            'submittal_id': procore_submittal_id,
            'title': submittal.title,
            'type': submittal.type,
            'phase': _submittal_phase(submittal.type),
            'status': submittal.status,
            'ball_in_court': submittal.ball_in_court,
            'rel': submittal.rel,
            'project_id': project_id,
            'procore_url': _submittal_procore_url(submittal),
        },
        'documents': documents,
    }), 200


@brain_bp.route(
    '/procore-submittals/<submittal_id>/documents/<attachment_id>/pull', methods=['POST'],
)
@admin_required
def pull_submittal_document(submittal_id, attachment_id):
    """Download one submittal drawing from Procore and cache it (no review)."""
    submittal, err = _load_submittal_or_404(submittal_id)
    if err:
        return err
    project_id = submittal.procore_project_id
    procore_submittal_id = submittal.submittal_id

    ref, refs = _find_ref(project_id, procore_submittal_id, attachment_id)
    if not ref:
        return jsonify({'error': 'Attachment not found on this submittal',
                        'candidates': refs}), 404

    pdf_bytes = download_markup_pdf(
        ref['project_id'], ref['item_id'], ref['item_type'], ref['attachment_id'],
        company_id=ref.get('company_id'),
    )
    if not pdf_bytes:
        return jsonify({'error': 'Could not download the drawing PDF from Procore',
                        'tried': ref, 'candidates': refs}), 502

    procore_pdf_cache.save(procore_submittal_id, ref['attachment_id'], pdf_bytes)
    logger.info("bb_submittal_document_pulled", submittal_id=procore_submittal_id,
                attachment_id=ref['attachment_id'], project_id=project_id,
                size=len(pdf_bytes), source=ref.get('source'))
    return jsonify({'ok': True, 'downloaded': True, 'size_bytes': len(pdf_bytes),
                    'name': ref.get('name'), 'source': ref.get('source')}), 200


@brain_bp.route(
    '/procore-submittals/<submittal_id>/documents/<attachment_id>/bb-review',
    methods=['POST'],
)
@admin_required
def bb_review_submittal_document(submittal_id, attachment_id):
    """Run a BB review on one submittal drawing and persist the result.

    review_only=true reviews the already-cached drawing (409 if nothing cached); otherwise
    the drawing is pulled-if-not-cached first. model=sonnet|opus selects the reviewing model.
    Runs inline (v1) and persists a submittal-keyed BBDrawingReview row.
    """
    submittal, err = _load_submittal_or_404(submittal_id)
    if err:
        return err
    project_id = submittal.procore_project_id
    procore_submittal_id = submittal.submittal_id
    attachment_id_int = _coerce_attachment_id(attachment_id)
    review_only = _truthy(request.args.get('review_only'))

    pdf_bytes = procore_pdf_cache.read(procore_submittal_id, attachment_id_int)
    if not pdf_bytes:
        if review_only:
            return jsonify({
                'error': 'No downloaded drawing for this attachment — pull it first'}), 409
        ref, refs = _find_ref(project_id, procore_submittal_id, attachment_id)
        if not ref:
            return jsonify({'error': 'Attachment not found on this submittal',
                            'candidates': refs}), 404
        pdf_bytes = download_markup_pdf(
            ref['project_id'], ref['item_id'], ref['item_type'], ref['attachment_id'],
            company_id=ref.get('company_id'),
        )
        if not pdf_bytes:
            return jsonify({'error': 'Could not download the drawing PDF from Procore',
                            'tried': ref, 'candidates': refs}), 502
        attachment_id_int = ref['attachment_id']
        procore_pdf_cache.save(procore_submittal_id, attachment_id_int, pdf_bytes)

    job_release = _submittal_job_release(submittal)
    user = get_current_user()
    result = service.review(pdf_bytes, job_release, model=request.args.get('model'))

    if result is None:
        review = BBDrawingReview(
            submittal_id=str(procore_submittal_id), attachment_id=attachment_id_int,
            drawing_version_id=None, release_id=None, status='error',
            error='Review call failed (see logs)',
            requested_by_user_id=user.id if user else None,
            completed_at=datetime.utcnow(),
        )
        db.session.add(review)
        db.session.commit()
        logger.info("bb_submittal_document_review_failed", submittal_id=procore_submittal_id,
                    attachment_id=attachment_id_int, review_id=review.id)
        return jsonify({'ok': False, 'error': 'Review call failed (see logs)',
                        'review_id': review.id}), 502

    review = BBDrawingReview(
        submittal_id=str(procore_submittal_id), attachment_id=attachment_id_int,
        drawing_version_id=None, release_id=None, status='complete',
        findings=result['findings'], model=result.get('model'),
        input_tokens=result.get('input_tokens'), output_tokens=result.get('output_tokens'),
        requested_by_user_id=user.id if user else None,
        completed_at=datetime.utcnow(),
    )
    db.session.add(review)
    db.session.commit()

    report = build_report(result['findings'], job_release)
    logger.info("bb_submittal_document_reviewed", submittal_id=procore_submittal_id,
                attachment_id=attachment_id_int, review_id=review.id,
                findings=len(result['findings']), model=result.get('model'))
    return jsonify({
        'ok': True,
        'review_id': review.id,
        'findings': result['findings'],
        'tally': report['tally'],
        'hold_recommended': report['hold_recommended'],
        'model': result.get('model'),
        'input_tokens': result.get('input_tokens'),
        'output_tokens': result.get('output_tokens'),
    }), 200


@brain_bp.route(
    '/procore-submittals/<submittal_id>/documents/<attachment_id>/bb-review',
    methods=['GET'],
)
@admin_required
def get_bb_review_submittal_document(submittal_id, attachment_id):
    """Latest persisted BB review for one submittal drawing, with PM feedback."""
    submittal, err = _load_submittal_or_404(submittal_id)
    if err:
        return err
    attachment_id_int = _coerce_attachment_id(attachment_id)

    review = (BBDrawingReview.query
              .filter(BBDrawingReview.submittal_id == str(submittal.submittal_id),
                      BBDrawingReview.attachment_id == attachment_id_int)
              .order_by(BBDrawingReview.created_at.desc())
              .first())
    if not review:
        return jsonify({'review': None}), 200

    report = build_report(review.findings or [], _submittal_job_release(submittal))
    payload = {
        'review_id': review.id,
        'status': review.status,
        'model': review.model,
        'completed_at': review.to_dict().get('completed_at'),
        'findings': review.findings if review.findings is not None else [],
        'tally': report['tally'],
        'hold_recommended': report['hold_recommended'],
        'feedback': _feedback_map(review.id),
    }
    return jsonify({'review': payload}), 200


@brain_bp.route(
    '/procore-submittals/<submittal_id>/documents/<attachment_id>/bb-review/'
    '<int:review_id>/feedback',
    methods=['POST'],
)
@admin_required
def save_submittal_document_feedback(submittal_id, attachment_id, review_id):
    """Upsert a PM accept/deny (+ notes) on one finding of a submittal-keyed review.

    Body: {finding_index:int, decision:'accepted'|'rejected', rule_id?, notes?, finding?}.
    One row per (review, finding_index); re-posting updates it. Release/version stay null.
    """
    submittal, err = _load_submittal_or_404(submittal_id)
    if err:
        return err

    review = db.session.get(BBDrawingReview, review_id)
    if not review or review.submittal_id != str(submittal.submittal_id):
        return jsonify({'error': 'Review not found'}), 404

    data = request.get_json(silent=True) or {}
    decision = data.get('decision')
    finding_index = data.get('finding_index')
    if decision not in _VALID_DECISIONS:
        return jsonify({'error': "decision must be 'accepted' or 'rejected'"}), 400
    if not isinstance(finding_index, int):
        return jsonify({'error': 'finding_index (int) is required'}), 400

    attachment_id_int = _coerce_attachment_id(attachment_id)
    user = get_current_user()
    fb = (BBReviewFeedback.query
          .filter_by(review_id=review_id, finding_index=finding_index)
          .first())
    if fb is None:
        fb = BBReviewFeedback(review_id=review_id, finding_index=finding_index)
        db.session.add(fb)

    fb.submittal_id = str(submittal.submittal_id)
    fb.attachment_id = attachment_id_int
    fb.release_id = None
    fb.drawing_version_id = None
    fb.rule_id = (data.get('rule_id') or None)
    fb.decision = decision
    fb.notes = (data.get('notes') or None)
    fb.finding_snapshot = data.get('finding')
    fb.user_id = user.id if user else None
    db.session.commit()

    logger.info("bb_submittal_feedback_saved", review_id=review_id,
                submittal_id=submittal.submittal_id, attachment_id=attachment_id_int,
                finding_index=finding_index, decision=decision)
    return jsonify({'feedback': fb.to_dict()}), 200


@brain_bp.route(
    '/procore-submittals/<submittal_id>/documents/<attachment_id>/file',
    methods=['GET'],
)
@admin_required
def get_submittal_document_file(submittal_id, attachment_id):
    """Stream the cached PDF for a downloaded submittal drawing (read-only viewer).

    Serves the bytes already pulled to the per-attachment cache; 404 when the drawing
    hasn't been downloaded yet (the UI only offers View on a downloaded row).
    """
    aid = _coerce_attachment_id(attachment_id)
    data = procore_pdf_cache.read(str(submittal_id), aid)
    if data is None:
        return jsonify({'error': 'Drawing not downloaded'}), 404
    return send_file(
        io.BytesIO(data),
        mimetype='application/pdf',
        download_name=f"{submittal_id}-{aid}.pdf",
    )
