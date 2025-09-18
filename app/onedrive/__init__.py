from flask import Blueprint, jsonify, request, make_response
import json
from app.onedrive.utils import run_onedrive_poll

onedrive_bp = Blueprint("onedrive", __name__)


@onedrive_bp.route("/poll", methods=["GET"])
def onedrive_poll():
    """
    Manual poll endpoint to check lastModifiedDateTime of Excel file.
    """
    from app.sync import sync_from_onedrive

    # Handle polling requests
    print("[OneDrive] Polling request received")

    # Process the data as needed
    event_info = run_onedrive_poll()

    # Return a JSON response
    return event_info["data"].to_dict(orient="records"), 200
