"""Banana Boy — per-user AI assistant powered by Claude Haiku."""
from flask import Blueprint

banana_boy_bp = Blueprint("banana_boy", __name__)

from app.banana_boy import routes  # noqa: E402, F401
