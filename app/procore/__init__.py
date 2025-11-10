# Package
from flask import Blueprint, request

procore_bp = Blueprint("procore", __name__)

@procore_bp.route("/webhook", methods=["HEAD", "POST"])
def procore_webhook():
    if request.method == "HEAD":
        return "", 200

    if request.method == "POST":
        data = request.json
        print(data)
        return "", 200