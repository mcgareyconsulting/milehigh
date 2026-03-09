"""
History blueprint — job and submittal change audit trail routes.

Routes:
    GET /api/jobs/<job>/<release>/history
    GET /api/jobs/history
    GET /api/submittals/history
"""

from flask import Blueprint, jsonify, request
from app.datetime_utils import format_datetime_mountain
from app.logging_config import get_logger

logger = get_logger(__name__)

history_bp = Blueprint("history", __name__)


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def _extract_new_value_from_payload(action, payload):
    """Human-readable summary of the new value for a ReleaseEvents payload."""
    if not payload:
        return None

    if action == 'update_stage':
        return payload.get('to')

    if action == 'list_move':
        to_list = payload.get('to_list_name') or payload.get('to_list_id')
        from_list = payload.get('from_list_name') or payload.get('from_list_id')
        if to_list and from_list:
            return to_list
        return to_list or None

    if action in ['created', 'create']:
        if isinstance(payload, dict):
            parts = []
            if 'Job' in payload:
                parts.append(f"Job: {payload['Job']}")
            if 'Release' in payload:
                parts.append(f"Release: {payload['Release']}")
            return " | ".join(parts) if parts else "Job created"
        return "Job created"

    if isinstance(payload, dict):
        for key in ['to', 'value', 'new_value', 'status', 'stage', 'state']:
            if key in payload:
                return str(payload[key])
        if len(payload) == 1:
            return str(list(payload.values())[0])
        return f"{len(payload)} fields updated"

    return str(payload) if payload else None


def _extract_submittal_new_value_from_payload(action, payload):
    """Human-readable summary of the new value for a SubmittalEvents payload."""
    if not payload:
        return None

    if action == 'created':
        if isinstance(payload, dict):
            parts = []
            if 'title' in payload:
                parts.append(f"Title: {payload['title']}")
            if 'status' in payload:
                parts.append(f"Status: {payload['status']}")
            return " | ".join(parts) if parts else "Submittal created"
        return "Submittal created"

    if action == 'updated':
        if isinstance(payload, dict):
            changes = []
            if 'ball_in_court' in payload:
                old_val = payload['ball_in_court'].get('old', 'N/A')
                new_val = payload['ball_in_court'].get('new', 'N/A')
                changes.append(f"Ball in Court: {old_val} → {new_val}")
            if 'status' in payload:
                old_val = payload['status'].get('old', 'N/A')
                new_val = payload['status'].get('new', 'N/A')
                changes.append(f"Status: {old_val} → {new_val}")
            if payload.get('order_bumped'):
                changes.append(f"Order bumped to {payload.get('order_number', 'N/A')}")
            return " | ".join(changes) if changes else "Submittal updated"
        return "Submittal updated"

    if isinstance(payload, dict):
        for key in ['to', 'value', 'new_value', 'status', 'stage', 'state']:
            if key in payload:
                return str(payload[key])
        if len(payload) == 1:
            return str(list(payload.values())[0])
        return f"{len(payload)} fields updated"

    return str(payload) if payload else None


# ---------------------------------------------------------------------------
# Internal query functions
# ---------------------------------------------------------------------------

def _get_job_change_history(job, release):
    """Query and format job event history."""
    from app.models import ReleaseEvents, Releases

    if job is None and release is None:
        return jsonify({
            'error': 'Missing required parameters',
            'message': 'At least one of job (int) or release (str) is required',
            'usage': {
                'job_only': '/api/jobs/history?job=<int>',
                'release_only': '/api/jobs/history?release=<str>',
                'both': '/api/jobs/history?job=<int>&release=<str>',
                'path': '/api/jobs/<job>/<release>/history'
            }
        }), 400

    try:
        events_query = ReleaseEvents.query.filter(
            ReleaseEvents.is_system_echo == False  # noqa: E712
        )
        if job is not None:
            events_query = events_query.filter(ReleaseEvents.job == job)
        if release is not None:
            events_query = events_query.filter(ReleaseEvents.release == str(release))

        job_events = events_query.order_by(ReleaseEvents.created_at.desc()).all()

        job_query = Releases.query
        if job is not None:
            job_query = job_query.filter_by(job=job)
        if release is not None:
            job_query = job_query.filter_by(release=str(release))
        job_records = job_query.all()

        history = []
        job_releases = set()
        job_details = []

        for event in job_events:
            new_value = _extract_new_value_from_payload(event.action, event.payload)
            history.append({
                'id': event.id,
                'job': event.job,
                'release': event.release,
                'action': event.action,
                'new_value': new_value,
                'payload': event.payload,
                'payload_hash': event.payload_hash,
                'source': event.source,
                'internal_user_id': event.internal_user_id,
                'external_user_id': event.external_user_id,
                'created_at': format_datetime_mountain(event.created_at),
                'applied_at': format_datetime_mountain(event.applied_at) if event.applied_at else None
            })
            job_releases.add((event.job, event.release))

        for job_row in job_records:
            job_key = (job_row.job, job_row.release)
            job_releases.add(job_key)
            job_details.append({
                'job': job_row.job,
                'release': job_row.release,
                'job_name': job_row.job_name,
                'description': job_row.description,
                'install_hrs': job_row.install_hrs,
                'start_install': job_row.start_install.isoformat() if job_row.start_install else None,
                'trello_list_name': job_row.trello_list_name,
                'viewer_url': job_row.viewer_url
            })

        if not job_releases and job_records:
            job_releases = {(jr.job, jr.release) for jr in job_records}

        search_type = (
            'both' if job is not None and release is not None
            else ('job' if job is not None else 'release')
        )

        default_selection = None
        if job_details:
            if job is not None and release is not None:
                default_selection = next(
                    (d for d in job_details if d['job'] == job and d['release'] == str(release)),
                    None
                )
            if default_selection is None:
                default_selection = job_details[0]

        return jsonify({
            'search_type': search_type,
            'search_job': job,
            'search_release': release,
            'job_releases': [{'job': jr[0], 'release': jr[1]} for jr in sorted(job_releases)],
            'total_changes': len(history),
            'history': history,
            'job_details': job_details,
            'default_selection': default_selection
        }), 200

    except Exception as e:
        logger.error("Error getting job event history", error=str(e), job=job, release=release)
        return jsonify({
            'error': 'Failed to retrieve change history',
            'message': str(e)
        }), 500


def _get_submittal_change_history(submittal_id):
    """Query and format submittal event history."""
    from app.models import SubmittalEvents, Submittals

    if not submittal_id:
        return jsonify({
            'error': 'Missing required parameter',
            'message': 'submittal_id (str) is required',
            'usage': {'submittal_id': '/api/submittals/history?submittal_id=<str>'}
        }), 400

    try:
        events_query = SubmittalEvents.query.filter(
            SubmittalEvents.submittal_id == str(submittal_id),
            SubmittalEvents.is_system_echo == False,  # noqa: E712
        )
        submittal_events = events_query.order_by(SubmittalEvents.created_at.desc()).all()
        submittal_record = Submittals.query.filter_by(submittal_id=str(submittal_id)).first()

        history = []
        for event in submittal_events:
            new_value = _extract_submittal_new_value_from_payload(event.action, event.payload)
            history.append({
                'id': event.id,
                'submittal_id': event.submittal_id,
                'action': event.action,
                'new_value': new_value,
                'payload': event.payload,
                'payload_hash': event.payload_hash,
                'source': event.source,
                'internal_user_id': event.internal_user_id,
                'external_user_id': event.external_user_id,
                'created_at': format_datetime_mountain(event.created_at),
                'applied_at': format_datetime_mountain(event.applied_at) if event.applied_at else None
            })

        submittal_details = None
        if submittal_record:
            submittal_details = {
                'submittal_id': submittal_record.submittal_id,
                'title': submittal_record.title,
                'status': submittal_record.status,
                'type': submittal_record.type,
                'ball_in_court': submittal_record.ball_in_court,
                'project_name': submittal_record.project_name,
                'project_number': submittal_record.project_number
            }

        return jsonify({
            'search_type': 'submittal',
            'search_submittal_id': submittal_id,
            'total_changes': len(history),
            'history': history,
            'submittal_details': submittal_details
        }), 200

    except Exception as e:
        logger.exception("Error retrieving submittal change history")
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@history_bp.route("/api/jobs/<int:job>/<release>/history")
def job_change_history_path(job, release):
    """Get change history for a specific job-release via URL path."""
    return _get_job_change_history(job, release)


@history_bp.route("/api/jobs/history")
def job_change_history_query():
    """Get job change history via query parameters (job, release)."""
    job = request.args.get('job', type=int)
    release = request.args.get('release', type=str)
    return _get_job_change_history(job, release)


@history_bp.route("/api/submittals/history")
def submittal_change_history():
    """Get submittal change history via query parameter (submittal_id)."""
    submittal_id = request.args.get('submittal_id', type=str)
    return _get_submittal_change_history(submittal_id)
