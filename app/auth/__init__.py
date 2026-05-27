# Auth module for user authentication and authorization

from app.auth.routes import auth_bp  # noqa: F401
from app.auth import google  # noqa: F401  attaches /google/initiate + /google/callback to auth_bp
from app.auth import microsoft  # noqa: F401  attaches /microsoft/* to auth_bp
