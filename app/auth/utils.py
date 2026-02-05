"""Authentication utilities for password hashing and user management."""
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session, jsonify
from app.models import User, db
from app.logging_config import get_logger

logger = get_logger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using werkzeug's security utilities.
    
    Uses pbkdf2:sha256 method which is compatible with Python 3.9+.
    scrypt is only available in Python 3.11+.
    """
    return generate_password_hash(password, method='pbkdf2:sha256')


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password against a hash."""
    return check_password_hash(password_hash, password)


def get_current_user():
    """
    Get the current logged-in user from the session.
    
    Returns:
        User object if logged in, None otherwise
    """
    from flask import has_request_context
    
    # If we're not in a request context (e.g., background thread), return None
    if not has_request_context():
        return None
    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return None
        
        user = User.query.get(user_id)
        if user and user.is_active:
            return user
        return None
    except Exception as e:
        logger.error(f"Error getting current user: {e}", exc_info=True)
        return None


def get_current_username():
    """
    Get the current logged-in user's username.
    
    Returns:
        str: Username if logged in, None otherwise
    """
    user = get_current_user()
    return user.username if user else None


def format_source_with_user(source: str, user=None) -> str:
    """
    Format source string with user information.
    
    Args:
        source: Base source string (e.g., 'Brain', 'Procore') or already formatted (e.g., 'Trello - username')
        user: User object or None to get from session
    
    Returns:
        str: Formatted source like 'Brain - Daniel' or just 'Brain' if no user
    """
    # If source already contains " - ", it's already formatted, return as-is
    if " - " in source:
        return source
    
    if user is None:
        user = get_current_user()
    
    if user:
        username = user.username if hasattr(user, 'username') else str(user)
        return f"{source} - {username}"
    return source


def login_required(f):
    """
    Decorator to require user login for a route.
    
    Returns 401 Unauthorized if user is not logged in.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator to require admin privileges for a route.
    
    Returns 401 Unauthorized if user is not logged in.
    Returns 403 Forbidden if user is not an admin.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        if not user.is_admin:
            logger.warning(f"Non-admin user {user.username} attempted to access admin-only route")
            return jsonify({'error': 'Admin privileges required'}), 403
        return f(*args, **kwargs)
    return decorated_function

