import hashlib
import json
import logging
import time
import pandas as pd
import re
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError

from app.models import SubmittalEvents, WebhookReceipt, db

# How long (seconds) to treat repeated Procore webhook deliveries as burst duplicates.
# Procore bursts arrive within ~7s. Workflow cycles happen minutes/hours apart.
WEBHOOK_DEDUP_WINDOW_SECONDS = 15

logger = logging.getLogger(__name__)

# Helper function to convert pandas NaT/NaN to None
def clean_value(value):
    if pd.isna(value):
        return None
    # If it's a pandas Timestamp, convert to Python datetime
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime() if not pd.isna(value) else None
    return value

def is_email(value):
    """Check if a string looks like an email address."""
    if not value or not isinstance(value, str):
        return False
    # Simple email pattern: contains @ and has a domain with at least one dot
    email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    return bool(re.match(email_pattern, value.strip()))

def parse_ball_in_court_from_submittal(submittal_data):
    """
    Parse the users assigned to ball_in_court and approvers from submittal webhook data.
    Handles multiple assignees by returning a comma-separated string.
    
    Args:
        submittal_data: Dict containing submittal data from Procore webhook
        
    Returns:
        dict: {
            'ball_in_court': str or None - Comma-separated list of user names/logins who have the ball in court,
                                          or single user name/login if only one person,
            'approvers': list - List of approver data from the submittal
        }
        Returns None if submittal_data is not a valid dict
    """
    if not isinstance(submittal_data, dict):
        return None
    
    # Get approvers list
    approvers = submittal_data.get("approvers", [])
    if not isinstance(approvers, list):
        approvers = []
    
    ball_in_court_users = []
    
    # First, check if ball_in_court array has entries
    ball_in_court = submittal_data.get("ball_in_court", [])
    if ball_in_court and isinstance(ball_in_court, list) and len(ball_in_court) > 0:
        # Extract user info from ALL ball_in_court entries (not just the first)
        for entry in ball_in_court:
            if isinstance(entry, dict):
                user = entry.get("user") or entry
                if user and isinstance(user, dict):
                    name = user.get("name")
                    login = user.get("login")
                    
                    # Prefer name over login, but skip if either is an email
                    if name and not is_email(name):
                        ball_in_court_users.append(name)
                    elif login and not is_email(login):
                        ball_in_court_users.append(login)
                    # If both name and login are emails or missing, skip this user
    
    # If ball_in_court is empty, derive from approvers with pending responses
    if not ball_in_court_users and approvers:
        # Find ALL approvers who need to respond (pending state)
        for approver in approvers:
            if not isinstance(approver, dict):
                continue
                
            response_required = approver.get("response_required", False)
            if not response_required:
                continue
            
            response = approver.get("response", {})
            if not isinstance(response, dict):
                continue
            
            # Check if response is pending
            response_considered = response.get("considered", "").lower()
            response_name = response.get("name", "").lower()
            
            # Consider it pending if:
            # - considered is 'pending'
            # - name is 'pending'
            # - or distributed is False (not yet sent)
            is_pending = (
                response_considered == "pending" or
                response_name == "pending" or
                not approver.get("distributed", False)
            )
            
            if is_pending:
                user = approver.get("user")
                if user and isinstance(user, dict):
                    name = user.get("name")
                    login = user.get("login")
                    
                    # Prefer name over login, but skip if either is an email
                    if name and not is_email(name) and name not in ball_in_court_users:
                        ball_in_court_users.append(name)
                    elif login and not is_email(login) and login not in ball_in_court_users:
                        ball_in_court_users.append(login)
                    # If both name and login are emails or missing, skip this user
    
    # Return comma-separated string if multiple users, single string if one, None if empty
    if not ball_in_court_users:
        ball_in_court_value = None
    elif len(ball_in_court_users) == 1:
        ball_in_court_value = ball_in_court_users[0]
    else:
        # Multiple users - join with comma and space
        ball_in_court_value = ", ".join(ball_in_court_users)
    
    return {
        "ball_in_court": ball_in_court_value,
        "approvers": approvers
    }


def extract_procore_user_id_from_webhook(payload: dict) -> Optional[str]:
    """
    Extract the Procore user ID of the actor who triggered the webhook from payload.
    Tries common field names used by Procore webhooks (v4 and others).

    Returns:
        str or None: Procore user id as string (for matching users.procore_id), or None if not found
    """
    if not isinstance(payload, dict):
        return None
    # Direct scalar fields
    for key in ("user_id", "initiator_id", "created_by", "updated_by", "actor_id"):
        val = payload.get(key)
        if val is not None:
            return str(val).strip() or None
    # Nested object: initiator or user with id
    for key in ("initiator", "user", "created_by_user", "updated_by_user"):
        obj = payload.get(key)
        if isinstance(obj, dict):
            uid = obj.get("id")
            if uid is not None:
                return str(uid).strip() or None
    return None


def resolve_internal_user_id(procore_user_id: Optional[str]) -> Optional[int]:
    """
    Resolve Procore user id to our User record. Uses users.procore_id (stored as string) for lookup.

    Returns:
        users.id if found, else None
    """
    if not procore_user_id or not str(procore_user_id).strip():
        return None
    from app.models import User
    procore_id_str = str(procore_user_id).strip()
    user = User.query.filter_by(procore_id=procore_id_str).first()
    return user.id if user else None


def resolve_webhook_user_ids(webhook_payload: Optional[dict]) -> Tuple[Optional[str], Optional[int]]:
    """
    Extract Procore user id from webhook payload and resolve to internal user id.

    Returns:
        (external_user_id, internal_user_id) - Procore user id string and users.id, or (None, None)
    """
    if not webhook_payload:
        return None, None
    external = extract_procore_user_id_from_webhook(webhook_payload)
    if not external:
        return None, None
    internal = resolve_internal_user_id(external)
    return external, internal


def is_duplicate_webhook(resource_id: int, project_id: int, event_type: str) -> bool:
    """
    Return True if this Procore webhook delivery is a burst duplicate of one already
    being processed within the current dedup window.

    On first delivery in the window: inserts a WebhookReceipt row and returns False.
    On retry deliveries: the unique constraint fires (IntegrityError), rolls back, returns True.

    receipt_hash = sha256("procore:{resource_id}:{project_id}:{event_type}:{bucket}")
    where bucket = int(unix_time // WEBHOOK_DEDUP_WINDOW_SECONDS)
    """
    bucket = int(time.time() // WEBHOOK_DEDUP_WINDOW_SECONDS)
    raw = f"procore:{resource_id}:{project_id}:{event_type}:{bucket}"
    receipt_hash = hashlib.sha256(raw.encode()).hexdigest()
    receipt = WebhookReceipt(
        receipt_hash=receipt_hash,
        provider='procore',
        resource_id=str(resource_id),
    )
    db.session.add(receipt)
    try:
        db.session.commit()
        return False
    except IntegrityError:
        db.session.rollback()
        return True


def create_submittal_payload_hash(action: str, submittal_id: str, payload: dict) -> str:
    """
    Content-based hash for the submittal event — used for auditing/debugging only.
    Deduplication is handled upstream by is_duplicate_webhook() and the row lock
    in check_and_update_submittal().
    """
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    hash_string = f"{action}:{submittal_id}:{payload_json}"
    return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()



def create_submittal_event(
    submittal_id,
    action: str,
    payload: dict,
    webhook_payload: Optional[dict] = None,
    source: str = 'Procore',
    internal_user_id: Optional[int] = None,
    is_system_echo: bool = False,
) -> bool:
    """
    Create a SubmittalEvents record with user attribution. Idempotent (skips if payload_hash exists).
    Lives in helpers to avoid circular imports (procore imports brain; brain routes need this).

    Args:
        submittal_id: Submittal ID (string)
        action: 'created' or 'updated'
        payload: Event payload dict
        webhook_payload: Raw webhook dict for resolving external_user_id / internal_user_id (Procore)
        source: Event source (default 'Procore'; use 'Brain' for app-originated updates)
        internal_user_id: Optional app user id (e.g. from get_current_user()); used when source='Brain', no webhook

    Returns:
        bool: True if event was created, False if skipped (duplicate or no payload)
    """
    if not payload and action == 'updated':
        return False
    if webhook_payload is not None:
        external_user_id, internal_user_id = resolve_webhook_user_ids(webhook_payload)
    else:
        external_user_id = None
    payload_hash = create_submittal_payload_hash(action, str(submittal_id), payload)
    event = SubmittalEvents(
        submittal_id=str(submittal_id),
        action=action,
        payload=payload,
        payload_hash=payload_hash,
        source=source,
        internal_user_id=internal_user_id,
        external_user_id=external_user_id,
        is_system_echo=is_system_echo,
    )
    db.session.add(event)
    try:
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        if "payload_hash" in str(e) or "unique" in str(e).lower() or "duplicate" in str(e).lower():
            logger.debug(
                "SubmittalEvent duplicate (payload_hash already exists) for submittal %s %s, skipping",
                submittal_id, action,
            )
            return False
        raise
    logger.info(
        "Created SubmittalEvent for submittal %s %s (external_user_id=%s, internal_user_id=%s, is_system_echo=%s)",
        submittal_id, action, external_user_id, internal_user_id, is_system_echo,
    )
    return True
