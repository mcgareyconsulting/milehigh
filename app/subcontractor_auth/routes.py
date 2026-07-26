"""HTTP routes for Subcontractor auth (invite acceptance, login, logout, me).

POST /brain/subcontractors (admin, elsewhere in app/brain/tm/subcontractors/)
creates the Subcontractor row and its invite token; everything here is what
the invited person themselves hits — GET/POST are public until a session
exists, matching the shape of app/auth/routes.py's login but with a real
token-based first-set-password step instead of a DB-flag-gated one (an
external account can't rely on "you must already know the username" as its
only barrier the way an internally-provisioned User account can).
"""
import hashlib
import hmac
from datetime import datetime

from flask import Blueprint, request, jsonify, session

from app.models import Subcontractor, db
from app.subcontractor_auth.utils import hash_password, verify_password, get_current_subcontractor
from app.logging_config import get_logger

logger = get_logger(__name__)

subcontractor_auth_bp = Blueprint('subcontractor_auth', __name__, url_prefix='/api/subcontractor-auth')

INVITE_TOKEN_MIN_PASSWORD_LENGTH = 8


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _lookup_by_token(raw_token: str):
    """Resolve a raw invite token to (subcontractor, error_response_tuple).
    Exactly one of the two is non-None. Never leaks whether an email/account
    exists beyond "token not found" — same response for garbage and for an
    expired-and-cleared token that just happens to collide with nothing.
    """
    if not raw_token:
        return None, (jsonify({'error': 'Invite token is required'}), 400)

    token_hash = _hash_token(raw_token)
    candidates = Subcontractor.query.filter(Subcontractor.invite_token_hash.isnot(None)).all()
    sub = next(
        (s for s in candidates if hmac.compare_digest(s.invite_token_hash, token_hash)),
        None,
    )
    if sub is None:
        return None, (jsonify({'error': 'Invite not found or already used'}), 404)
    if sub.invite_token_expires_at and sub.invite_token_expires_at < datetime.utcnow():
        return None, (jsonify({'error': 'Invite has expired'}), 410)
    return sub, None


@subcontractor_auth_bp.route('/invite/<token>', methods=['GET'])
def validate_invite(token):
    """No side effect — lets the accept-invite page pre-fill name/company and
    show a clean expired/invalid state without burning the token on a page load."""
    sub, error = _lookup_by_token(token)
    if error:
        return error
    return jsonify({
        'valid': True,
        'company_name': sub.company_name,
        'contact_name': sub.contact_name,
        'email': sub.email,
    }), 200


@subcontractor_auth_bp.route('/accept-invite', methods=['POST'])
def accept_invite():
    """Consume the token: set password, mark accepted, clear the token fields
    (single-use — a replayed raw token no longer matches anything after
    this), create session."""
    data = request.get_json(silent=True) or {}
    raw_token = data.get('token')
    password = data.get('password')
    confirm_password = data.get('confirm_password')

    sub, error = _lookup_by_token(raw_token)
    if error:
        return error

    if not password or not confirm_password:
        return jsonify({'error': 'Password and confirmation are required'}), 400
    if password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400
    if len(password) < INVITE_TOKEN_MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'Password must be at least {INVITE_TOKEN_MIN_PASSWORD_LENGTH} characters'}), 400

    sub.password_hash = hash_password(password)
    sub.invite_accepted_at = datetime.utcnow()
    sub.invite_token_hash = None
    sub.invite_token_expires_at = None
    sub.last_login = datetime.utcnow()
    db.session.commit()

    # Clear first — a leftover staff user_id from an earlier session in this same
    # browser must never coexist with a subcontractor session (see module docstring).
    session.clear()
    session['subcontractor_id'] = sub.id
    session.permanent = True

    logger.info("subcontractor_invite_accepted", subcontractor_id=sub.id, email=sub.email)
    return jsonify({'status': 'success', 'subcontractor': sub.to_dict()}), 200


@subcontractor_auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    sub = Subcontractor.query.filter_by(email=email).first()
    if not sub or not sub.is_active or not sub.password_hash:
        # Same response whether the account doesn't exist, isn't active, or
        # hasn't accepted its invite yet — don't leak which.
        logger.warning("subcontractor_login_failed", email=email)
        return jsonify({'error': 'Invalid email or password'}), 401

    if not verify_password(sub.password_hash, password):
        logger.warning("subcontractor_login_failed", email=email)
        return jsonify({'error': 'Invalid email or password'}), 401

    sub.last_login = datetime.utcnow()
    db.session.commit()

    # Clear first (see accept_invite's identical comment).
    session.clear()
    session['subcontractor_id'] = sub.id
    session.permanent = True

    logger.info("subcontractor_logged_in", subcontractor_id=sub.id, email=sub.email)
    return jsonify({'status': 'success', 'subcontractor': sub.to_dict()}), 200


@subcontractor_auth_bp.route('/logout', methods=['POST'])
def logout():
    sub_id = session.get('subcontractor_id')
    session.pop('subcontractor_id', None)
    logger.info("subcontractor_logged_out", subcontractor_id=sub_id)
    return jsonify({'status': 'success'}), 200


@subcontractor_auth_bp.route('/me', methods=['GET'])
def me():
    sub = get_current_subcontractor()
    if not sub:
        return jsonify({'error': 'Not authenticated'}), 401
    return jsonify(sub.to_dict()), 200
