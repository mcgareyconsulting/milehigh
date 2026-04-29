# Auth module for user authentication and authorization

from app.auth.routes import auth_bp  # noqa: F401
from app.auth import google  # noqa: F401  attaches /google/initiate + /google/callback to auth_bp
