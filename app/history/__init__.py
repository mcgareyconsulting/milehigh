"""
@milehigh-header
schema_version: 1
purpose: Provide audit trail endpoints for job and submittal change history.
exports:
  history_bp: Blueprint registering history query routes.
  _extract_new_value_from_payload: Human-readable summary for ReleaseEvents payloads.
  _extract_submittal_new_value_from_payload: Human-readable summary for SubmittalEvents payloads.
imports_from: [flask, app.datetime_utils, app.logging_config, app.models]
imported_by: [app/__init__.py]
invariants:
  - Filters out system echo events (is_system_echo == False) from all queries.
  - Models are imported inside functions to avoid circular imports.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

History blueprint — job and submittal change audit trail routes.

Routes:
    GET /api/jobs/<job>/<release>/history
    GET /api/jobs/history
    GET /api/submittals/history
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from app.auth.utils import invoicing_report_access_required
from app.datetime_utils import format_datetime_mountain, get_mountain_timezone
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

    # Field-level updates carry the changed field name explicitly:
    # {'field': <name>, 'old_value': ..., 'new_value': ...}
    if isinstance(payload, dict) and 'field' in payload:
        field = payload['field']
        if 'new_value' in payload:
            return f"{field} → {payload['new_value']}"
        return str(field)

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
            if 'order_step' in payload:
                step_dir = payload['order_step']
                on = payload.get('order_number', {})
                old_n = on.get('old', 'N/A') if isinstance(on, dict) else 'N/A'
                new_n = on.get('new', 'N/A') if isinstance(on, dict) else 'N/A'
                msg = f"Order stepped {step_dir}: {old_n} → {new_n}"
                swapped = payload.get('swapped_with')
                if swapped and swapped.get('submittal_id'):
                    msg += f" (swapped with {swapped['submittal_id']})"
                changes.append(msg)
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


def _month_range_utc(year, month):
    """Return [start, end) naive-UTC datetimes bounding a Mountain-Time month.

    Event timestamps are stored as naive UTC; we compute the month boundaries in
    Mountain Time (how the user thinks about a month) and convert to UTC so the
    filter lines up with stored values.
    """
    mtn = get_mountain_timezone()
    start_local = datetime(year, month, 1, tzinfo=mtn)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=mtn)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=mtn)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def _project_sort_key(number):
    """Sort numeric project numbers naturally; non-numeric ones sort after."""
    try:
        return (0, int(number))
    except (ValueError, TypeError):
        return (1, str(number))


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

        from app.models import ReleaseDrawingVersion, db
        release_ids_with_drawings = set()
        if job_records:
            release_ids_with_drawings = {
                row[0] for row in
                db.session.query(ReleaseDrawingVersion.release_id)
                .filter(
                    ReleaseDrawingVersion.release_id.in_([jr.id for jr in job_records]),
                    ReleaseDrawingVersion.is_deleted.is_(False),
                )
                .distinct()
                .all()
            }

        for job_row in job_records:
            job_key = (job_row.job, job_row.release)
            job_releases.add(job_key)
            job_details.append({
                'id': job_row.id,
                'job': job_row.job,
                'release': job_row.release,
                'job_name': job_row.job_name,
                'description': job_row.description,
                'install_hrs': job_row.install_hrs,
                'start_install': job_row.start_install.isoformat() if job_row.start_install else None,
                'trello_list_name': job_row.trello_list_name,
                'viewer_url': job_row.viewer_url,
                'has_drawing': job_row.id in release_ids_with_drawings,
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


@history_bp.route("/api/reports/monthly-invoicing")
@invoicing_report_access_required
def monthly_invoicing_report():
    """Monthly invoicing report: change history for all releases and submittals
    in a given month, grouped by project.

    Query params (default to the current Mountain-Time month):
        year=<int>&month=<int>

    Only projects with at least one release or submittal change event in the
    month are included; each item carries only that month's events.
    """
    from app.models import ReleaseEvents, SubmittalEvents, Releases, Submittals, Projects

    now_mtn = datetime.now(get_mountain_timezone())
    year = request.args.get('year', type=int) or now_mtn.year
    month = request.args.get('month', type=int) or now_mtn.month
    if month < 1 or month > 12:
        return jsonify({'error': 'Invalid month', 'message': 'month must be between 1 and 12'}), 400

    try:
        start_utc, end_utc = _month_range_utc(year, month)

        release_events = ReleaseEvents.query.filter(
            ReleaseEvents.created_at >= start_utc,
            ReleaseEvents.created_at < end_utc,
            ReleaseEvents.is_system_echo == False,  # noqa: E712
        ).order_by(ReleaseEvents.created_at.asc()).all()

        submittal_events = SubmittalEvents.query.filter(
            SubmittalEvents.created_at >= start_utc,
            SubmittalEvents.created_at < end_utc,
            SubmittalEvents.is_system_echo == False,  # noqa: E712
        ).order_by(SubmittalEvents.created_at.asc()).all()

        # Bulk-fetch parent records to avoid N+1 lookups.
        release_keys = {(e.job, e.release) for e in release_events}
        submittal_ids = {e.submittal_id for e in submittal_events}

        releases_by_key = {}
        if release_keys:
            jobs = {k[0] for k in release_keys}
            for r in Releases.query.filter(Releases.job.in_(jobs)).all():
                releases_by_key[(r.job, r.release)] = r

        submittals_by_id = {}
        if submittal_ids:
            for s in Submittals.query.filter(Submittals.submittal_id.in_(submittal_ids)).all():
                submittals_by_id[s.submittal_id] = s

        # Canonical project names keyed by project number (string).
        project_numbers = {str(job) for (job, _release) in release_keys}
        for sid in submittal_ids:
            s = submittals_by_id.get(sid)
            if s and s.project_number:
                project_numbers.add(str(s.project_number))

        project_names = {}
        if project_numbers:
            for p in Projects.query.filter(Projects.job_number.in_(project_numbers)).all():
                project_names[str(p.job_number)] = p.name

        projects = {}

        def _bucket(number, fallback_name):
            bucket = projects.get(number)
            if bucket is None:
                bucket = {
                    'project_number': number,
                    'project_name': project_names.get(number) or fallback_name,
                    '_releases': {},
                    '_submittals': {},
                }
                projects[number] = bucket
            elif not bucket['project_name'] and fallback_name:
                bucket['project_name'] = fallback_name
            return bucket

        for e in release_events:
            number = str(e.job)
            r = releases_by_key.get((e.job, e.release))
            bucket = _bucket(number, r.job_name if r else None)
            rkey = (e.job, e.release)
            item = bucket['_releases'].get(rkey)
            if item is None:
                item = {
                    'job': e.job,
                    'release': e.release,
                    'description': r.description if r else None,
                    'pm': r.pm if r else None,
                    'stage': r.stage if r else None,
                    'install_prog': r.job_comp if r else None,
                    'invoiced': r.invoiced if r else None,
                    'events': [],
                }
                bucket['_releases'][rkey] = item
            item['events'].append({
                'id': e.id,
                'action': e.action,
                'new_value': _extract_new_value_from_payload(e.action, e.payload),
                'payload': e.payload,
                'source': e.source,
                'internal_user_id': e.internal_user_id,
                'external_user_id': e.external_user_id,
                'created_at': format_datetime_mountain(e.created_at),
            })

        for e in submittal_events:
            s = submittals_by_id.get(e.submittal_id)
            number = str(s.project_number) if (s and s.project_number) else 'Unknown'
            bucket = _bucket(number, s.project_name if s else None)
            item = bucket['_submittals'].get(e.submittal_id)
            if item is None:
                item = {
                    'submittal_id': e.submittal_id,
                    'title': s.title if s else None,
                    'status': s.status if s else None,
                    'ball_in_court': s.ball_in_court if s else None,
                    'submittal_manager': s.submittal_manager if s else None,
                    'events': [],
                }
                bucket['_submittals'][e.submittal_id] = item
            item['events'].append({
                'id': e.id,
                'action': e.action,
                'new_value': _extract_submittal_new_value_from_payload(e.action, e.payload),
                'payload': e.payload,
                'source': e.source,
                'internal_user_id': e.internal_user_id,
                'external_user_id': e.external_user_id,
                'created_at': format_datetime_mountain(e.created_at),
            })

        result_projects = []
        for number in sorted(projects.keys(), key=_project_sort_key):
            bucket = projects[number]
            releases_list = []
            for rkey in sorted(bucket['_releases'].keys(), key=lambda k: (k[0], str(k[1]))):
                item = bucket['_releases'][rkey]
                item['total_changes'] = len(item['events'])
                item['events'].reverse()  # most recent change first
                releases_list.append(item)
            submittals_list = []
            for sid in sorted(bucket['_submittals'].keys(), key=str):
                item = bucket['_submittals'][sid]
                item['total_changes'] = len(item['events'])
                item['events'].reverse()  # most recent change first
                submittals_list.append(item)
            result_projects.append({
                'project_number': bucket['project_number'],
                'project_name': bucket['project_name'],
                'releases': releases_list,
                'submittals': submittals_list,
            })

        return jsonify({
            'year': year,
            'month': month,
            'month_label': datetime(year, month, 1).strftime('%B %Y'),
            'generated_at': format_datetime_mountain(datetime.utcnow()),
            'total_projects': len(result_projects),
            'projects': result_projects,
        }), 200

    except Exception as e:
        logger.exception("Error generating monthly invoicing report")
        return jsonify({'error': 'Failed to generate report', 'message': str(e)}), 500
