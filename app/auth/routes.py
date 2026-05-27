"""
@milehigh-header
schema_version: 1
purpose: Handle the full session-auth lifecycle so users can log in, set initial passwords, and check auth state.
exports:
  auth_bp: Flask blueprint registered at /api/auth with login, logout, me, check-user, set-password routes
  login: POST endpoint that verifies credentials and creates a Flask session
  logout: POST endpoint that clears the session
  get_current_user_info: GET endpoint returning the authenticated user's profile
  set_password: POST endpoint for first-login password setup flow
imports_from: [flask, app.models, app.auth.utils, app.logging_config, datetime]
imported_by: [app/__init__.py]
invariants:
  - set_password only works when user.password_set is False; once True the endpoint rejects further changes
  - session['user_id'] is the single source of auth state; clearing it logs the user out
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Authentication routes for login, logout, and user management."""
from flask import Blueprint, request, jsonify, session
from app.models import User, db
from app.auth.utils import verify_password, get_current_user, hash_password
from app.logging_config import get_logger
from datetime import datetime

logger = get_logger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/login', methods=['POST'])
def login():
    """Login endpoint that authenticates user and creates a session."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        username = data.get('username', '').lower()
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Find user
        user = User.query.filter_by(username=username).first()
        
        if not user:
            logger.warning(f"Login attempt with non-existent username: {username}")
            return jsonify({'error': 'Invalid username or password'}), 401
        
        if not user.is_active:
            logger.warning(f"Login attempt for inactive user: {username}")
            return jsonify({'error': 'Account is inactive'}), 403
        
        # Verify password
        if not verify_password(user.password_hash, password):
            logger.warning(f"Failed login attempt for user: {username}")
            return jsonify({'error': 'Invalid username or password'}), 401
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Create session
        session['user_id'] = user.id
        session['username'] = user.username
        session.permanent = True
        
        logger.info(f"User {username} logged in successfully")
        
        return jsonify({
            'status': 'success',
            'user': {
                'id': user.id,
                'username': user.username,
                'is_admin': user.is_admin,
                'is_drafter': user.is_drafter
            }
        }), 200

    except Exception as e:
        logger.error(f"Error during login: {e}", exc_info=True)
        return jsonify({'error': 'An error occurred during login'}), 500


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Logout endpoint that clears the session."""
    try:
        username = session.get('username', 'Unknown')
        session.clear()
        logger.info(f"User {username} logged out")
        return jsonify({'status': 'success', 'message': 'Logged out successfully'}), 200
    except Exception as e:
        logger.error(f"Error during logout: {e}", exc_info=True)
        return jsonify({'error': 'An error occurred during logout'}), 500


@auth_bp.route('/me', methods=['GET'])
def get_current_user_info():
    """Get current logged-in user information."""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401

        return jsonify({
            'id': user.id,
            'username': user.username,
            'is_admin': user.is_admin,
            'is_drafter': user.is_drafter,
            'is_active': user.is_active,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'gmail_linked': user.gmail_credentials is not None,
            'gmail_email': user.gmail_credentials.email if user.gmail_credentials else None,
            'outlook_linked': user.outlook_credentials is not None,
            'outlook_email': user.outlook_credentials.email if user.outlook_credentials else None,
            'wants_daily_brief': bool(user.wants_daily_brief),
        }), 200
    except Exception as e:
        logger.error(f"Error getting current user info: {e}", exc_info=True)
        return jsonify({'error': 'An error occurred'}), 500


@auth_bp.route('/check-user', methods=['POST'])
def check_user():
    """Check if a user exists and whether they need to set a password.

    Request body: { "username": "<email>" }
    Response: { "exists": true, "needs_password_setup": true/false }
    or: { "exists": false }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        username = data.get('username', '').lower()
        if not username:
            return jsonify({'error': 'Username is required'}), 400

        # Look up user by username (email)
        user = User.query.filter_by(username=username).first()

        if not user:
            logger.info(f"Check user: account not found for {username}")
            return jsonify({'exists': False}), 200

        if not user.is_active:
            logger.info(f"Check user: account inactive for {username}")
            return jsonify({'exists': True, 'needs_password_setup': False}), 200

        needs_setup = not user.password_set
        logger.info(f"Check user: {username} exists, needs_password_setup={needs_setup}")

        return jsonify({
            'exists': True,
            'needs_password_setup': needs_setup
        }), 200

    except Exception as e:
        logger.error(f"Error during check user: {e}", exc_info=True)
        return jsonify({'error': 'An error occurred'}), 500


@auth_bp.route('/set-password', methods=['POST'])
def set_password():
    """Set password for a user on first login.

    Request body: {
        "username": "<email>",
        "new_password": "...",
        "confirm_password": "..."
    }

    Validates:
    - User exists
    - password_set == False
    - Passwords match
    - Minimum length >= 8 chars

    On success, sets password, marks password_set = True, creates session.
    Returns same shape as login endpoint.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        username = data.get('username', '').lower()
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')

        if not username or not new_password or not confirm_password:
            return jsonify({'error': 'Username and passwords are required'}), 400

        # Find user
        user = User.query.filter_by(username=username).first()

        if not user:
            logger.warning(f"Set password attempt for non-existent user: {username}")
            return jsonify({'error': 'User not found'}), 404

        if not user.is_active:
            logger.warning(f"Set password attempt for inactive user: {username}")
            return jsonify({'error': 'Account is inactive'}), 403

        # Check if password has already been set
        if user.password_set:
            logger.warning(f"Set password attempt for user with password already set: {username}")
            return jsonify({'error': 'Password has already been set for this account'}), 400

        # Validate password match
        if new_password != confirm_password:
            return jsonify({'error': 'Passwords do not match'}), 400

        # Validate minimum length
        if len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        # Set password and mark as set
        user.password_hash = hash_password(new_password)
        user.password_set = True
        user.last_login = datetime.utcnow()
        db.session.commit()

        # Create session
        session['user_id'] = user.id
        session['username'] = user.username
        session.permanent = True

        logger.info(f"User {username} set password and logged in successfully")

        return jsonify({
            'status': 'success',
            'user': {
                'id': user.id,
                'username': user.username,
                'is_admin': user.is_admin,
                'is_drafter': user.is_drafter
            }
        }), 200

    except Exception as e:
        logger.error(f"Error during set password: {e}", exc_info=True)
        return jsonify({'error': 'An error occurred'}), 500


