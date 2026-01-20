"""
Shared Trello card creation functionality.

This module provides a unified interface for creating Trello cards from various sources,
with support for all features including mirror cards, FC Drawing links, Fab Order, etc.
"""

from typing import Dict, Optional, Any
from app.logging_config import get_logger
from app.config import Config as cfg
import requests
import math

logger = get_logger(__name__)


def build_card_title(job_number: int, release: str, job_name: str, description: str) -> str:
    """
    Build a standardized Trello card title.
    
    Args:
        job_number: Job number
        release: Release number
        job_name: Job name
        description: Job description
    
    Returns:
        Formatted card title
    """
    job_name = job_name or 'Unknown Job'
    description = description or 'Unknown Description'
    return f"{job_number}-{release} {job_name} {description}"


def build_card_description(
    description: Optional[str] = None,
    install_hrs: Optional[float] = None,
    paint_color: Optional[str] = None,
    pm: Optional[str] = None,
    by: Optional[str] = None,
    released: Optional[Any] = None,
    num_guys: float = 2
) -> str:
    """
    Build a standardized Trello card description.
    
    Args:
        description: Job description
        install_hrs: Installation hours
        paint_color: Paint color
        pm: Project manager
        by: Buyer
        released: Released date
        num_guys: Number of guys (default: 2)
    
    Returns:
        Formatted card description
    """
    from app.trello.api import calculate_installation_duration
    
    description_parts = []
    
    if description:
        description_parts.append(f"**Description:** {description}")
    
    if install_hrs:
        description_parts.append(f"**Install HRS:** {install_hrs}")
        description_parts.append(f"**Number of Guys:** {num_guys}")
        
        # Calculate installation duration
        installation_duration = calculate_installation_duration(install_hrs, num_guys)
        if installation_duration is not None:
            description_parts.append(f"**Installation Duration:** {installation_duration} days")
    
    if paint_color:
        description_parts.append(f"**Paint color:** {paint_color}")
    
    if pm and by:
        description_parts.append(f"**Team:** PM: {pm} / BY: {by}")
    
    if released:
        # Handle both date objects and strings
        if isinstance(released, str):
            released_str = released
        else:
            released_str = str(released)
        description_parts.append(f"**Released:** {released_str}")
    
    return "\n".join(description_parts) if description_parts else ""


def create_trello_card_core(
    card_title: str,
    card_description: str,
    list_id: str,
    position: str = "top"
) -> Dict[str, Any]:
    """
    Core function to create a Trello card.
    
    This is the shared logic for creating a card in Trello.
    All other card creation functions should use this.
    
    Args:
        card_title: Card title
        card_description: Card description
        list_id: Trello list ID to create card in
        position: Position in list ("top", "bottom", or numeric)
    
    Returns:
        Dictionary with:
            - success: bool
            - card_data: dict (if success)
            - card_id: str (if success)
            - error: str (if not success)
    """
    try:
        url = "https://api.trello.com/1/cards"
        payload = {
            "key": cfg.TRELLO_API_KEY,
            "token": cfg.TRELLO_TOKEN,
            "name": card_title,
            "desc": card_description,
            "idList": list_id,
            "pos": position
        }
        
        logger.info(f"Creating Trello card in list {list_id}")
        response = requests.post(url, params=payload)
        response.raise_for_status()
        
        card_data = response.json()
        logger.info(f"Trello card created successfully: {card_data['id']}")
        
        return {
            "success": True,
            "card_data": card_data,
            "card_id": card_data['id']
        }
        
    except Exception as err:
        error_msg = f"Error creating Trello card: {str(err)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg
        }


def apply_card_post_creation_features(
    card_id: str,
    list_id: str,
    job_record: Optional[Any] = None,
    fab_order: Optional[float] = None,
    viewer_url: Optional[str] = None,
    notes: Optional[str] = None,
    create_mirror: bool = False,
    operation_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Apply post-creation features to a Trello card.
    
    This handles:
    - Fab Order custom field and sorting
    - FC Drawing link
    - Notes as comment
    - Mirror card creation
    
    Args:
        card_id: Trello card ID
        list_id: List ID (for sorting)
        job_record: Job database record (optional, for viewer_url)
        fab_order: Fab Order value (optional)
        viewer_url: Viewer URL for FC Drawing link (optional, can come from job_record)
        notes: Notes to add as comment (optional)
        create_mirror: Whether to create mirror card (default: False)
        operation_id: Operation ID for logging (optional)
    
    Returns:
        Dictionary with results of each operation
    """
    from app.trello.api import (
        update_card_custom_field_number,
        add_procore_link,
        add_comment_to_trello_card,
        copy_trello_card,
        link_cards,
        card_has_link_to,
        update_trello_card
    )
    from app.trello.utils import sort_list_if_needed
    import pandas as pd
    
    results = {
        "fab_order_set": False,
        "fab_order_sorted": False,
        "fc_drawing_added": False,
        "notes_added": False,
        "mirror_card_id": None
    }
    
    # Get viewer_url from job_record if not provided
    if not viewer_url and job_record and hasattr(job_record, 'viewer_url'):
        viewer_url = job_record.viewer_url
    
    # If viewer_url is still missing and we have a job_record, try to fetch from Procore
    if not viewer_url and job_record and hasattr(job_record, 'job') and hasattr(job_record, 'release'):
        try:
            from app.procore.procore import get_viewer_url_for_job
            from app.models import db
            procore_result = get_viewer_url_for_job(job_record.job, job_record.release)
            if procore_result and procore_result.get("success") and procore_result.get("viewer_url"):
                viewer_url = procore_result["viewer_url"]
                # Update the job record with the viewer_url for future use
                if hasattr(job_record, 'viewer_url'):
                    job_record.viewer_url = viewer_url
                    # Commit the viewer_url update
                    try:
                        db.session.commit()
                        logger.info(f"Fetched and saved viewer_url from Procore for {job_record.job}-{job_record.release}")
                    except Exception as commit_err:
                        logger.warning(f"Failed to commit viewer_url: {commit_err}")
                        db.session.rollback()
        except Exception as procore_err:
            logger.warning(f"Failed to fetch viewer_url from Procore: {procore_err}")
    
    # Get fab_order from job_record if not provided
    if fab_order is None and job_record and hasattr(job_record, 'fab_order'):
        fab_order = job_record.fab_order
    
    # Handle Fab Order custom field
    if fab_order is not None:
        try:
            # Convert to int (round up if float)
            if isinstance(fab_order, float):
                fab_order_int = math.ceil(fab_order)
            else:
                fab_order_int = int(fab_order)
            
            if cfg.FAB_ORDER_FIELD_ID:
                fab_order_success = update_card_custom_field_number(
                    card_id,
                    cfg.FAB_ORDER_FIELD_ID,
                    fab_order_int
                )
                if fab_order_success:
                    results["fab_order_set"] = True
                    logger.info(f"Successfully set Fab Order custom field to {fab_order_int}")
                    
                    # Sort the list if it's one of the target lists
                    sort_success = sort_list_if_needed(
                        list_id,
                        cfg.FAB_ORDER_FIELD_ID,
                        operation_id,
                        "list"
                    )
                    if sort_success:
                        results["fab_order_sorted"] = True
                else:
                    logger.error(f"Failed to set Fab Order custom field")
            else:
                logger.debug("FAB_ORDER_FIELD_ID not configured, skipping Fab Order custom field")
        except (ValueError, TypeError) as e:
            logger.error(f"Could not convert Fab Order '{fab_order}' to int: {e}")
    
    # Add FC Drawing link if viewer_url exists
    if viewer_url:
        try:
            link_result = add_procore_link(card_id, viewer_url, link_name="FC Drawing")
            if link_result.get("success"):
                results["fc_drawing_added"] = True
                logger.info(f"Added FC Drawing link to card {card_id}")
            else:
                logger.warning(f"Failed to add FC Drawing link: {link_result.get('error')}")
        except Exception as link_err:
            logger.warning(f"Error adding FC Drawing link: {link_err}")
    
    # Handle notes field - append as comment if not empty
    if notes is not None:
        # Check if notes value is valid (not None, not NaN, not empty string, not 'nan'/'NaN')
        if (not pd.isna(notes) and 
            str(notes).strip() and
            str(notes).strip().lower() not in ['nan', 'none']):
            try:
                comment_success = add_comment_to_trello_card(card_id, str(notes).strip())
                if comment_success:
                    results["notes_added"] = True
                    logger.info(f"Successfully added notes as comment to Trello card")
            except Exception as comment_err:
                logger.warning(f"Error adding notes comment: {comment_err}")
    
    # Create mirror card in unassigned list if configured
    if create_mirror and cfg.UNASSIGNED_CARDS_LIST_ID:
        try:
            # Check if card already has a link (to avoid duplicates)
            if not card_has_link_to(card_id):
                logger.info(f"Creating mirror card in unassigned list for card {card_id}")
                cloned = copy_trello_card(card_id, cfg.UNASSIGNED_CARDS_LIST_ID, pos="bottom")
                mirror_card_id = cloned["id"]
                link_cards(card_id, mirror_card_id)
                # Clear due dates on both cards
                update_trello_card(card_id, clear_due_date=True)
                update_trello_card(mirror_card_id, clear_due_date=True)
                results["mirror_card_id"] = mirror_card_id
                logger.info(f"Mirror card created and linked: {mirror_card_id}")
            else:
                logger.info(f"Card {card_id} already has a link, skipping mirror card creation")
        except Exception as mirror_err:
            logger.warning(f"Failed to create mirror card: {mirror_err}")
    
    return results

