import requests
import re
import os
from app.config import Config as cfg
from app.trello.utils import mountain_due_datetime, mountain_start_datetime
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
        # Clear the due date - use null value in JSON
        payload["due"] = None
    # If neither new_due_date nor clear_due_date, don't include 'due' parameter at all

    try:
        # Log the payload for debugging
        print(f"[TRELLO API] Updating card {card_id} with payload: {payload}")
        
        # Use JSON when clearing due dates (null values), otherwise use URL params
        if clear_due_date and payload.get("due") is None:
            # Use JSON to properly send null values for clearing
            auth_params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
            json_payload = {"due": None}
            if new_list_id:
                json_payload["idList"] = new_list_id
            response = requests.put(url, params=auth_params, json=json_payload)
        else:
            # Use URL params for normal updates
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
        "Released",
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


def get_all_trello_cards():
    """
    Fetch all open Trello cards from the board (all lists, not just a subset).
    
    Returns:
        list: List of card dictionaries with id, name, desc, idList, due, labels, and list_name
    """
    # Get all lists on the board
    url_lists = f"https://api.trello.com/1/boards/{cfg.TRELLO_BOARD_ID}/lists"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    response = requests.get(url_lists, params=params)
    response.raise_for_status()
    lists = response.json()
    
    # Build a mapping from list ID to list name
    list_id_to_name = {lst["id"]: lst["name"] for lst in lists}
    
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
    
    # Add list_name to each card
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
        for card in cards
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
        try:
            job_int = int(job_number)
        except (ValueError, TypeError):
            error_msg = f"Invalid job number: {job_number} - cannot convert to integer"
            print(f"[ERROR] {error_msg}")
            raise Exception(error_msg)
        
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
        
        # Extract basic identifiers with validation
        job_val = excel_data.get('Job #')
        try:
            job_number = int(job_val) if job_val is not None else 0
        except (ValueError, TypeError):
            print(f"[ERROR] Invalid Job # value: {job_val} - cannot convert to integer")
            return None
        
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
        # Store the ID BEFORE commit (while object is still in session)
        job_id = job_record.id
        
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
        
        # Use the stored ID instead of accessing the expired object
        print(f"[DEBUG] Updated Job record {job_id} with Trello data")
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
        
        # Determine Trello list to create the card in
        if list_name:
            target_list = get_list_by_name(list_name)
            if not target_list:
                raise ValueError(f"List '{list_name}' not found on the board")
            list_id = target_list["id"]
        else:
            # Default to configured new-card list
            list_id = cfg.NEW_TRELLO_CARD_LIST_ID
        
        # Format card title
        job_number = excel_data.get('Job #', 'Unknown')
        release_number = excel_data.get('Release #', 'Unknown')
        job_name = excel_data.get('Job', 'Unknown Job')
        job_description = excel_data.get('Description', 'Unknown Description')
        card_title = f"{job_number}-{release_number} {job_name} {job_description}"
        
        # Format card description with bold field names
        description_parts = []
        
        # Job description (first line)
        if excel_data.get('Description'):
            description_parts.append(f"**Description:** {excel_data['Description']}")
        
        # Add field details with bold formatting
        if excel_data.get('Install HRS'):
            install_hrs = excel_data.get('Install HRS')
            description_parts.append(f"**Install HRS:** {install_hrs}")
            # Number of Guys
            num_guys = 2
            description_parts.append(f"**Number of Guys:** {num_guys}")
            
            # Installation Duration calculation with error handling
            installation_duration = calculate_installation_duration(install_hrs, num_guys)
            if installation_duration is not None:
                description_parts.append(f"**Installation Duration:** {installation_duration} days")

        # Paint Color
        if excel_data.get('Paint color'):
            description_parts.append(f"**Paint color:** {excel_data['Paint color']}")

        # Team
        if excel_data.get('PM') and excel_data.get('BY'):
            description_parts.append(f"**Team:** PM: {excel_data['PM']} / BY: {excel_data['BY']}")
        
        # Released
        if excel_data.get('Released'):
            released_date = to_date(excel_data.get('Released'))
            if released_date:
                description_parts.append(f"**Released:** {released_date}")
        
        # Join all description parts with newlines
        card_description = "\n".join(description_parts)
        
        # Create the card
        url = "https://api.trello.com/1/cards"
        
        payload = {
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
            "name": card_title,
            "desc": card_description,
            "idList": list_id,
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
        
        # Handle Fab Order custom field - set if value exists in Excel
        fab_order_value = excel_data.get('Fab Order')
        if fab_order_value is not None and not pd.isna(fab_order_value):
            try:
                # Convert to int (round up if float)
                if isinstance(fab_order_value, float):
                    fab_order_int = math.ceil(fab_order_value)
                else:
                    fab_order_int = int(fab_order_value)
                
                # Update Trello custom field
                if cfg.FAB_ORDER_FIELD_ID:
                    fab_order_success = update_card_custom_field_number(
                        card_data["id"],
                        cfg.FAB_ORDER_FIELD_ID,
                        fab_order_int
                    )
                    if fab_order_success:
                        print(f"[DEBUG] Successfully set Fab Order custom field to {fab_order_int}")
                        
                        # Sort the list if it's one of the target lists
                        from app.trello.utils import sort_list_if_needed
                        sort_list_if_needed(
                            list_id,
                            cfg.FAB_ORDER_FIELD_ID,
                            None,  # No operation_id for card creation
                            "list"
                        )
                    else:
                        print(f"[ERROR] Failed to set Fab Order custom field")
                else:
                    print(f"[WARNING] FAB_ORDER_FIELD_ID not configured, skipping Fab Order custom field")
            except (ValueError, TypeError) as e:
                print(f"[ERROR] Could not convert Fab Order '{fab_order_value}' to int: {e}")
        
        # Handle notes field - append as comment if not empty
        notes_value = excel_data.get('Notes')
        # Check if notes value is valid (not None, not NaN, not empty string, not 'nan'/'NaN')
        if (notes_value is not None and 
            not pd.isna(notes_value) and 
            str(notes_value).strip() and
            str(notes_value).strip().lower() not in ['nan', 'none']):
            print(f"[DEBUG] Notes field found, appending as comment to Trello card: {notes_value}")
            comment_success = add_comment_to_trello_card(card_data["id"], str(notes_value).strip())
            if comment_success:
                print(f"[DEBUG] Successfully added notes as comment to Trello card")
            else:
                print(f"[ERROR] Failed to add notes as comment to Trello card")
        else:
            print(f"[DEBUG] No notes field, empty notes, NaN value, or 'nan'/'none' string, skipping comment addition")
        
        # Add FC Drawing link if viewer_url exists on the job
        if new_job.viewer_url:
            try:
                link_result = add_procore_link(card_data["id"], new_job.viewer_url, link_name="FC Drawing")
                if link_result.get("success"):
                    print(f"[DEBUG] Added FC Drawing link to card {card_data['id']}")
                else:
                    print(f"[WARNING] Failed to add FC Drawing link: {link_result.get('error')}")
            except Exception as link_err:
                print(f"[WARNING] Error adding FC Drawing link: {link_err}")
        
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


def get_board_custom_fields(board_id):
    """
    Get all custom fields for a Trello board.
    
    Args:
        board_id: Trello board ID
    
    Returns:
        List of custom field definitions or None if error
    """
    url = f"https://api.trello.com/1/boards/{board_id}/customFields"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error getting custom fields: {http_err}")
        print("[TRELLO API] Response content:", response.text)
        return None
    except Exception as err:
        print(f"[TRELLO API] Error getting custom fields: {err}")
        return None


def find_fab_order_field_id(custom_fields):
    """
    Find the custom field ID for 'Fab Order'.
    
    Args:
        custom_fields: List of custom field definitions
    
    Returns:
        Custom field ID (str) or None if not found
    """
    if not custom_fields:
        return None
    
    for field in custom_fields:
        if field.get("name") == "Fab Order":
            return field.get("id")
    
    return None


def update_card_custom_field_number(card_id, custom_field_id, number_value):
    """
    Updates a number custom field on a Trello card.
    
    Args:
        card_id: Trello card ID
        custom_field_id: Custom field ID
        number_value: Integer value for the custom field
    
    Returns:
        True if successful, False otherwise
    """
    url = f"https://api.trello.com/1/cards/{card_id}/customField/{custom_field_id}/item"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN
    }
    data = {
        "value": {"number": str(number_value)}  # Trello API expects number as string
    }
    
    try:
        print(f"[TRELLO API] Updating custom field {custom_field_id} on card {card_id} with value: {number_value}")
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


def sort_list_by_fab_order(list_id, fab_order_field_id):
    """
    Sort a Trello list by Fab Order custom field (ascending order).
    Cards without Fab Order values will be placed at the end.
    
    Args:
        list_id: Trello list ID to sort
        fab_order_field_id: Custom field ID for "Fab Order"
    
    Returns:
        dict with keys:
            - success: bool
            - cards_sorted: int (number of cards that were sorted)
            - cards_failed: int (number of cards that failed to update)
            - total_cards: int (total cards in list)
            - error: str (if success is False)
    """
    # Get all cards in the list with custom field items
    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "customFieldItems": "true",
        "fields": "id,pos,name"
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        cards = response.json()
        
        if not cards:
            print(f"[TRELLO API] List {list_id} is empty, nothing to sort")
            return {"success": True, "cards_sorted": 0, "cards_failed": 0, "total_cards": 0}
        
        # Extract Fab Order for each card
        card_data = []
        for card in cards:
            fab_order = None
            
            # Find Fab Order custom field value
            for field_item in card.get("customFieldItems", []):
                if field_item.get("idCustomField") == fab_order_field_id:
                    value = field_item.get("value", {})
                    number_val = value.get("number")
                    if number_val:
                        try:
                            # Convert to float then int (handles rounding)
                            fab_order = float(number_val)
                        except (ValueError, TypeError):
                            pass
                    break
            
            card_data.append({
                "card_id": card["id"],
                "card_name": card.get("name", "Unknown"),
                "fab_order": fab_order,
                "current_pos": card.get("pos")
            })
        
        # Sort by fab_order (None values go to end)
        # Cards with lower fab_order come first
        card_data.sort(key=lambda x: (x["fab_order"] is None, x["fab_order"] or 0))
        
        # Calculate new positions
        # Trello positions can be:
        # - "top" (string)
        # - "bottom" (string)
        # - numeric (float) - cards are ordered by position value
        
        position_updates = []
        
        if len(card_data) == 1:
            # Only one card - use "top"
            position_updates.append({
                "card_id": card_data[0]["card_id"],
                "new_pos": "top"
            })
        else:
            # Multiple cards - calculate positions
            # Start with a base position and increment
            base_position = 16384  # Standard starting position in Trello
            
            for index, card_info in enumerate(card_data):
                new_pos = base_position + (index * 16384)
                position_updates.append({
                    "card_id": card_info["card_id"],
                    "new_pos": new_pos,
                    "fab_order": card_info["fab_order"]
                })
        
        # Update card positions
        updated_count = 0
        failed_count = 0
        
        for update in position_updates:
            update_url = f"https://api.trello.com/1/cards/{update['card_id']}"
            update_params = {
                "key": cfg.TRELLO_API_KEY,
                "token": cfg.TRELLO_TOKEN,
                "pos": update["new_pos"]
            }
            
            try:
                update_response = requests.put(update_url, params=update_params)
                update_response.raise_for_status()
                updated_count += 1
            except requests.exceptions.HTTPError as http_err:
                print(f"[TRELLO API] HTTP error updating card {update['card_id']} position: {http_err}")
                failed_count += 1
            except Exception as err:
                print(f"[TRELLO API] Error updating card {update['card_id']} position: {err}")
                failed_count += 1
        
        if failed_count > 0:
            print(f"[TRELLO API] Sort completed with {failed_count} failures out of {len(position_updates)} cards")
        else:
            print(f"[TRELLO API] Successfully sorted list {list_id} ({updated_count} cards)")
        
        return {
            "success": True,
            "cards_sorted": updated_count,
            "cards_failed": failed_count,
            "total_cards": len(card_data)
        }
        
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"HTTP error sorting list {list_id}: {http_err}"
        print(f"[TRELLO API] {error_msg}")
        if hasattr(http_err.response, 'text'):
            print(f"[TRELLO API] Response: {http_err.response.text}")
        return {"success": False, "error": error_msg, "cards_sorted": 0, "cards_failed": 0, "total_cards": 0}
    except Exception as err:
        error_msg = f"Error sorting list {list_id}: {err}"
        print(f"[TRELLO API] {error_msg}")
        return {"success": False, "error": error_msg, "cards_sorted": 0, "cards_failed": 0, "total_cards": 0}


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


def get_card_attachments_by_job_release(job_number, release_number):
    """
    Get attachments for a Trello card by job number and release number.
    
    Args:
        job_number (int or str): The job number
        release_number (int or str): The release number
        
    Returns:
        dict: Dictionary containing success status and attachments data
    """
    try:
        # Convert job_number to int, keep release_number as string to preserve format like "v862"
        try:
            job_int = int(job_number)
        except (ValueError, TypeError):
            error_msg = f"Invalid job number: {job_number} - cannot convert to integer"
            print(f"[TRELLO API] {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "attachments": []
            }
        
        release_str = str(release_number)
        
        print(f"[TRELLO API] Looking up attachments for job: {job_int}-{release_str}")
        
        # Find the job record in the database
        job_record = Job.query.filter_by(job=job_int, release=release_str).one_or_none()
        
        if not job_record:
            return {
                "success": False,
                "error": f"Job {job_int}-{release_str} not found in database",
                "attachments": []
            }
        
        if not job_record.trello_card_id:
            return {
                "success": False,
                "error": f"Job {job_int}-{release_str} has no associated Trello card",
                "attachments": []
            }
        
        # Get attachments from Trello API
        url = f"https://api.trello.com/1/cards/{job_record.trello_card_id}/attachments"
        
        headers = {
            "Accept": "application/json"
        }
        
        query = {
            'key': cfg.TRELLO_API_KEY,
            'token': cfg.TRELLO_TOKEN
        }
        
        response = requests.get(url, headers=headers, params=query)
        
        if response.status_code == 200:
            attachments = response.json()
            print(f"[TRELLO API] Found {len(attachments)} attachments for job {job_int}-{release_str}")
            return {
                "success": True,
                "job": job_int,
                "release": release_str,
                "trello_card_id": job_record.trello_card_id,
                "trello_card_name": job_record.trello_card_name,
                "attachments": attachments
            }
        else:
            print(f"[TRELLO API] Error getting attachments: {response.status_code} {response.text}")
            return {
                "success": False,
                "error": f"Trello API error: {response.status_code} {response.text}",
                "attachments": []
            }
            
    except (ValueError, TypeError) as e:
        error_msg = f"Invalid job or release identifiers: job={job_number}, release={release_number}, error={str(e)}"
        print(f"[TRELLO API] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "attachments": []
        }
    except Exception as e:
        error_msg = f"Error getting attachments for job {job_number}-{release_number}: {str(e)}"
        print(f"[TRELLO API] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "attachments": []
        }


def update_mirror_card_date_range(trello_card_id, start_date, install_hrs):
    """
    Update the date range for a mirror card based on the main card's start date and installation duration.
    
    Args:
        trello_card_id (str): The main Trello card ID
        start_date (datetime.date): The exact start date (no business day adjustment)
        install_hrs (float): Installation hours to calculate duration
        
    Returns:
        dict: Dictionary containing success status and details
    """
    try:
        # Get attachments for the main card
        attachments_result = get_card_attachments_by_card_id(trello_card_id)
        
        if not attachments_result["success"]:
            return {
                "success": False,
                "error": f"Failed to get attachments: {attachments_result['error']}"
            }
        
        attachments = attachments_result["attachments"]
        
        # Validate we have exactly one attachment (the mirror card)
        if len(attachments) == 0:
            return {
                "success": False,
                "error": "No attachments found for this card"
            }
        elif len(attachments) > 1:
            print(f"[TRELLO API] Warning: Found {len(attachments)} attachments, expected 1 mirror card")
            # Continue anyway, but log the warning
        
        # Get the mirror card shortLink from the first attachment's fileName
        mirror_attachment = attachments[0]
        mirror_short_link = mirror_attachment.get("fileName")
        
        if not mirror_short_link:
            return {
                "success": False,
                "error": "No fileName found in attachment data"
            }
        
        # Calculate installation duration from install_hrs
        installation_duration = calculate_installation_duration(install_hrs)
        
        if installation_duration is None:
            return {
                "success": False,
                "error": f"Could not calculate installation duration from install_hrs: {install_hrs}"
            }
        
        # Calculate due date (x business days from start date)
        due_date = calculate_business_days_after(start_date, installation_duration)
        
        # Update the mirror card's date range
        return update_card_date_range(mirror_short_link, start_date, due_date)
        
    except Exception as e:
        error_msg = f"Error updating mirror card date range: {str(e)}"
        print(f"[TRELLO API] {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }


def get_card_attachments_by_card_id(trello_card_id):
    """
    Get attachments for a Trello card by card ID.
    
    Args:
        trello_card_id (str): The Trello card ID
        
    Returns:
        dict: Dictionary containing success status and attachments data
    """
    try:
        print(f"[TRELLO API] Looking up attachments for card: {trello_card_id}")
        
        # Get attachments from Trello API
        url = f"https://api.trello.com/1/cards/{trello_card_id}/attachments"
        
        headers = {
            "Accept": "application/json"
        }
        
        query = {
            'key': cfg.TRELLO_API_KEY,
            'token': cfg.TRELLO_TOKEN
        }
        
        response = requests.get(url, headers=headers, params=query)
        
        if response.status_code == 200:
            attachments = response.json()
            print(f"[TRELLO API] Found {len(attachments)} attachments for card {trello_card_id}")
            return {
                "success": True,
                "trello_card_id": trello_card_id,
                "attachments": attachments
            }
        else:
            print(f"[TRELLO API] Error getting attachments: {response.status_code} {response.text}")
            return {
                "success": False,
                "error": f"Trello API error: {response.status_code} {response.text}",
                "attachments": []
            }
            
    except Exception as e:
        error_msg = f"Error getting attachments for card {trello_card_id}: {str(e)}"
        print(f"[TRELLO API] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "attachments": []
        }


def calculate_installation_duration(install_hrs, num_guys=2.5):
    """
    Calculate installation duration in days from installation hours and number of guys.
    
    Args:
        install_hrs (float): Installation hours
        num_guys (float): Number of guys (default: 2.5 for backward compatibility)
        
    Returns:
        int: Installation duration in days, or None if calculation fails
    """
    try:
        if install_hrs is None or str(install_hrs).lower() in ['nan', 'none', '']:
            print(f"[DEBUG] Install HRS is empty/None: {install_hrs}")
            return None
        
        install_hrs_float = float(install_hrs)
        if install_hrs_float > 0 and num_guys > 0:
            # Calculate: (install hrs / num guys) / 8hrs/day
            installation_duration = math.ceil((install_hrs_float / float(num_guys)) / 8.0)
            print(f"[DEBUG] Install HRS: {install_hrs} / Num Guys: {num_guys} / 8hrs/day -> Duration: {installation_duration} days")
            return installation_duration
        else:
            print(f"[DEBUG] Install HRS is zero or negative: {install_hrs_float}, or num_guys is zero: {num_guys}")
            return None
            
    except (ValueError, TypeError) as e:
        print(f"[DEBUG] Error calculating installation duration: {e}, Install HRS: {install_hrs} (type: {type(install_hrs)}), Num Guys: {num_guys}")
        return None
    except Exception as e:
        print(f"[DEBUG] Unexpected error calculating installation duration: {e}, Install HRS: {install_hrs}")
        return None


def parse_num_guys_from_description(description):
    """
    Parse the 'Number of Guys:' value from a Trello card description.
    
    Args:
        description (str): The card description text
        
    Returns:
        float or None: The number of guys if found, None otherwise
    """
    if not description:
        return None
    
    # Pattern to match "**Number of Guys:** X" or "Number of Guys: X"
    pattern = r'\*\*Number\s+of\s+Guys:\*\*\s*(\d+(?:\.\d+)?)|Number\s+of\s+Guys:\s*(\d+(?:\.\d+)?)'
    match = re.search(pattern, description, re.IGNORECASE)
    
    if match:
        # Try first group (with **), then second group (without **)
        num_guys_str = match.group(1) or match.group(2)
        try:
            return float(num_guys_str)
        except (ValueError, TypeError):
            return None
    
    return None


def update_installation_duration_in_description(description, install_hrs, num_guys):
    """
    Update the installation duration in a description string based on install_hrs and num_guys.
    
    Args:
        description (str): The current card description
        install_hrs (float): Installation hours from database
        num_guys (float): Number of guys from description
        
    Returns:
        str: Updated description with new installation duration, or original if update fails
    """
    if not description or not install_hrs or not num_guys:
        print(f"[DEBUG] update_installation_duration_in_description: Missing required input - desc={bool(description)}, install_hrs={install_hrs}, num_guys={num_guys}")
        return description
    
    # Calculate new installation duration
    installation_duration = calculate_installation_duration(install_hrs, num_guys)
    if installation_duration is None:
        print(f"[DEBUG] update_installation_duration_in_description: Could not calculate duration")
        return description
    
    print(f"[DEBUG] update_installation_duration_in_description: Target duration = {installation_duration} days")
    
    # Pattern to match "**Installation Duration:** X days"
    pattern = r'(\*\*Installation\s+Duration:\*\*\s*)(\d+)\s*days'
    
    match = re.search(pattern, description, re.IGNORECASE)
    if match:
        current_duration = int(match.group(2))
        print(f"[DEBUG] update_installation_duration_in_description: Found existing duration = {current_duration} days")
        
        # Only update if duration has actually changed
        if current_duration != installation_duration:
            # Replace existing installation duration using lambda to avoid backreference issues
            def replace_duration(m):
                return f'{m.group(1)}{installation_duration} days'
            updated_description = re.sub(pattern, replace_duration, description, flags=re.IGNORECASE)
            print(f"[DEBUG] update_installation_duration_in_description: Updated {current_duration} -> {installation_duration} days")
            return updated_description
        else:
            print(f"[DEBUG] update_installation_duration_in_description: Duration unchanged ({current_duration} days)")
            return description
    else:
        print(f"[DEBUG] update_installation_duration_in_description: No existing Installation Duration found, attempting to add")
        # If no installation duration line exists, add it after Number of Guys
        num_guys_pattern = r'(\*\*Number\s+of\s+Guys:\*\*\s*\d+(?:\.\d+)?)'
        
        if re.search(num_guys_pattern, description, re.IGNORECASE):
            def add_duration(m):
                return f'{m.group(1)}\n**Installation Duration:** {installation_duration} days'
            updated_description = re.sub(num_guys_pattern, add_duration, description, flags=re.IGNORECASE)
            print(f"[DEBUG] update_installation_duration_in_description: Added new Installation Duration line")
            return updated_description
        else:
            print(f"[DEBUG] update_installation_duration_in_description: Could not find Number of Guys line to add duration after")
    
    return description


def parse_installation_duration(description):
    """
    Parse the '**Installation Duration:** X days' value from a Trello card description.
    Returns an int or None.
    """
    if not description:
        return None
    pattern = r"\*\*Installation\s+Duration:\*\*\s*(\d+)\s*days"
    m = re.search(pattern, description, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None

def update_trello_card_description(card_id, new_description):
    """
    Update a Trello card's description via API.
    
    Args:
        card_id (str): Trello card ID
        new_description (str): New description text
        
    Returns:
        dict: Response from Trello API, or None if update fails
    """
    url = f"https://api.trello.com/1/cards/{card_id}"
    
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "desc": new_description
    }
    
    try:
        print(f"[TRELLO API] Updating description for card {card_id}")
        response = requests.put(url, params=params)
        response.raise_for_status()
        
        print(f"[TRELLO API] Card {card_id} description updated successfully")
        return response.json()
        
    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error updating card {card_id} description: {http_err}")
        if hasattr(http_err.response, 'text'):
            print("[TRELLO API] Response content:", http_err.response.text)
        raise
    except Exception as err:
        print(f"[TRELLO API] Other error updating card {card_id} description: {err}")
        raise


def update_trello_card_name(card_id, new_name):
    """
    Update a Trello card's name via API.
    
    Args:
        card_id (str): Trello card ID
        new_name (str): New card name
        
    Returns:
        dict: Response from Trello API, or None if update fails
    """
    url = f"https://api.trello.com/1/cards/{card_id}"
    
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "name": new_name
    }
    
    try:
        print(f"[TRELLO API] Updating name for card {card_id}")
        response = requests.put(url, params=params)
        response.raise_for_status()
        
        print(f"[TRELLO API] Card {card_id} name updated successfully")
        return response.json()
        
    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error updating card {card_id} name: {http_err}")
        if hasattr(http_err.response, 'text'):
            print("[TRELLO API] Response content:", http_err.response.text)
        raise
    except Exception as err:
        print(f"[TRELLO API] Other error updating card {card_id} name: {err}")
        raise


def get_expected_card_name(job_number, release_number, job_name, description):
    """
    Generate the expected Trello card name based on database values.
    Format: {job_number}-{release_number} {job_name} {description}
    
    Args:
        job_number: Job number (int or str)
        release_number: Release number (str)
        job_name: Job name (str, can be None/empty)
        description: Description (str, can be None/empty)
        
    Returns:
        str: Expected card name
    """
    # Handle None/empty values - use empty strings
    job_name = (job_name or "").strip()
    description = (description or "").strip()
    
    # Format: {job}-{release} {job_name} {description}
    # Build parts and join with spaces, avoiding double spaces
    parts = [f"{job_number}-{release_number}"]
    if job_name:
        parts.append(job_name)
    if description:
        parts.append(description)
    
    expected_name = " ".join(parts)
    return expected_name


def calculate_business_days_after(start_date, days):
    """
    Calculate a date that is a certain number of business days after the start date.
    
    Args:
        start_date (datetime.date): The start date
        days (int): Number of business days to add
        
    Returns:
        datetime.date: The calculated due date
    """
    from app.trello.utils import add_business_days
    return add_business_days(start_date, days)


def update_card_date_range(card_short_link, start_date, due_date):
    """
    Update a card's start and due dates.
    
    Args:
        card_short_link (str): The card's short link (from fileName)
        start_date (datetime.date): The start date
        due_date (datetime.date): The due date
        
    Returns:
        dict: Dictionary containing success status and details
    """
    try:
        # Convert dates to proper timezone-aware format for Trello
        start_date_str = mountain_start_datetime(start_date)
        due_date_str = mountain_due_datetime(due_date)
        
        url = f"https://api.trello.com/1/cards/{card_short_link}"
        
        payload = {
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
            "start": start_date_str,
            "due": due_date_str
        }
        
        print(f"[TRELLO API] Updating mirror card {card_short_link} with start: {start_date_str}, due: {due_date_str}")
        
        response = requests.put(url, params=payload)
        
        if response.status_code == 200:
            print(f"[TRELLO API] Successfully updated mirror card {card_short_link}")
            return {
                "success": True,
                "card_short_link": card_short_link,
                "start_date": start_date_str,
                "due_date": due_date_str
            }
        else:
            print(f"[TRELLO API] Error updating mirror card: {response.status_code} {response.text}")
            return {
                "success": False,
                "error": f"Trello API error: {response.status_code} {response.text}"
            }
            
    except Exception as e:
        error_msg = f"Error updating card date range: {str(e)}"
        print(f"[TRELLO API] {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }


def add_procore_link(card_id, procore_url, link_name=None):
    """
    Add a Procore link as an attachment to a Trello card.
    
    Args:
        card_id (str): Trello card ID
        procore_url (str): The Procore URL to attach
        link_name (str, optional): Custom name for the link (defaults to "Procore Link)
    
    Returns:
        dict: Dictionary containing success status and attachment data, or error message
    """
    if not procore_url or not procore_url.strip():
        print(f"[TRELLO API] Skipping empty Procore URL for card {card_id}")
        return {
            "success": False,
            "error": "Procore URL is required"
        }
    
    url = f"https://api.trello.com/1/cards/{card_id}/attachments"
    
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "url": procore_url.strip(),
        "name": "FC Drawing - Procore Link"
    }
    
    # Add optional name parameter if provided
    if link_name:
        params["name"] = link_name
    
    try:
        print(f"[TRELLO API] Adding Procore link to card {card_id}: {procore_url[:100]}...")
        response = requests.post(url, params=params)
        response.raise_for_status()
        
        attachment_data = response.json()
        print(f"[TRELLO API] Procore link added successfully (attachment ID: {attachment_data.get('id')})")
        
        return {
            "success": True,
            "card_id": card_id,
            "attachment_id": attachment_data.get("id"),
            "attachment_url": attachment_data.get("url"),
            "attachment_name": attachment_data.get("name")
        }
        
    except requests.exceptions.HTTPError as http_err:
        print(f"[TRELLO API] HTTP error adding Procore link: {http_err}")
        if hasattr(http_err.response, 'text'):
            print("[TRELLO API] Response content:", http_err.response.text)
        return {
            "success": False,
            "error": f"HTTP error: {http_err}",
            "response": http_err.response.text if hasattr(http_err.response, 'text') else None
        }
    except Exception as err:
        print(f"[TRELLO API] Error adding Procore link: {err}")
        return {
            "success": False,
            "error": str(err)
        }

########################################################
# Copy Card to Unassigned and Link
########################################################
def copy_trello_card(card_id, target_list_id, pos="bottom"):
    url = "https://api.trello.com/1/cards"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "idCardSource": card_id,
        "idList": target_list_id,
        "keepFromSource": "all",
        "pos": pos,
    }
    resp = requests.post(url, params=params)
    resp.raise_for_status()
    return resp.json()

def card_has_link_to(card_id):
    url = f"https://api.trello.com/1/cards/{card_id}/attachments"
    params = {"key": cfg.TRELLO_API_KEY, "token": cfg.TRELLO_TOKEN}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return any(att.get("name") == "Linked card" for att in resp.json())

def link_cards(primary_id, secondary_id):
    base = "https://trello.com/c/"
    for src, dst in ((primary_id, secondary_id), (secondary_id, primary_id)):
        url = f"https://api.trello.com/1/cards/{src}/attachments"
        params = {
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
            "url": f"{base}{dst}",
            "name": "Linked card",
        }
        resp = requests.post(url, params=params)
        resp.raise_for_status()
