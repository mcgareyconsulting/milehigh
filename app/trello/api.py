import requests
import re
import os
from app.config import Config as cfg
from app.trello.utils import mountain_due_datetime
from app.models import Job, db
from flask import current_app
from datetime import datetime
import pandas as pd
import math


# Main function for updating trello card information
def update_trello_card(card_id, new_list_id=None, new_due_date=None, clear_due_date=False):
    """
    Updates a Trello card\'s list and/or due date in a single API call.
    
    Args:
        card_id: Trello card ID
        new_list_id: New list ID (optional)
        new_due_date: New due date as datetime object (optional)
        clear_due_date: If True, explicitly clear the due date even if new_due_date is None
    """
    url = f"https://api.trello.com/1/cards/{card_id}"

    payload = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
    }

    if new_list_id:
        payload["idList"] = new_list_id

    # Handle due date
    if new_due_date:
        # Set due date to 6pm Mountain time, DST-aware
        payload["due"] = mountain_due_datetime(new_due_date)
    elif clear_due_date:
        # Explicitly clear the due date using empty string (Trello API requirement)
        payload["due"] = ""
    # If neither new_due_date nor clear_due_date, don't include 'due' parameter at all

    try:
        # Log the payload for debugging
        print(f"[TRELLO API] Updating card {card_id} with payload: {payload}")
        
        response = requests.put(url, params=payload)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        print(f"[TRELLO API] Card {card_id} updated successfully")
        return response.json()

    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error updating card {card_id}: {http_err}")
        print("[TRELLO API] Response content:", response.text)
        raise
    except Exception as err:
        print(f"[TRELLO API] Other error updating card {card_id}: {err}")
        raise


## Helper functions for combining Trello and Excel data
def get_list_name_by_id(list_id):
    """
    Fetches the list name from Trello API by list ID.
    """
    url = f"https://api.trello.com/1/lists/{list_id}"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get("name")
    else:
        print(f"Trello API error: {response.status_code} {response.text}")
        return None


def get_list_by_name(list_name):
    """
    Fetches the list details from Trello API by list name.
    """
    url = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/lists"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        lists = response.json()
        for lst in lists:
            if lst["name"] == list_name:
                return {"name": lst["name"], "id": lst["id"]}
    else:
        print(f"Trello API error: {response.status_code} {response.text}")
        return None


def get_trello_card_by_id(card_id):
    """
    Fetches the full card data from Trello API by card ID.
    """
    url = f"https://api.trello.com/1/cards/{card_id}"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Trello API error: {response.status_code} {response.text}")
        return None


def get_trello_cards_from_subset():
    """
    Fetch all Trello cards from the board and filter them based on a specific subset.
    """
    # Hardcoded list of stage names
    target_list_names = [
        "Fit Up Complete.",
        "Paint complete",
        "Shipping completed",
        "Store at MHMW for shipping",
        "Shipping planning",
    ]

    # Get all lists on the board
    url_lists = url_lists = (
        f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/lists"
    )
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url_lists, params=params)
    response.raise_for_status()
    lists = response.json()

    # Get list IDs for your target lists
    target_list_ids = [lst["id"] for lst in lists if lst["name"] in target_list_names]

    # debug statement
    # print(f"Target List IDs: {target_list_ids}")

    # Get all cards on the board
    url_cards = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/cards"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "fields": "id,name,desc,idList,due,labels",
        "filter": "open",
    }
    response = requests.get(url_cards, params=params)
    response.raise_for_status()
    cards = response.json()

    # Build a mapping from list ID to list name
    list_id_to_name = {lst["id"]: lst["name"] for lst in lists}

    # Filter cards by your target list IDs
    filtered_cards = [card for card in cards if card["idList"] in target_list_ids]
    relevant_data = [
        {
            "id": card["id"],
            "name": card["name"],
            "desc": card["desc"],
            "list_id": card["idList"],
            "list_name": list_id_to_name.get(card["idList"], "Unknown"),
            "due": card.get("due"),
            "labels": [label["name"] for label in card.get("labels", [])],
        }
        for card in filtered_cards
    ]
    return relevant_data


def check_job_exists_in_db(job_number, release_number):
    """
    Check if a job with the given job number and release number already exists in the database.
    
    Args:
        job_number: The job number (can be int or string)
        release_number: The release number (can be int or string)
    
    Returns:
        Job object if found, None if not found
        
    Raises:
        Exception: For debugging purposes - will be caught and logged by caller
    """
    try:
        print(f"[DEBUG] Checking for job: {job_number}-{release_number}")
        
        # Convert job_number to int, keep release_number as string to preserve format like "v862"
        job_int = int(job_number)
        release_str = str(release_number)
        
        print(f"[DEBUG] Converted identifiers - job_int: {job_int}, release_str: {release_str}")
        
        # Use Flask application context for database access
        existing_job = Job.query.filter_by(job=job_int, release=release_str).one_or_none()
        print(f"[DEBUG] Database query completed, found job: {existing_job is not None}")
        
        return existing_job
        
    except (ValueError, TypeError) as e:
        error_msg = f"Invalid job or release identifiers: job={job_number}, release={release_number}, error={str(e)}"
        print(f"[ERROR] {error_msg}")
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Database error checking for job {job_number}-{release_number}: {str(e)}"
        print(f"[ERROR] {error_msg}")
        print(f"[ERROR] Exception type: {type(e).__name__}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        raise Exception(error_msg)


def to_date(val):
    """Convert a value to a date, returning None if conversion fails or value is null."""
    if pd.isnull(val) or val is None or str(val).strip() == '':
        return None
    try:
        dt = pd.to_datetime(val)
        return dt.date() if not pd.isnull(dt) else None
    except:
        return None


def safe_float(val):
    """Safely convert a value to float, returning None if conversion fails."""
    try:
        return float(val) if val is not None and str(val).strip() != '' else None
    except (TypeError, ValueError):
        return None


def safe_string(val, max_length=None):
    """Safely convert a value to string, optionally truncating."""
    if val is None or pd.isna(val):
        return None
    string_val = str(val)
    if max_length and len(string_val) > max_length:
        return string_val[:max_length-3] + "..."
    return string_val


def create_job_record_from_excel_data(excel_data):
    """
    Create a Job record from Excel data only (without Trello data initially).
    
    Args:
        excel_data: Dictionary containing Excel data from macro
    
    Returns:
        Job object if created successfully, None otherwise
    """
    try:
        from app.onedrive.utils import parse_excel_datetime
        
        # Extract basic identifiers
        job_number = int(excel_data.get('Job #', 0))
        release_number = str(excel_data.get('Release #', ''))
        
        # Create new Job record with Excel data only
        new_job = Job(
            # Basic identifiers
            job=job_number,
            release=release_number,
            
            # Excel data
            job_name=safe_string(excel_data.get('Job'), 128),
            description=safe_string(excel_data.get('Description'), 256),
            fab_hrs=safe_float(excel_data.get('Fab Hrs')),
            install_hrs=safe_float(excel_data.get('Install HRS')),
            paint_color=safe_string(excel_data.get('Paint color'), 64),
            pm=safe_string(excel_data.get('PM'), 16),
            by=safe_string(excel_data.get('BY'), 16),
            released=to_date(excel_data.get('Released')),
            fab_order=safe_float(excel_data.get('Fab Order')),
            cut_start=safe_string(excel_data.get('Cut start'), 8),
            fitup_comp=safe_string(excel_data.get('Fitup comp'), 8),
            welded=safe_string(excel_data.get('Welded'), 8),
            paint_comp=safe_string(excel_data.get('Paint Comp'), 8),
            ship=safe_string(excel_data.get('Ship'), 8),
            start_install=to_date(excel_data.get('Start install')),
            comp_eta=to_date(excel_data.get('Comp. ETA')),
            job_comp=safe_string(excel_data.get('Job Comp'), 8),
            invoiced=safe_string(excel_data.get('Invoiced'), 8),
            notes=safe_string(excel_data.get('Notes'), 256),
            
            # Trello fields will be empty initially
            trello_card_id=None,
            trello_card_name=None,
            trello_list_id=None,
            trello_list_name=None,
            trello_card_description=None,
            
            # Metadata
            last_updated_at=datetime.utcnow(),
            source_of_update='Excel'  # Created from Excel macro
        )
        
        # Save to database
        db.session.add(new_job)
        db.session.commit()
        
        print(f"[DEBUG] Created Job record: {job_number}-{release_number} (ID: {new_job.id})")
        return new_job
        
    except Exception as e:
        print(f"[ERROR] Failed to create Job record: {str(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        db.session.rollback()
        return None


def update_job_record_with_trello_data(job_record, card_data):
    """
    Update an existing Job record with Trello card data.
    
    Args:
        job_record: Existing Job object
        card_data: Dictionary containing Trello card information
    
    Returns:
        True if updated successfully, False otherwise
    """
    try:
        # Update Trello fields
        job_record.trello_card_id = card_data.get('id')
        job_record.trello_card_name = card_data.get('name')
        job_record.trello_list_id = card_data.get('idList')
        job_record.trello_list_name = get_list_name_by_id(card_data.get('idList'))
        job_record.trello_card_description = card_data.get('desc', '')
        
        # Update metadata
        job_record.last_updated_at = datetime.utcnow()
        
        # Save changes
        db.session.commit()
        
        print(f"[DEBUG] Updated Job record {job_record.id} with Trello data")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to update Job record with Trello data: {str(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        db.session.rollback()
        return False


def create_trello_card_from_excel_data(excel_data, list_name=None):
    """
    Creates a Trello card from Excel macro data.
    First checks if a job with the same identifier already exists in the database.
    
    Args:
        excel_data: Dictionary containing job data from Excel macro
        list_name: Optional list name to create the card in (defaults to first available list)
    
    Returns:
        Dictionary with card creation result
    """
    try:
        print(f"[DEBUG] Starting card creation with data: {excel_data}")
        
        # Check for duplicate job in database first
        job_number = excel_data.get('Job #')
        release_number = excel_data.get('Release #')
        
        print(f"[DEBUG] Extracted identifiers - Job #: {job_number}, Release #: {release_number}")
        
        if not job_number or not release_number:
            error_msg = "Missing Job # or Release # in Excel data"
            print(f"[ERROR] {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
        
        print(f"[DEBUG] Checking for duplicate job in database...")
        existing_job = check_job_exists_in_db(job_number, release_number)
        
        if existing_job:
            error_msg = f"Job {job_number}-{release_number} already exists in database"
            print(f"[DEBUG] {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "existing_job_id": existing_job.id,
                "existing_trello_card_id": existing_job.trello_card_id
            }
        
        print(f"[DEBUG] No duplicate found, proceeding with card creation...")
        
        # Create database record with Excel data first
        print(f"[DEBUG] Creating database record with Excel data...")
        new_job = create_job_record_from_excel_data(excel_data)
        
        if not new_job:
            return {
                "success": False,
                "error": "Failed to create database record"
            }
        
        print(f"[DEBUG] Database record created: Job {new_job.id}")
        
        # # Get the target list ID - default to "Released" list
        # if list_name:
        #     target_list = get_list_by_name(list_name)
        #     if not target_list:
        #         raise ValueError(f"List '{list_name}' not found on the board")
        #     list_id = target_list["id"]
        # else:
        #     # Default to "Released" list
        #     target_list = get_list_by_name("Released")
        #     if not target_list:
        #         # Fallback to first available list if "Released" not found
        #         url_lists = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/lists"
        #         params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
        #         response = requests.get(url_lists, params=params)
        #         response.raise_for_status()
        #         lists = response.json()
        #         if not lists:
        #             raise ValueError("No lists found on the board")
        #         list_id = lists[0]["id"]  # Use first list
        #     else:
        #         list_id = target_list["id"]
        
        # Format card title
        job_number = excel_data.get('Job #', 'Unknown')
        release_number = excel_data.get('Release #', 'Unknown')
        job_name = excel_data.get('Job', 'Unknown Job')
        card_title = f"{job_number}-{release_number} {job_name}"
        
        # Format card description with bold field names
        description_parts = []
        
        # Job description (first line)
        if excel_data.get('Description'):
            description_parts.append(f"**Description:** {excel_data['Description']}")
        
        # Add field details with bold formatting
        if excel_data.get('Install HRS'):
            install_hrs = excel_data.get('Install HRS')
            description_parts.append(f"**Install HRS:** {install_hrs}")
            
            # Installation Duration calculation with error handling
            try:
                # Handle different data types (None, NaN, string, number)
                if install_hrs is None or str(install_hrs).lower() in ['nan', 'none', '']:
                    print(f"[DEBUG] Install HRS is empty/None: {install_hrs}")
                else:
                    # Convert to float, handling string numbers
                    install_hrs_float = float(install_hrs)
                    if install_hrs_float > 0:
                        installation_duration = math.ceil(install_hrs_float / 2.5)
                        description_parts.append(f"**Installation Duration:** {installation_duration} days")
                        print(f"[DEBUG] Install HRS: {install_hrs} -> Duration: {installation_duration} days")
                    else:
                        print(f"[DEBUG] Install HRS is zero or negative: {install_hrs_float}")
            except (ValueError, TypeError) as e:
                print(f"[DEBUG] Error calculating installation duration: {e}, Install HRS: {install_hrs} (type: {type(install_hrs)})")
            except Exception as e:
                print(f"[DEBUG] Unexpected error calculating installation duration: {e}, Install HRS: {install_hrs}")

        # Paint Color
        if excel_data.get('Paint color'):
            description_parts.append(f"**Paint color:** {excel_data['Paint color']}")

        # Team
        if excel_data.get('PM') and excel_data.get('BY'):
            description_parts.append(f"**Team:** PM: {excel_data['PM']} / BY: {excel_data['BY']}")
        
        # Released
        if excel_data.get('Released'):
            description_parts.append(f"**Released:** {excel_data['Released']}")
        
        # Join all description parts with newlines
        card_description = "\n".join(description_parts)
        
        # Create the card
        url = "https://api.trello.com/1/cards"
        
        payload = {
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
            "name": card_title,
            "desc": card_description,
            "idList": cfg.NEW_TRELLO_CARD_LIST_ID,
            "pos": "top"  # Add to top of list
        }
        
        print(f"[TRELLO API] Creating card with payload: {payload}")
        
        response = requests.post(url, params=payload)
        response.raise_for_status()
        
        card_data = response.json()
        print(f"[TRELLO API] Card created successfully: {card_data['id']}")
        
        # Update the existing database record with Trello card data
        print(f"[DEBUG] Updating database record with Trello card data...")
        success = update_job_record_with_trello_data(new_job, card_data)
        
        if success:
            print(f"[DEBUG] Successfully updated database record with Trello data")
        else:
            print(f"[ERROR] Failed to update database record with Trello data")
        
        return {
            "success": True,
            "card_id": card_data["id"],
            "card_name": card_data["name"],
            "card_url": card_data["url"],
            "job_id": new_job.id
        }
        
    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error creating card: {http_err}")
        print("[TRELLO API] Response content:", response.text)
        return {
            "success": False,
            "error": f"HTTP error: {http_err}",
            "response": response.text
        }
    except Exception as err:
        print(f"[TRELLO API] Other error creating card: {err}")
        return {
            "success": False,
            "error": str(err)
        }
    
    except Exception as e:
        error_msg = f"Unexpected error in create_trello_card_from_excel_data: {str(e)}"
        print(f"[ERROR] {error_msg}")
        import traceback
        print(f"[ERROR] Full traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": error_msg,
            "exception_type": type(e).__name__
        }


def get_card_custom_field_items(card_id):
    """
    Retrieves all custom field items for a Trello card.
    
    Args:
        card_id: Trello card ID
    
    Returns:
        List of custom field items or None if error
    """
    url = f"https://api.trello.com/1/cards/{card_id}/customFieldItems"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error getting custom field items for card {card_id}: {http_err}")
        return None
    except Exception as err:
        print(f"[TRELLO API] Error getting custom field items for card {card_id}: {err}")
        return None


def update_card_custom_field(card_id, custom_field_id, text_value):
    """
    Updates a custom field on a Trello card.
    
    Args:
        card_id: Trello card ID
        custom_field_id: Custom field ID
        text_value: New text value for the custom field
    
    Returns:
        True if successful, False otherwise
    """
    url = f"https://api.trello.com/1/cards/{card_id}/customField/{custom_field_id}/item"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN
    }
    data = {
        "value": {"text": text_value}
    }
    
    try:
        print(f"[TRELLO API] Updating custom field {custom_field_id} on card {card_id} with value: {text_value[:100]}...")
        response = requests.put(url, params=params, json=data)
        response.raise_for_status()
        print(f"[TRELLO API] Custom field updated successfully")
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error updating custom field: {http_err}")
        print("[TRELLO API] Response content:", response.text)
        return False
    except Exception as err:
        print(f"[TRELLO API] Error updating custom field: {err}")
        return False


def add_comment_to_trello_card(card_id, comment_text, operation_id=None):
    """
    Adds a timestamped comment to a Trello card.
    
    Args:
        card_id: Trello card ID
        comment_text: Comment text to add
        operation_id: Optional operation ID for logging
    
    Returns:
        True if successful, False otherwise
    """
    if not comment_text or not comment_text.strip():
        print(f"[TRELLO API] Skipping empty comment for card {card_id}")
        return True
    
    # Format comment with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_comment = f"[{timestamp}] {comment_text.strip()}"
    
    url = f"https://api.trello.com/1/cards/{card_id}/actions/comments"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "text": formatted_comment
    }
    
    try:
        print(f"[TRELLO API] Adding comment to card {card_id}: {formatted_comment[:100]}...")
        response = requests.post(url, params=params)
        response.raise_for_status()
        print(f"[TRELLO API] Comment added successfully")
        if operation_id:
            print(f"[TRELLO API] Operation ID: {operation_id}")
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error adding comment: {http_err}")
        print("[TRELLO API] Response content:", response.text)
        return False
    except Exception as err:
        print(f"[TRELLO API] Error adding comment: {err}")
        return False
