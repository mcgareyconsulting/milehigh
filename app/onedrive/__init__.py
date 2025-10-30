from flask import Blueprint
from app.onedrive.utils import run_onedrive_poll

onedrive_bp = Blueprint("onedrive", __name__)
