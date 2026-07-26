"""Session helpers and route decorator for Subcontractor auth.

Structurally mirrors app/auth/utils.py's get_current_user()/login_required so
the pattern is familiar, but reads session['subcontractor_id'] and the
Subcontractor table — never session['user_id']/User, and never the reverse.
Password hashing is imported from app.auth.utils rather than reimplemented,
so "same hashing mechanism as internal accounts" holds by construction, not
by convention.
"""
from functools import wraps

from flask import session, jsonify, has_request_context

from app.auth.utils import hash_password, verify_password  # noqa: F401 - re-exported for callers
from app.models import Subcontractor, db
from app.logging_config import get_logger

logger = get_logger(__name__)


def get_current_subcontractor():
    """Resolve session['subcontractor_id'] to a Subcontractor, or None.

    Returns None outside request context (mirrors get_current_user's
    background-thread guard), if no session, or if the account is inactive.
    """
    if not has_request_context():
        return None
    try:
        subcontractor_id = session.get('subcontractor_id')
        if not subcontractor_id:
            return None
        sub = db.session.get(Subcontractor, subcontractor_id)
        if sub and sub.is_active:
            return sub
        return None
    except Exception as e:
        logger.error("get_current_subcontractor_failed", error=str(e), exc_info=True)
        return None


def subcontractor_login_required(f):
    """401 if no active Subcontractor session. Does not accept a User session
    — an internal admin hitting a subcontractor-facing route must log in as a
    subcontractor separately (there is no shared/elevated path)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        sub = get_current_subcontractor()
        if not sub:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function
