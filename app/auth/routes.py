"""Authentication routes for login, logout, and user management."""
from flask import Blueprint, request, jsonify, session
from app.models import User, db
from app.auth.utils import verify_password, get_current_user
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
        
        username = data.get('username')
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
                'is_admin': user.is_admin
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
            'is_active': user.is_active,
            'last_login': user.last_login.isoformat() if user.last_login else None
        }), 200
    except Exception as e:
        logger.error(f"Error getting current user info: {e}", exc_info=True)
        return jsonify({'error': 'An error occurred'}), 500


