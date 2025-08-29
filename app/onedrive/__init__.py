from flask import Blueprint, jsonify, request, make_response
import json
from app.onedrive.utils import parse_polling_data

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
    event_info = parse_polling_data()

    # Trigger sync process
    sync_from_onedrive(event_info)

    return "Successfully passed data to sync", 200


# @onedrive_bp.route("/webhook", methods=["GET", "POST"])
# def onedrive_webhook():
#     # Handle Microsoft Graph subscription validation
#     validation_token = request.args.get("validationToken")
#     if validation_token:
#         print(f"[OneDrive] Webhook validation request received")
#         resp = make_response(validation_token, 200)
#         resp.headers["Content-Type"] = "text/plain"
#         return resp

#     # Handle actual webhook notifications
#     if request.method == "POST":
#         try:
#             data = request.get_json()
#             if not data:
#                 print("[OneDrive] No JSON data received")
#                 return "", 400

#             # Microsoft Graph sends notifications in a 'value' array
#             notifications = data.get("value", [])

#             for notification in notifications:
#                 resource = notification.get("resource")
#                 change_type = notification.get("changeType")
#                 client_state = notification.get("clientState")

#                 print(f"[OneDrive] Notification received:")
#                 print(f"  Resource: {resource}")
#                 print(f"  Change Type: {change_type}")
#                 print(f"  Client State: {client_state}")

#                 if change_type == "updated":
#                     print(f"[OneDrive] File/folder updated: {resource}")
#                 elif change_type == "created":
#                     print(f"[OneDrive] File/folder created: {resource}")
#                 elif change_type == "deleted":
#                     print(f"[OneDrive] File/folder deleted: {resource}")

#                 # # Add your custom processing logic here
#                 # from app.sync import sync_from_onedrive

#                 # sync_from_onedrive(notification)

#             return "", 202  # Accepted - webhook processed successfully

#         except json.JSONDecodeError:
#             print("[OneDrive] Invalid JSON received")
#             return "", 400
#         except Exception as e:
#             print(f"[OneDrive] Error processing webhook: {str(e)}")
#             return "", 500

#     return "", 405  # Method not allowed
