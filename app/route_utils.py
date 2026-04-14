"""
@milehigh-header
schema_version: 1
purpose: Decorators and helpers that reduce boilerplate in Flask route handlers (error wrapping, JSON validation, 404 lookups).
exports:
  handle_errors: Decorator — wraps a route in try/except with db.session.rollback and structured error response
  require_json: Decorator — validates JSON body and required fields, stores parsed data on flask.g.json_data
  get_or_404: Looks up a record or returns a (None, (response, 404)) tuple for early return
imports_from: [flask, app/logging_config, app/models]
imported_by: [app/brain/job_log/routes.py, app/brain/drafting_work_load/routes.py, app/admin/__init__.py]
invariants: []
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Route handler utilities to reduce boilerplate across Flask endpoints.
"""
from functools import wraps
from flask import request, jsonify, g
from app.logging_config import get_logger
from app.models import db

logger = get_logger(__name__)


def handle_errors(operation_name, raw_error=False):
    """Decorator that wraps a route in try/except with rollback and error logging.

    On unhandled exception: rolls back db.session, logs the error, and returns
    a 500 JSON response.

    Args:
        operation_name: Describes the operation for log messages.
        raw_error: When False (default), returns
            ``{"error": "Failed to <operation_name>", "details": str(exc)}``.
            When True, returns ``{"error": str(exc), "error_type": "<ExcType>"}``.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as exc:
                if raw_error:
                    logger.error(f"{operation_name} failed", exc_info=True)
                    db.session.rollback()
                    return jsonify({
                        "error": str(exc),
                        "error_type": type(exc).__name__
                    }), 500
                else:
                    logger.error(f"Error in {operation_name}", error=str(exc))
                    db.session.rollback()
                    return jsonify({
                        "error": f"Failed to {operation_name}",
                        "details": str(exc)
                    }), 500
        return decorated_function
    return decorator


def require_json(*required_fields):
    """Decorator that validates JSON request body and required fields.

    Parses request JSON and returns 400 if the body is missing or not JSON.
    For each field in required_fields, returns 400 if the value is None.
    Stores the parsed dict on ``flask.g.json_data``.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            data = request.get_json(silent=True)
            if data is None:
                return jsonify({"error": "No JSON data provided"}), 400
            for field in required_fields:
                if data.get(field) is None:
                    return jsonify({"error": f"{field} is required"}), 400
            g.json_data = data
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_or_404(model, error_msg=None, **filter_kwargs):
    """Look up a single record or return a 404 error tuple.

    Returns:
        (record, None) if found.
        (None, (response, 404)) if not found.

    Usage::

        submittal, err = get_or_404(Submittals, submittal_id=sid)
        if err:
            return err
    """
    record = model.query.filter_by(**filter_kwargs).first()
    if record is None:
        msg = error_msg or f"{model.__name__} not found"
        return None, (jsonify({"error": msg}), 404)
    return record, None
