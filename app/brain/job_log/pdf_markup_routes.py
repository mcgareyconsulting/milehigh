"""REST endpoints for the PDF markup feature.

Endpoints (registered on brain_bp under the /brain prefix):
  POST   /releases/<release_id>/drawing                          — upload v1 or save next version
  GET    /releases/<release_id>/drawing/versions                 — list versions (newest first)
  GET    /releases/<release_id>/procore-documents                — Final PDF Pack candidates
  POST   /releases/<release_id>/procore-documents/<aid>/pull     — pull one into a version
  GET    /releases/<release_id>/drawing/versions/<vid>/file      — stream the PDF bytes
  DELETE /releases/<release_id>/drawing/versions/<vid>           — admin-only soft delete

Any logged-in user may upload, view, and mark up drawings (matching photos);
each save is attributed to its author via `uploaded_by_user_id`. Deleting a
version remains admin-only to guard against accidental loss of markup history.
"""

from flask import jsonify, request, send_file

from app.brain import brain_bp
from app.auth.utils import (
    admin_required,
    drafter_or_admin_required,
    login_required,
    get_current_user,
)
from app.models import (
    Releases,
    ReleaseDrawingVersion,
    DrawingVersionComment,
    Notification,
    User,
    db,
)
from app.brain.mentions import parse_mentions, resolve_mentioned_users
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

from app.brain.job_log.features.pdf_markup.command import (
    SaveDrawingVersionCommand,
    UploadInitialDrawingCommand,
)
from app.brain.job_log.features.pdf_markup.payloads import is_pdf_bytes
from app.brain.job_log.features.pdf_markup.procore_pull import (
    ProcorePullError,
    SubmittalNotResolved,
    debug_payloads,
    list_documents,
    probe_candidate,
    pull_document,
)
from app.brain.job_log.features.pdf_markup.storage import absolute_path

logger = get_logger(__name__)


def _resolve_user_display_name(user: User) -> str:
    if not user:
        return None
    first = (user.first_name or '').strip()
    last = (user.last_name or '').strip()
    return (f"{first} {last}".strip()) or user.username


@brain_bp.route('/releases/<int:release_id>/drawing', methods=['POST'])
@login_required
def upload_release_drawing(release_id):
    """Upload a PDF for a release.

    First upload (no existing versions) creates v1.
    Subsequent uploads require `source_version_id` and create v(N+1).
    """
    release = db.session.get(Releases, release_id)
    if not release:
        return jsonify({'error': 'Release not found'}), 404

    file = request.files.get('file')
    if not file:
        return jsonify({'error': "Missing 'file' part"}), 400

    filename = file.filename or ''
    mimetype = (file.mimetype or '').lower()
    if mimetype != 'application/pdf' and not filename.lower().endswith('.pdf'):
        return jsonify({'error': 'File must be a PDF'}), 400

    file_bytes = file.read()
    if not is_pdf_bytes(file_bytes):
        return jsonify({'error': 'Invalid PDF (magic bytes mismatch)'}), 400

    note = (request.form.get('note') or '').strip() or None
    source_version_id_raw = request.form.get('source_version_id')
    user = get_current_user()

    has_existing = db.session.query(ReleaseDrawingVersion.id).filter(
        ReleaseDrawingVersion.release_id == release_id,
    ).first() is not None

    try:
        if not has_existing:
            command = UploadInitialDrawingCommand(
                release_id=release_id,
                file_bytes=file_bytes,
                filename=filename or None,
                mime_type='application/pdf',
                uploaded_by_user_id=user.id,
                note=note,
            )
        else:
            if not source_version_id_raw:
                return jsonify({
                    'error': "source_version_id is required when a drawing already exists"
                }), 400
            try:
                source_version_id = int(source_version_id_raw)
            except (TypeError, ValueError):
                return jsonify({'error': 'source_version_id must be an integer'}), 400

            command = SaveDrawingVersionCommand(
                release_id=release_id,
                file_bytes=file_bytes,
                uploaded_by_user_id=user.id,
                source_version_id=source_version_id,
                note=note,
            )

        version = command.execute()
    except ValueError as exc:
        message = str(exc)
        if 'not found' in message.lower():
            return jsonify({'error': message}), 404
        return jsonify({'error': message}), 409

    return jsonify(version.to_dict()), 201


@brain_bp.route('/releases/<int:release_id>/drawing/versions', methods=['GET'])
@login_required
def list_release_drawing_versions(release_id):
    release = db.session.get(Releases, release_id)
    if not release:
        return jsonify({'error': 'Release not found'}), 404

    versions = (ReleaseDrawingVersion.query
                .filter(ReleaseDrawingVersion.release_id == release_id,
                        ReleaseDrawingVersion.is_deleted.is_(False))
                .order_by(ReleaseDrawingVersion.version_number.desc())
                .all())

    return jsonify({
        'release_id': release_id,
        'versions': [v.to_dict() for v in versions],
    })


@brain_bp.route(
    '/releases/<int:release_id>/drawing/versions/<int:version_id>/file',
    methods=['GET'],
)
@login_required
def get_release_drawing_file(release_id, version_id):
    version = db.session.get(ReleaseDrawingVersion, version_id)
    if not version or version.release_id != release_id or version.is_deleted:
        return jsonify({'error': 'Version not found'}), 404

    path = absolute_path(version.storage_key)
    if not path.exists():
        logger.error(
            "Drawing file missing on disk",
            extra={'release_id': release_id, 'version_id': version_id, 'storage_key': version.storage_key},
        )
        return jsonify({'error': 'File missing on disk'}), 410

    return send_file(
        str(path),
        mimetype=version.mime_type or 'application/pdf',
        as_attachment=False,
        conditional=True,
    )


@brain_bp.route(
    '/releases/<int:release_id>/drawing/versions/<int:version_id>/comments',
    methods=['GET'],
)
@login_required
def list_drawing_version_comments(release_id, version_id):
    version = db.session.get(ReleaseDrawingVersion, version_id)
    if not version or version.release_id != release_id or version.is_deleted:
        return jsonify({'error': 'Version not found'}), 404

    comments = (version.comments
                .order_by(DrawingVersionComment.created_at.asc())
                .all())
    return jsonify({
        'version_id': version_id,
        'comments': [c.to_dict() for c in comments],
    })


@brain_bp.route(
    '/releases/<int:release_id>/drawing/versions/<int:version_id>/comments',
    methods=['POST'],
)
@login_required
def add_drawing_version_comment(release_id, version_id):
    version = db.session.get(ReleaseDrawingVersion, version_id)
    if not version or version.release_id != release_id or version.is_deleted:
        return jsonify({'error': 'Version not found'}), 404

    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({'error': 'Comment body is required'}), 400

    user = get_current_user()
    author_name = _resolve_user_display_name(user)

    comment = DrawingVersionComment(
        drawing_version_id=version.id,
        release_id=release_id,
        body=body,
        author_id=user.id,
        author_name=author_name,
    )
    db.session.add(comment)
    db.session.commit()

    # Parse @FirstName mentions and create notifications (mirrors board comments).
    mentioned_users = resolve_mentioned_users(parse_mentions(body))
    if mentioned_users:
        for mu in mentioned_users:
            notif = Notification(
                user_id=mu.id,
                type='mention',
                message=f'{author_name} mentioned you on drawing v{version.version_number}',
                drawing_version_comment_id=comment.id,
            )
            db.session.add(notif)
        db.session.commit()

    return jsonify(comment.to_dict()), 201


@brain_bp.route(
    '/releases/<int:release_id>/drawing/versions/<int:version_id>',
    methods=['DELETE'],
)
@admin_required
def delete_release_drawing_version(release_id, version_id):
    version = db.session.get(ReleaseDrawingVersion, version_id)
    if not version or version.release_id != release_id:
        return jsonify({'error': 'Version not found'}), 404
    if version.is_deleted:
        return jsonify({'status': 'already_deleted'}), 200

    release = db.session.get(Releases, release_id)
    user = get_current_user()

    version.is_deleted = True
    JobEventService.create_and_close(
        job=release.job,
        release=release.release,
        action='delete_drawing_version',
        source="Brain",
        internal_user_id=user.id if user else None,
        payload={
            'version': version.version_number,
            'version_id': version.id,
            'soft': True,
        },
    )
    db.session.commit()

    return jsonify({'status': 'deleted', 'version_id': version_id})


# ── Final PDF Pack puller ────────────────────────────────────────────────────
# The nightly FC worker only links a release to its Procore submittal; these two
# endpoints fetch the pack itself. Manual by design — they cover the gaps the
# worker leaves (no link yet, wrong submittal, a pack revised after the pull)
# and give the drawing pipeline something to test against on demand.

@brain_bp.route('/releases/<int:release_id>/procore-documents', methods=['GET'])
@drafter_or_admin_required
def list_release_procore_documents(release_id):
    """Which Procore submittal this release resolves to, and what can be pulled from it.

    ?submittal_id=<id> overrides the resolution for a release the worker has not linked.
    ?debug=1 adds Procore's raw attachment/response objects plus every JSON path that looks
    like a final-PDF label — for reading in the browser console, never for decisions.
    ?probe=<attachment_id> additionally takes that attachment's ids back to Procore and
    reports what each candidate endpoint returns (the approver record included).
    """
    release = db.session.get(Releases, release_id)
    if not release:
        return jsonify({'error': 'Release not found'}), 404

    submittal_id = request.args.get('submittal_id')
    try:
        payload = list_documents(release, submittal_id)
        if request.args.get('debug') in ('1', 'true', 'yes'):
            payload['debug'] = debug_payloads(release, submittal_id)
        probe_id = request.args.get('probe')
        if probe_id:
            payload.setdefault('debug', {})['probe'] = probe_candidate(
                release, probe_id, submittal_id,
            )
    except SubmittalNotResolved as exc:
        return jsonify({'error': str(exc), 'resolvable': False}), 409
    except Exception as exc:
        logger.error("release_procore_documents_failed", release_id=release_id,
                     error=str(exc), error_type=type(exc).__name__, exc_info=True)
        return jsonify({'error': 'Could not reach Procore for this release'}), 502

    return jsonify(payload), 200


@brain_bp.route(
    '/releases/<int:release_id>/procore-documents/<attachment_id>/pull', methods=['POST'],
)
@drafter_or_admin_required
def pull_release_procore_document(release_id, attachment_id):
    """Download one Procore attachment and attach it as this release's next version."""
    release = db.session.get(Releases, release_id)
    if not release:
        return jsonify({'error': 'Release not found'}), 404

    user = get_current_user()
    submittal_id = (request.get_json(silent=True) or {}).get('submittal_id') \
        or request.args.get('submittal_id')

    try:
        version, ref = pull_document(
            release, attachment_id,
            uploaded_by_user_id=user.id if user else None,
            submittal_id_override=submittal_id,
        )
    except SubmittalNotResolved as exc:
        return jsonify({'error': str(exc), 'resolvable': False}), 409
    except ProcorePullError as exc:
        return jsonify({'error': str(exc)}), 502
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 409
    except Exception as exc:
        logger.error("release_procore_pull_failed", release_id=release_id,
                     attachment_id=attachment_id, error=str(exc),
                     error_type=type(exc).__name__, exc_info=True)
        return jsonify({'error': 'Pull failed (see logs)'}), 502

    return jsonify({
        'ok': True,
        'version': version.to_dict(),
        'pulled': {
            'attachment_id': ref.get('attachment_id'),
            'name': ref.get('name'),
            'source': ref.get('source'),
            'response_name': ref.get('response_name'),
            'approver_name': ref.get('approver_name'),
            # Procore renders through its markup endpoint, so an approver's markups are
            # burned into these bytes; this says whether there were any to burn.
            'carried_markup': ref.get('carried_markup', False),
            # 'raw_attachment' when the markup renderer refused every id shape and we fell
            # back to the file itself — a clean copy, markups not burned in.
            'render_fallback': ref.get('render_fallback'),
            'markup_paths': ref.get('markup_paths') or [],
            'size_bytes': version.file_size_bytes,
        },
    }), 201
