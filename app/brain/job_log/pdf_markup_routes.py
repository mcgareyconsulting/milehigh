"""REST endpoints for the PDF markup feature.

Endpoints (registered on brain_bp under the /brain prefix):
  POST   /releases/<release_id>/drawing                          — upload v1 or save next version
  GET    /releases/<release_id>/drawing/versions                 — list versions (newest first)
  GET    /releases/<release_id>/drawing/versions/<vid>/file      — stream the PDF bytes
  DELETE /releases/<release_id>/drawing/versions/<vid>           — admin-only soft delete
"""

from flask import jsonify, request, send_file

from app.brain import brain_bp
from app.auth.utils import (
    admin_required,
    drafter_or_admin_required,
    get_current_user,
)
from app.models import (
    Releases,
    ReleaseDrawingVersion,
    User,
    db,
)
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

from app.brain.job_log.features.pdf_markup.command import (
    SaveDrawingVersionCommand,
    UploadInitialDrawingCommand,
)
from app.brain.job_log.features.pdf_markup.payloads import is_pdf_bytes
from app.brain.job_log.features.pdf_markup.storage import absolute_path

logger = get_logger(__name__)


def _resolve_user_display_name(user: User) -> str:
    if not user:
        return None
    first = (user.first_name or '').strip()
    last = (user.last_name or '').strip()
    return (f"{first} {last}".strip()) or user.username


@brain_bp.route('/releases/<int:release_id>/drawing', methods=['POST'])
@drafter_or_admin_required
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
@drafter_or_admin_required
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
@drafter_or_admin_required
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
        source=f"Brain:{user.username}" if user else "Brain",
        payload={
            'version': version.version_number,
            'version_id': version.id,
            'soft': True,
        },
    )
    db.session.commit()

    return jsonify({'status': 'deleted', 'version_id': version_id})
