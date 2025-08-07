from flask import Blueprint, request, make_response
import json

onedrive_bp = Blueprint("onedrive", __name__)


@onedrive_bp.route("/webhook", methods=["GET", "POST"])
def onedrive_webhook():
    # Handle Microsoft Graph subscription validation
    validation_token = request.args.get("validationToken")
    if validation_token:
        print(f"[OneDrive] Webhook validation request received")
        resp = make_response(validation_token, 200)
        resp.headers["Content-Type"] = "text/plain"
        return resp

    # Handle actual webhook notifications
    if request.method == "POST":
        try:
            data = request.get_json()
            if not data:
                print("[OneDrive] No JSON data received")
                return "", 400

            # Microsoft Graph sends notifications in a 'value' array
            notifications = data.get("value", [])

            for notification in notifications:
                resource = notification.get("resource")
                change_type = notification.get("changeType")
                client_state = notification.get("clientState")

                print(f"[OneDrive] Notification received:")
                print(f"  Resource: {resource}")
                print(f"  Change Type: {change_type}")
                print(f"  Client State: {client_state}")

                # Process specific change types
                if change_type == "updated":
                    print(f"[OneDrive] File/folder updated: {resource}")

                    # Run comparison when file is updated
                    try:
                        from app.sync import run_comparison

                        differences = run_comparison()

                        if differences:
                            print(
                                f"[OneDrive] Found {len(differences)} differences after file update"
                            )
                            # You can add additional logic here, such as:
                            # - Send notifications
                            # - Update database
                            # - Log to a file
                            # - Trigger other workflows

                            # Example: Log some details about the differences
                            for diff in differences[:5]:  # Log first 5 differences
                                print(
                                    f"  Difference in {diff['identifier']}: {diff['diff_columns']}"
                                )
                                for col in diff["diff_columns"][
                                    :3
                                ]:  # Show first 3 different columns
                                    col_diff = diff["column_differences"][col]
                                    print(
                                        f"    {col}: DB='{col_diff['db']}' vs Excel='{col_diff['excel']}'"
                                    )
                        else:
                            print("[OneDrive] No differences found after file update")

                    except Exception as e:
                        print(f"[OneDrive] Error running comparison: {str(e)}")

                elif change_type == "created":
                    print(f"[OneDrive] File/folder created: {resource}")
                elif change_type == "deleted":
                    print(f"[OneDrive] File/folder deleted: {resource}")

                # # Add your custom processing logic here
                # from app.sync import sync_from_onedrive

                # sync_from_onedrive(notification)

            return "", 202  # Accepted - webhook processed successfully

        except json.JSONDecodeError:
            print("[OneDrive] Invalid JSON received")
            return "", 400
        except Exception as e:
            print(f"[OneDrive] Error processing webhook: {str(e)}")
            return "", 500

    return "", 405  # Method not allowed
