# Package
from flask import Blueprint

from app.logging_config import get_logger

logger = get_logger(__name__)

api_bp = Blueprint("api", __name__)

from app.api import routes

