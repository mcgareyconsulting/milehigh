"""REST endpoints for the Release Issue Register (roadmap T11).

Endpoints (registered on brain_bp under the /brain prefix), all admin-only in v1:
  GET    /release-issues/options                                   — departments/categories/priorities/statuses
  GET    /releases/<release_id>/issues                             — list + open count / open estimated cost
  POST   /releases/<release_id>/issues                             — create an issue
  GET    /release-issues/<issue_id>                                — issue + comments + attachments + history
  PATCH  /release-issues/<issue_id>                                — partial edit; tracked fields log history
  POST   /release-issues/<issue_id>/comments                       — comment; @FirstName mentions notify
  POST   /release-issues/<issue_id>/attachments                    — upload a photo/PDF (optional comment_id)
  GET    /release-issues/<issue_id>/attachments/<attachment_id>/file — stream the file bytes
  DELETE /release-issues/<issue_id>/attachments/<attachment_id>    — soft delete
"""
from flask import jsonify, request, send_file

from app.auth.utils import admin_required, get_current_user
from app.brain import brain_bp
from app.brain.release_issues import constants as C
from app.brain.release_issues import service
from app.brain.release_issues.service import IssueValidationError
from app.brain.release_issues.storage import absolute_path, sniff_mime
from app.logging_config import get_logger
from app.models import ReleaseIssue, ReleaseIssueAttachment, Releases, db

logger = get_logger(__name__)


def _issue_or_404(issue_id):
    return db.session.get(ReleaseIssue, issue_id)


@brain_bp.route('/release-issues/options', methods=['GET'])
@admin_required
def release_issue_options():
    return jsonify(C.as_options()), 200


@brain_bp.route('/releases/<int:release_id>/issues', methods=['GET'])
@admin_required
def list_release_issues(release_id):
    release = db.session.get(Releases, release_id)
    if not release:
        return jsonify({'error': 'Release not found'}), 404

    issues = service.list_for_release(release_id)
    return jsonify({
        'release_id': release_id,
        'issues': [i.to_dict() for i in issues],
        'summary': service.summarize(issues),
    }), 200


@brain_bp.route('/releases/<int:release_id>/issues', methods=['POST'])
@admin_required
def create_release_issue(release_id):
    release = db.session.get(Releases, release_id)
    if not release:
        return jsonify({'error': 'Release not found'}), 404

    data = request.get_json(silent=True) or {}
    try:
        issue = service.create_issue(release, data, get_current_user())
    except IssueValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify(service.detail(issue)), 201


@brain_bp.route('/release-issues/<int:issue_id>', methods=['GET'])
@admin_required
def get_release_issue(issue_id):
    issue = _issue_or_404(issue_id)
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404
    return jsonify(service.detail(issue)), 200


@brain_bp.route('/release-issues/<int:issue_id>', methods=['PATCH'])
@admin_required
def update_release_issue(issue_id):
    issue = _issue_or_404(issue_id)
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404

    data = request.get_json(silent=True) or {}
    try:
        service.update_issue(issue, data, get_current_user())
    except IssueValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify(service.detail(issue)), 200


@brain_bp.route('/release-issues/<int:issue_id>/comments', methods=['POST'])
@admin_required
def add_release_issue_comment(issue_id):
    issue = _issue_or_404(issue_id)
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404

    data = request.get_json(silent=True) or {}
    try:
        comment = service.add_comment(issue, data.get('body'), get_current_user())
    except IssueValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify(comment.to_dict()), 201


@brain_bp.route('/release-issues/<int:issue_id>/attachments', methods=['POST'])
@admin_required
def upload_release_issue_attachment(issue_id):
    issue = _issue_or_404(issue_id)
    if not issue:
        return jsonify({'error': 'Issue not found'}), 404

    file = request.files.get('file')
    if not file:
        return jsonify({'error': "Missing 'file' part"}), 400

    file_bytes = file.read()
    if not file_bytes:
        return jsonify({'error': 'File is empty'}), 400
    if len(file_bytes) > C.ATTACHMENT_MAX_BYTES:
        return jsonify({'error': 'File is larger than 50 MB'}), 400

    mime_type = sniff_mime(file_bytes, file.mimetype, file.filename)
    if not mime_type:
        return jsonify({'error': 'File must be a photo or a PDF'}), 400

    comment_id = request.form.get('comment_id', type=int)
    try:
        attachment = service.add_attachment(
            issue,
            file_bytes=file_bytes,
            filename=file.filename,
            mime_type=mime_type,
            user=get_current_user(),
            comment_id=comment_id,
        )
    except IssueValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify(attachment.to_dict()), 201


@brain_bp.route('/release-issues/<int:issue_id>/attachments/<int:attachment_id>/file', methods=['GET'])
@admin_required
def get_release_issue_attachment_file(issue_id, attachment_id):
    attachment = db.session.get(ReleaseIssueAttachment, attachment_id)
    if not attachment or attachment.issue_id != issue_id or attachment.is_deleted:
        return jsonify({'error': 'Attachment not found'}), 404

    path = absolute_path(attachment.storage_key)
    if not path.exists():
        logger.error('release_issue_attachment_file_missing', release_issue_id=issue_id,
                     attachment_id=attachment_id, exc_info=False)
        return jsonify({'error': 'File missing on disk'}), 410

    return send_file(
        str(path),
        mimetype=attachment.mime_type or 'application/octet-stream',
        as_attachment=False,
        download_name=attachment.original_filename or path.name,
        conditional=True,
    )


@brain_bp.route('/release-issues/<int:issue_id>/attachments/<int:attachment_id>', methods=['DELETE'])
@admin_required
def delete_release_issue_attachment(issue_id, attachment_id):
    attachment = db.session.get(ReleaseIssueAttachment, attachment_id)
    if not attachment or attachment.issue_id != issue_id:
        return jsonify({'error': 'Attachment not found'}), 404
    if attachment.is_deleted:
        return jsonify({'status': 'already_deleted'}), 200

    # Soft delete only: the file stays on disk so evidence is never lost to a misclick.
    attachment.is_deleted = True
    db.session.commit()
    logger.info('release_issue_attachment_deleted', release_issue_id=issue_id,
                attachment_id=attachment_id, user_id=get_current_user().id)
    return jsonify({'status': 'deleted', 'attachment_id': attachment_id}), 200
