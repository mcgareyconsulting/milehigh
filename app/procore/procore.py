"""
@milehigh-header
schema_version: 1
purpose: Core Procore business logic for creating, updating, and health-checking submittals against the Procore API.
exports:
  get_project_id_by_project_name: Resolve a project name to its Procore project ID.
  create_submittal_from_webhook: Create a new Submittals DB record from a Procore webhook payload.
  check_and_update_submittal: Diff a webhook payload against the DB record and apply changes.
  comprehensive_health_scan: Full audit comparing DB submittals against Procore API state.
  get_viewer_url_for_job: Look up the FC Drawing Viewer URL for a given job/release number.
  add_procore_link_to_trello_card: Attach the Procore viewer link to the corresponding Trello card.
  get_drafting_workload: Aggregate drafting-relevant submittals across all projects.
imports_from: [requests, sqlalchemy, app.config, app.models, app.procore.procore_auth, app.procore.client, app.procore.helpers, app.brain.drafting_work_load.service]
imported_by: [app/procore/__init__.py, app/sync/sync.py, app/trello/card_creation.py, app/trello/sync.py, app/admin/__init__.py, app/__init__.py, app/procore/scripts/sync_submittals.py]
invariants:
  - check_and_update_submittal uses a row-level lock (with_for_update) to prevent concurrent webhook races.
  - Submittal events are recorded via helpers.create_submittal_event to maintain the audit trail.
  - Connector-originated updates are tagged with is_system_echo=True in submittal events.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
import re
import json
import os
import hashlib
import requests
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from requests.exceptions import ConnectionError, Timeout
from urllib3.exceptions import ProtocolError
from app.config import Config as cfg
from app.logging_config import get_logger
from app.models import db, Releases, Submittals
from app.trello.api import add_procore_link
from app.procore.procore_auth import get_access_token
from app.procore.client import get_procore_client
from app.procore.helpers import (
    parse_ball_in_court_from_submittal,
    extract_procore_user_id_from_webhook,
    resolve_internal_user_id,
    resolve_webhook_user_ids,
    create_submittal_event as _create_submittal_event,
)
from app.brain.drafting_work_load.service import UrgencyService, SubmittalOrderingService
from app.brain.drafting_work_load.engine import SubmittalOrderingEngine
from app.api.helpers import active_releases_filter


logger = get_logger(__name__)

# Submittal type that triggers a "Rel" (release) number assignment on the DWL tab.
DRR_TYPE = "Drafting Release Review"
# Rel numbers cycle through this inclusive range, rolling over to REL_MIN once
# REL_MAX is occupied.
REL_MIN = 101
REL_MAX = 998


def _to_int_or_none(value):
    """Coerce ``value`` to int, or return None if it isn't a clean integer."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


class RelAssignmentError(Exception):
    """Raised when a manual Rel assignment is invalid.

    ``code`` is one of 'type' (submittal isn't a DRR), 'range' (not an integer
    in [REL_MIN, REL_MAX]), or 'collision' (number already taken).
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _globally_taken_rel_numbers(exclude_submittal_id=None):
    """Rel numbers that are unavailable system-wide, keyed on the value alone.

    Uniqueness is locked on the 3-digit Rel value (job-agnostic). A number is
    taken if it appears in the union of two sources:

    (a) Active release #s -- every ACTIVE job-log ``Releases`` row, any job
        (``active_releases_filter``: not archived; ``is_active`` True or NULL).
    (b) Pending DRR release #s -- DRR submittals that hold a ``rel`` but haven't
        become a release yet (status not 'Closed'), excluding the submittal being
        edited (``exclude_submittal_id``).

    A Closed DRR is on its way to being an active release that (a) catches, so it
    is intentionally not reserved here -- otherwise every historical Closed DRR
    would hold its number forever and exhaust the 101..998 range. Values that
    aren't clean integers are ignored. Returns the set of taken integers.
    """
    taken = set()

    release_rows = (
        db.session.query(Releases.release)
        .filter(active_releases_filter())
        .all()
    )
    for (value,) in release_rows:
        number = _to_int_or_none(value)
        if number is not None:
            taken.add(number)

    drr_filters = [
        Submittals.type == DRR_TYPE,
        Submittals.rel.isnot(None),
        or_(Submittals.status.is_(None), Submittals.status != "Closed"),
    ]
    if exclude_submittal_id is not None:
        drr_filters.append(Submittals.submittal_id != str(exclude_submittal_id))
    drr_rows = (
        db.session.query(Submittals.rel)
        .filter(*drr_filters)
        .all()
    )
    for (value,) in drr_rows:
        number = _to_int_or_none(value)
        if number is not None:
            taken.add(number)

    return taken


def next_rel_number(exclude_submittal_id=None):
    """Return the suggested next Rel number (used to prefill the manual popup).

    Assignment is "semi-chronological": the sequence climbs to the next highest
    available value rather than back-filling gaps. The suggestion is
    ``max(currently-taken) + 1``, so a run like 650, 651, 652 keeps advancing
    even when intermediate numbers are blocked -- if 653 is taken the max is
    >= 653 and the next suggestion is 654, never a low/freed number like 101.
    (Nothing above the max is taken, so ``max + 1`` is always free.)

    Freed numbers -- archived releases and never-used gaps below the max -- are
    NOT reused until the sequence rolls over. Rollover happens only once REL_MAX
    is occupied: the suggestion then drops to the lowest free value from REL_MIN
    up, recycling the freed low numbers.

    "Taken" is the union in ``_globally_taken_rel_numbers``.
    ``exclude_submittal_id`` lets the submittal being edited ignore its own
    current Rel. Returns REL_MIN when nothing is taken. Raises RuntimeError only
    in the pathological case where every number in [REL_MIN, REL_MAX] is taken.
    """
    taken = _globally_taken_rel_numbers(exclude_submittal_id)
    in_range = [n for n in taken if REL_MIN <= n <= REL_MAX]
    if not in_range:
        return REL_MIN

    current_max = max(in_range)
    if current_max < REL_MAX:
        # Nothing above current_max is taken, so current_max + 1 is free.
        return current_max + 1

    # REL_MAX is occupied -> roll over and recycle the lowest free number.
    for candidate in range(REL_MIN, REL_MAX + 1):
        if candidate not in taken:
            return candidate

    raise RuntimeError(
        f"No free Rel number in [{REL_MIN}, {REL_MAX}]: every value is taken "
        f"by an active release or pending DRR."
    )


def assign_rel_manual(submittal, desired_rel):
    """Validate and assign a manually-entered Rel to a DRR submittal.

    Raises ``RelAssignmentError`` (code 'type' | 'range' | 'collision') on
    failure and leaves the submittal untouched. On success sets ``rel`` and
    ``rel_assigned_at`` and returns the assigned integer. The caller commits.
    Reassignment is allowed: the submittal's own current Rel is excluded from
    the collision check.
    """
    if submittal is None or (submittal.type or "").strip() != DRR_TYPE:
        raise RelAssignmentError(
            "type", "Rel can only be assigned to a Drafting Release Review submittal."
        )
    number = _to_int_or_none(desired_rel)
    if number is None or not (REL_MIN <= number <= REL_MAX):
        raise RelAssignmentError(
            "range", f"Rel must be a whole number from {REL_MIN} to {REL_MAX}."
        )
    taken = _globally_taken_rel_numbers(exclude_submittal_id=submittal.submittal_id)
    if number in taken:
        raise RelAssignmentError(
            "collision",
            f"Rel {number} is already assigned to an active release or pending DRR.",
        )
    submittal.rel = number
    submittal.rel_assigned_at = datetime.utcnow()
    logger.info(
        "rel_assigned",
        release=number,
        submittal_id=submittal.submittal_id,
        job=submittal.project_number,
    )
    return number


def _request_json(url, headers, params=None):
    """
    Wrapper around requests.get that adds logging and error handling.
    Returns JSON data or None if the request fails.
    """
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error(
            "procore_request_failed",
            url=url,
            params=params,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return None

    try:
        data = response.json()
    except ValueError:
        logger.error("procore_response_not_json", url=url, params=params, exc_info=True)
        return None

    if isinstance(data, dict) and data.get("errors"):
        logger.error("procore_response_errors", url=url, params=params, errors=data.get("errors"))
        return None

    return data


def _normalize_title(value):
    if not value:
        return ""
    normalized = re.sub(r"\s*-\s*", "-", value.strip().lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _identifier_matches(normalized_identifier, normalized_title):
    """Check if identifier appears in title with word boundaries (tight match).

    Uses lookaround assertions so that '123-456' does not falsely match
    inside '1123-4567'.  Supports both xxx-yyy and xxx-Vyyy patterns.
    """
    pattern = r'(?<![a-z0-9])' + re.escape(normalized_identifier) + r'(?![a-z0-9])'
    return bool(re.search(pattern, normalized_title))


# Get Companies List
def get_companies_list():
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.0/companies"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    companies = _request_json(url, headers=headers) or []
    if not companies:
        logger.warning("procore_companies_empty")
        return None
    company_id = companies[0]["id"]
    return company_id


# Get Projects by Company ID
def get_projects_by_company_id(company_id, project_number):
    '''
    Get projects by company ID and project number
    '''
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects?company_id={company_id}"
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Procore-Company-Id": str(company_id),
    }
    projects = _request_json(url, headers=headers) or []
    for project in projects:
        if project["project_number"] == str(project_number):
            return project["id"]
    return None


def fetch_all_projects(company_id):
    """Fetch every Procore project in one call. Returns {project_number_str: project_id}."""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects?company_id={company_id}"
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Procore-Company-Id": str(company_id),
    }
    projects = _request_json(url, headers=headers) or []
    return {p["project_number"]: p["id"] for p in projects}


def fetch_all_submittals(project_id):
    """Fetch every submittal for a project in one call (unfiltered)."""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects/{project_id}/submittals"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    result = _request_json(url, headers=headers)
    return result if isinstance(result, list) else []


def submittals_for_release(all_submittals, job, release):
    """Filter a pre-fetched submittal list to the FC submittals matching one (job, release)."""
    identifier = f"{job}-{release}".strip().lower()
    return [
        s for s in all_submittals
        if _identifier_matches(identifier, _normalize_title(s.get("title", "")))
        and (s.get("type") or {}).get("name") == "For Construction"
    ]

# Function to get project id by project name
def get_project_id_by_project_name(project_name):
    # get procore client
    procore = get_procore_client()
    projects = procore.get_projects(cfg.PROD_PROCORE_COMPANY_ID)
    logger.debug("projects_fetched", count=len(projects))
    for project in projects:
        if project["name"] == project_name:
            logger.debug(
                "project_matched",
                project_id=project["id"],
                project_number=project["project_number"],
                project_name=project["name"],
            )
            return project["id"]
    return None

def parse_and_log_submittal_data(submittal_data: dict, project_id: int, submittal_id: int, source: str = "webhook"):
    """
    Parse submittal data into a clean, structured format and log it for easy visualization.
    
    Args:
        submittal_data: Raw submittal data from Procore API
        project_id: Procore project ID
        submittal_id: Procore submittal ID
        source: Source of the data (e.g., "webhook", "api")
    
    Returns:
        dict: Parsed submittal data in a structured format
    """
    if not isinstance(submittal_data, dict):
        logger.warning(
            "submittal_data_not_dict",
            submittal_id=submittal_id,
            project_id=project_id,
            data_type=type(submittal_data).__name__,
        )
        return None
    
    # Extract key fields in a structured way
    parsed = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "project_id": project_id,
        "submittal_id": submittal_id,
        "summary": {},
        "fields": {},
        "nested_objects": {},
        "raw_data_keys": list(submittal_data.keys()) if isinstance(submittal_data, dict) else []
    }
    
    # Extract common fields
    def extract_value(obj, default=None):
        """Extract value from object (handles dict, string, or None)"""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get("name") or obj.get("id") or obj.get("login") or str(obj)
        if isinstance(obj, str):
            return obj.strip() if obj.strip() else default
        return str(obj) if obj else default
    
    # Summary fields (most important)
    parsed["summary"] = {
        "title": submittal_data.get("title"),
        "status": extract_value(submittal_data.get("status")),
        "type": extract_value(submittal_data.get("type")),
        "ball_in_court": extract_value(submittal_data.get("ball_in_court")),
        "submittal_manager": extract_value(submittal_data.get("submittal_manager") or submittal_data.get("manager")),
        "specification_section": extract_value(submittal_data.get("specification_section")),
        "created_at": submittal_data.get("created_at"),
        "updated_at": submittal_data.get("updated_at"),
    }
    
    # Parse ball_in_court using existing helper
    ball_parsed = parse_ball_in_court_from_submittal(submittal_data)
    if ball_parsed:
        parsed["summary"]["ball_in_court_parsed"] = ball_parsed.get("ball_in_court")
        parsed["summary"]["ball_in_court_details"] = ball_parsed
    
    # Extract all top-level fields
    for key, value in submittal_data.items():
        if key in ["status", "type", "ball_in_court", "submittal_manager", "manager", "specification_section"]:
            # Already in summary, skip
            continue
        
        if isinstance(value, (str, int, float, bool, type(None))):
            parsed["fields"][key] = value
        elif isinstance(value, dict):
            # Store nested objects separately
            parsed["nested_objects"][key] = {
                "type": "object",
                "keys": list(value.keys()) if isinstance(value, dict) else [],
                "sample": {k: v for k, v in list(value.items())[:5]}  # First 5 items
            }
        elif isinstance(value, list):
            parsed["nested_objects"][key] = {
                "type": "array",
                "length": len(value),
                "item_type": type(value[0]).__name__ if len(value) > 0 else "empty",
                "sample": value[0] if len(value) > 0 and isinstance(value[0], (str, int, float, bool)) else None
            }

    return parsed


# Get Submittal by ID
def get_submittal_by_id(project_id, submittal_id):
    procore = get_procore_client()
    submittal = procore.get_submittal_by_id(project_id, submittal_id)
    return submittal

# Get Submittals by Project ID and Identifier
def get_submittals_by_project_id(project_id, identifier):
    """Get submittals by project ID and identifier"""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects/{project_id}/submittals"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    submittals = _request_json(url, headers=headers)
    if not isinstance(submittals, list):
        logger.warning(
            "submittals_payload_unexpected",
            project_id=project_id,
            identifier=identifier,
            payload_type=type(submittals).__name__,
        )
        return []
    normalized_identifier = (identifier or "").strip().lower()
    return [
        s for s in submittals
        if _identifier_matches(normalized_identifier, _normalize_title(s.get("title", "")))
        and s.get("type", {}).get("name") == "For Construction"
    ]


# Get Workflow Data by Project ID and Submittal ID
def get_workflow_data(project_id, submittal_id):
    """Fetch workflow data for a given submittal"""
    url = f"{cfg.PROD_PROCORE_BASE_URL}/rest/v1.1/projects/{project_id}/submittals/{submittal_id}/workflow_data"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    workflow_data = _request_json(url, headers=headers)
    if workflow_data is None:
        logger.debug("workflow_data_missing", project_id=project_id, submittal_id=submittal_id)
        return {}
    return workflow_data


# Get Final PDF Viewers by Project ID and Submittals
def get_final_pdf_viewers(project_id, submittals):
    """Extract viewer URLs for 'Final PDF Pack' responses"""
    final_results = []

    for sub in submittals:
        submittal_id = sub["id"]
        title = sub.get("title")

        # Step 1: Find response name "Final PDF Pack"
        responses = sub.get("last_distributed_submittal", {}).get("distributed_responses", [])
        approver_ids = [
            r.get("submittal_approver_id")
            for r in responses if r.get("response_name") == "Final PDF Pack"
        ]
        if not approver_ids:
            continue

        # Step 2: Get workflow data
        workflow_data = get_workflow_data(project_id, submittal_id)

        # Step 3: Match approver_id → attachment → viewer_url
        attachments = workflow_data.get("attachments") if isinstance(workflow_data, dict) else []
        for att in attachments or []:
            if att.get("approver_id") in approver_ids:
                viewer_url = att.get("viewer_url")
                if viewer_url:
                    full_viewer_url = f"https://app.procore.com{viewer_url}"
                    final_results.append({
                        "title": title,
                        "submittal_id": submittal_id,
                        "approver_id": att.get("approver_id"),
                        "filename": att.get("name"),
                        "viewer_url": full_viewer_url,
                    })

    return final_results

def get_webhook_deliveries(company_id, project_id):
    procore = get_procore_client()

    # get webhook_id based on project_id assuming 1 hook
    webhooks = procore.list_project_webhooks(project_id, 'mile-high-metal-works')
    if not webhooks:
        logger.warning("project_webhooks_missing", project_id=project_id)
        return None
    webhook_id = webhooks[0]["id"]
    if not webhook_id:
        logger.warning("project_webhook_id_missing", project_id=project_id)
        return None
    return procore.get_deliveries(company_id, project_id, webhook_id)


def handle_submittal_update(project_id, submittal_id):
    """
    Compare ball_in_court, status, title, and submittal_manager from submittal webhook data against DB record.
    
    Args:
        project_id: The Procore project ID
        submittal_id: The submittal ID (resource_id from webhook)
        
    Returns:
        tuple: (procore_submittal, ball_in_court, approvers, status, title, submittal_manager) or None if parsing fails
        - procore_submittal: Submittals DB record or None if not found
        - ball_in_court: str or None - User who has the ball in court
        - approvers: list - List of approver data
        - status: str or None - Status of the submittal from Procore
        - title: str or None - Title of the submittal from Procore
        - submittal_manager: str or None - Submittal manager from Procore
    """
    # Collect submittal data and pass to parser function
    submittal = get_submittal_by_id(project_id, submittal_id)
    if not isinstance(submittal, dict):
        return None
    
    # Parse and log submittal data for visualization
    try:
        parse_and_log_submittal_data(submittal, project_id, submittal_id, source="webhook_update")
    except Exception as parse_error:
        logger.warning(
            "submittal_parse_log_failed",
            submittal_id=submittal_id,
            project_id=project_id,
            error=str(parse_error),
            error_type=type(parse_error).__name__,
            exc_info=True,
        )
    
    parsed = parse_ball_in_court_from_submittal(submittal)
    if parsed is None:
        return None
    
    ball_in_court = parsed.get("ball_in_court")
    approvers = parsed.get("approvers", [])
    
    # Extract status from submittal data
    # Status might be a string or nested in a dict with 'name' key
    status_obj = submittal.get("status")
    if isinstance(status_obj, dict):
        status = status_obj.get("name")
    elif isinstance(status_obj, str):
        status = status_obj
    else:
        status = None
    
    # Normalize status to string or None
    status = str(status).strip() if status else None
    
    # Extract title
    title = submittal.get("title")
    title = str(title).strip() if title else None
    
    # Extract submittal_manager (if available)
    submittal_manager_obj = submittal.get("submittal_manager") or submittal.get("manager")
    if isinstance(submittal_manager_obj, dict):
        submittal_manager = submittal_manager_obj.get("name") or submittal_manager_obj.get("login")
    elif isinstance(submittal_manager_obj, str):
        submittal_manager = submittal_manager_obj
    else:
        submittal_manager = None
    submittal_manager = str(submittal_manager).strip() if submittal_manager else None
    
    # Look up the DB record
    procore_submittal = Submittals.query.filter_by(submittal_id=str(submittal_id)).first()
    
    # Always return a tuple, even if procore_submittal is None
    return procore_submittal, ball_in_court, approvers, status, title, submittal_manager


def get_project_info(project_id):
    """
    Get project information (name and number) by project ID.
    
    Args:
        project_id: Procore project ID
        
    Returns:
        dict with 'name' and 'project_number' keys, or None if not found
    """
    try:
        procore = get_procore_client()
        projects = procore.get_projects(cfg.PROD_PROCORE_COMPANY_ID)
        for project in projects:
            if project.get("id") == project_id:
                return {
                    "name": project.get("name"),
                    "project_number": project.get("project_number")
                }
        logger.debug("project_not_found", project_id=project_id)
        return None
    except Exception as e:
        logger.error(
            "project_info_fetch_failed",
            project_id=project_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return None


def create_submittal_from_webhook(project_id, submittal_id, webhook_payload=None, source='Procore'):
    """
    Create a new Submittals record in the database from a webhook create event.
    
    Args:
        project_id: Procore project ID
        submittal_id: Procore submittal ID (resource_id from webhook)
        webhook_payload: Raw webhook payload dict (for extracting user who triggered the event)
        
    Returns:
        tuple: (created: bool, record: Submittals or None, error_message: str or None)
    """
    try:
        logger.debug("submittal_create_started", submittal_id=submittal_id, project_id=project_id)

        # Check if submittal already exists
        existing = Submittals.query.filter_by(submittal_id=str(submittal_id)).first()
        if existing:
            logger.debug("submittal_create_skipped", submittal_id=submittal_id, reason="already_exists")
            return False, existing, None

        logger.debug("submittal_fetch_started", submittal_id=submittal_id, project_id=project_id)
        # Get submittal data from Procore API
        submittal_data = get_submittal_by_id(project_id, submittal_id)
        if not isinstance(submittal_data, dict):
            error_msg = f"Failed to fetch submittal data from Procore API - got {type(submittal_data)} instead of dict"
            logger.error(
                "submittal_fetch_failed",
                submittal_id=submittal_id,
                project_id=project_id,
                error=error_msg,
            )
            return False, None, error_msg

        # Parse and log submittal data for visualization
        try:
            parse_and_log_submittal_data(submittal_data, project_id, submittal_id, source="webhook_create")
        except Exception as parse_error:
            logger.warning(
                "submittal_parse_log_failed",
                submittal_id=submittal_id,
                project_id=project_id,
                error=str(parse_error),
                error_type=type(parse_error).__name__,
                exc_info=True,
            )

        logger.debug("project_info_fetch_started", project_id=project_id)
        # Get project information
        project_info = get_project_info(project_id)
        if not project_info:
            error_msg = f"Failed to fetch project info for project {project_id}"
            logger.error("project_info_fetch_failed", project_id=project_id, submittal_id=submittal_id)
            return False, None, error_msg

        logger.debug(
            "project_info_fetched",
            project_name=project_info.get("name"),
            project_number=project_info.get("project_number"),
        )
        
        # Parse ball_in_court from submittal data
        parsed = parse_ball_in_court_from_submittal(submittal_data)
        ball_in_court = parsed.get("ball_in_court") if parsed else None
        
        # Extract status
        status_obj = submittal_data.get("status")
        if isinstance(status_obj, dict):
            status = status_obj.get("name")
        elif isinstance(status_obj, str):
            status = status_obj
        else:
            status = None
        status = str(status).strip() if status else None
        
        # Extract type
        type_obj = submittal_data.get("type")
        if isinstance(type_obj, dict):
            submittal_type = type_obj.get("name")
        elif isinstance(type_obj, str):
            submittal_type = type_obj
        else:
            submittal_type = None
        submittal_type = str(submittal_type).strip() if submittal_type else None
        
        # Extract title
        title = submittal_data.get("title")
        title = str(title).strip() if title else None
        
        # Extract submittal_manager (if available)
        submittal_manager_obj = submittal_data.get("submittal_manager") or submittal_data.get("manager")
        if isinstance(submittal_manager_obj, dict):
            submittal_manager = submittal_manager_obj.get("name") or submittal_manager_obj.get("login")
        elif isinstance(submittal_manager_obj, str):
            submittal_manager = submittal_manager_obj
        else:
            submittal_manager = None
        submittal_manager = str(submittal_manager).strip() if submittal_manager else None
        
        logger.debug("submittal_record_creating", submittal_id=submittal_id, title=title)

        # Extract created_at from Procore API if available
        procore_created_at = None
        created_at_str = submittal_data.get("created_at")
        logger.debug("created_at_extracted", submittal_id=submittal_id, created_at=created_at_str)
        if created_at_str:
            try:
                # Parse ISO format timestamp (handles Z suffix and timezone offsets)
                procore_created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                # Convert to naive datetime (remove timezone info)
                if procore_created_at.tzinfo:
                    procore_created_at = procore_created_at.replace(tzinfo=None)
                logger.debug("created_at_parsed", submittal_id=submittal_id, created_at=str(procore_created_at))
            except (ValueError, AttributeError) as e:
                logger.warning(
                    "created_at_parse_failed",
                    submittal_id=submittal_id,
                    created_at=created_at_str,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                )
                procore_created_at = None

        # Fallback to current time if not available from API
        if not procore_created_at:
            logger.debug("created_at_fallback_used", submittal_id=submittal_id)
            procore_created_at = datetime.utcnow()
        
        # Double-check it doesn't exist (race condition protection)
        # Another thread/request might have created it between our initial check and now
        existing_check = Submittals.query.filter_by(submittal_id=str(submittal_id)).first()
        if existing_check:
            logger.debug("submittal_create_skipped", submittal_id=submittal_id, reason="concurrent_create")
            return False, existing_check, None
        
        # Create new Submittals record
        new_submittal = Submittals(
            submittal_id=str(submittal_id),
            procore_project_id=str(project_id),
            project_number=str(project_info.get("project_number", "")).strip() or None,
            project_name=project_info.get("name"),
            title=title,
            status=status,
            type=submittal_type,
            ball_in_court=str(ball_in_court).strip() if ball_in_court else None,
            submittal_manager=submittal_manager,
            # submittal_drafting_status uses model default of '' (empty string)
            created_at=procore_created_at,
            last_updated=datetime.utcnow()
        )
        
        # Rel (release) numbers are no longer assigned automatically on creation.
        # A drafter/admin assigns one manually from the DWL submittal popup
        # (assign_rel_manual), so a freshly-created DRR arrives with rel=None.

        db.session.add(new_submittal)
        logger.debug("submittal_commit_started", submittal_id=submittal_id)

        try:
            db.session.commit()
            logger.debug("submittal_committed", submittal_id=submittal_id)
        except IntegrityError as integrity_error:
            # Handle unique constraint violations (if another thread created it during commit)
            logger.warning(
                "submittal_commit_conflict",
                submittal_id=submittal_id,
                error=str(integrity_error),
                error_type=type(integrity_error).__name__,
                exc_info=True,
            )
            db.session.rollback()
            # Fetch the record that was created by the other process
            existing_after_error = Submittals.query.filter_by(submittal_id=str(submittal_id)).first()
            if existing_after_error:
                logger.debug("submittal_existing_returned", submittal_id=submittal_id)
                return False, existing_after_error, None
            else:
                # Unexpected: constraint violation but no record found
                error_msg = f"Unique constraint violation but no existing record found: {integrity_error}"
                logger.error(
                    "submittal_commit_conflict_unresolved",
                    submittal_id=submittal_id,
                    error=str(integrity_error),
                    error_type=type(integrity_error).__name__,
                    exc_info=True,
                )
                return False, None, error_msg
        except Exception as commit_error:
            # Re-raise other commit errors after logging
            logger.error(
                "submittal_commit_failed",
                submittal_id=submittal_id,
                error=str(commit_error),
                error_type=type(commit_error).__name__,
                exc_info=True,
            )
            raise
        
        # Create submittal event for creation (with user attribution from webhook)
        try:
            event_payload = {
                "submittal_id": str(submittal_id),
                "project_id": str(project_id),
                "title": title,
                "status": status,
                "type": submittal_type,
                "ball_in_court": str(ball_in_court).strip() if ball_in_court else None,
                "submittal_manager": submittal_manager,
                "project_name": project_info.get("name"),
                "project_number": str(project_info.get("project_number", "")).strip() or None
            }
            _create_submittal_event(
                str(submittal_id), "created", event_payload,
                webhook_payload=webhook_payload, source=source,
            )
        except Exception as event_error:
            logger.warning(
                "submittal_event_create_failed",
                submittal_id=submittal_id,
                action="created",
                error=str(event_error),
                error_type=type(event_error).__name__,
                exc_info=True,
            )

        logger.info(
            "submittal_created",
            submittal_id=submittal_id,
            project_id=project_id,
            title=title,
            source=source,
        )

        return True, new_submittal, None

    except (ConnectionError, ProtocolError, Timeout) as e:
        # Connection errors - classify and provide better error message
        # Note: The API client already retries these, so if we get here, all retries failed
        error_type = type(e).__name__
        error_msg = (
            f"Connection error while creating submittal {submittal_id}: {error_type} - {str(e)}. "
            f"This may be a temporary network issue. The webhook will be retried on the next update event."
        )
        logger.error(
            "submittal_create_failed",
            submittal_id=submittal_id,
            project_id=project_id,
            error=str(e),
            error_type=error_type,
            exc_info=True,
        )
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.error(
                "db_rollback_failed",
                submittal_id=submittal_id,
                error=str(rollback_error),
                error_type=type(rollback_error).__name__,
                exc_info=True,
            )
        return False, None, error_msg
    except Exception as e:
        # Other errors - classify and log
        error_type = type(e).__name__
        error_msg = f"Error creating submittal {submittal_id} from webhook: {error_type} - {str(e)}"
        logger.error(
            "submittal_create_failed",
            submittal_id=submittal_id,
            project_id=project_id,
            error=str(e),
            error_type=error_type,
            exc_info=True,
        )
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.error(
                "db_rollback_failed",
                submittal_id=submittal_id,
                error=str(rollback_error),
                error_type=type(rollback_error).__name__,
                exc_info=True,
            )
        return False, None, error_msg


def check_and_update_submittal(project_id, submittal_id, webhook_payload=None, source='Procore'):
    """
    Check if ball_in_court, status, title, and submittal_manager from Procore differ from DB, update if needed.

    Args:
        project_id: Procore project ID
        submittal_id: Procore submittal ID
        webhook_payload: Raw webhook payload dict (for extracting user who triggered the event)
        source: Event source string — 'Procore' for real user changes, 'Connector' for
                bounce-backs from the connector service account. 'Connector' events are
                still processed (to catch Procore side-effect changes like auto-ball_in_court)
                but are tagged for filtering in the UI.

    Returns:
        tuple: (ball_updated: bool, status_updated: bool, title_updated: bool, manager_updated: bool,
                record: Submittals or None, ball_in_court: str or None, status: str or None)
    """
    try:
        result = handle_submittal_update(project_id, submittal_id)
        if result is None:
            logger.warning("submittal_parse_failed", submittal_id=submittal_id, project_id=project_id)
            return False, False, False, False, None, None, None
        
        _, ball_in_court, approvers, status, title, submittal_manager = result

        # Re-fetch with a row-level lock so concurrent webhook deliveries serialize here
        # rather than both detecting the same mismatch and writing duplicate events.
        record = Submittals.query.filter_by(
            submittal_id=str(submittal_id)
        ).with_for_update().first()

        if not record:
            logger.warning("submittal_record_missing", submittal_id=submittal_id)
            return False, False, False, False, None, ball_in_court, status

        ball_updated = False
        status_updated = False
        title_updated = False
        manager_updated = False
        order_bumped = False
        
        # Check and update ball_in_court
        db_ball_value = record.ball_in_court if record.ball_in_court is not None else ""
        webhook_ball_value = ball_in_court if ball_in_court is not None else ""
        
        if db_ball_value != webhook_ball_value:
            logger.debug(
                "ball_in_court_mismatch",
                submittal_id=submittal_id,
                old=record.ball_in_court,
                new=ball_in_court,
            )

            # Compress the old drafter's list if the old value is a single drafter (not empty, not multiple)
            if db_ball_value and ',' not in db_ball_value:
                logger.debug("drafter_orders_compressing", drafter=db_ball_value, submittal_id=submittal_id)
                
                # Get all submittals for the old ball_in_court (excluding the one being moved)
                old_drafter_submittals = Submittals.query.filter(
                    Submittals.ball_in_court == db_ball_value,
                    Submittals.submittal_id != str(submittal_id),
                    Submittals.status == 'Open'
                ).all()
                
                if old_drafter_submittals:
                    # Convert to dict format for compression
                    submittals_data = [
                        {
                            'submittal_id': s.submittal_id,
                            'order_number': s.order_number
                        }
                        for s in old_drafter_submittals
                    ]
                    
                    # Compress both urgency and regular subsets
                    compression_updates = SubmittalOrderingEngine.compress_orders(submittals_data)
                    
                    # Apply compression updates
                    if compression_updates:
                        submittal_map = {s.submittal_id: s for s in old_drafter_submittals}
                        for submittal_id, new_order in compression_updates:
                            if submittal_id in submittal_map:
                                submittal_map[submittal_id].order_number = new_order
                                logger.info(
                                    "submittal_order_compressed",
                                    submittal_id=submittal_id,
                                    order_number=new_order,
                                    drafter=db_ball_value,
                                )
            
            # Check if new value is multiple assignees (comma-separated)
            is_new_multiple = webhook_ball_value and ',' in webhook_ball_value
            
            # Update the flag: set to True if new value is multiple assignees
            if is_new_multiple:
                record.was_multiple_assignees = True
            elif record.was_multiple_assignees and not is_new_multiple:
                # Was multiple, now single - this is the bounce-back scenario
                if UrgencyService.bump_order_number_to_urgent(record, submittal_id, webhook_ball_value):
                    order_bumped = True
                
                # Reset the flag after handling bounce-back
                record.was_multiple_assignees = False
            
            record.ball_in_court = ball_in_court
            ball_updated = True
        
        # Check if submitter appears as pending in a later workflow group (triggers order bump)
        submitter_pending = (
            UrgencyService.check_submitter_pending_in_workflow(approvers)
            if approvers else False
        )
        logger.debug(
            "submitter_pending_checked",
            submittal_id=submittal_id,
            submitter_pending=submitter_pending,
            has_approvers=bool(approvers),
        )
        if submitter_pending:
            # Only bump if order_number is an integer >= 1 (not already a decimal)
            if record.order_number is not None:
                current_order = record.order_number
                is_integer = isinstance(current_order, (int, float)) and current_order >= 1 and current_order == int(current_order)
                if is_integer:
                    ball_in_court_for_bump = record.ball_in_court if ball_updated else (ball_in_court or "")
                    if UrgencyService.bump_order_number_to_urgent(record, submittal_id, ball_in_court_for_bump):
                        order_bumped = True
                        logger.debug(
                            "submittal_order_bump_triggered",
                            submittal_id=submittal_id,
                            reason="submitter_pending_in_workflow",
                        )
        
        # Check and update status
        db_status_value = record.status if record.status is not None else ""
        webhook_status_value = status if status is not None else ""
        
        if db_status_value != webhook_status_value:
            logger.debug(
                "submittal_status_mismatch",
                submittal_id=submittal_id,
                old=record.status,
                new=status,
            )
            record.status = status
            status_updated = True
            if status != 'Open' and record.order_number is not None:
                record.order_number = None
                logger.info("submittal_order_cleared", submittal_id=submittal_id, status=status)
        
        # Check and update title
        db_title_value = record.title if record.title is not None else ""
        webhook_title_value = title if title is not None else ""
        
        if db_title_value != webhook_title_value:
            logger.debug(
                "submittal_title_mismatch",
                submittal_id=submittal_id,
                old=record.title,
                new=title,
            )
            record.title = title
            title_updated = True
        
        # Check and update submittal_manager
        db_manager_value = record.submittal_manager if record.submittal_manager is not None else ""
        webhook_manager_value = submittal_manager if submittal_manager is not None else ""
        
        if db_manager_value != webhook_manager_value:
            logger.debug(
                "submittal_manager_mismatch",
                submittal_id=submittal_id,
                old=record.submittal_manager,
                new=submittal_manager,
            )
            record.submittal_manager = submittal_manager
            manager_updated = True
        
        # Update timestamp and commit if any changes
        if ball_updated or status_updated or title_updated or manager_updated or order_bumped:
            record.last_updated = datetime.utcnow()
            db.session.commit()
            
            # Create submittal event for update
            try:
                action = "updated"
                payload = {}
                
                if ball_updated:
                    payload["ball_in_court"] = {
                        "old": db_ball_value,
                        "new": ball_in_court
                    }
                
                if status_updated:
                    payload["status"] = {
                        "old": db_status_value,
                        "new": status
                    }
                
                if title_updated:
                    payload["title"] = {
                        "old": db_title_value,
                        "new": title
                    }
                
                if manager_updated:
                    payload["submittal_manager"] = {
                        "old": db_manager_value,
                        "new": submittal_manager
                    }
                
                if order_bumped:
                    payload["order_bumped"] = True
                    payload["order_number"] = record.order_number
                
                if payload:
                    try:
                        _create_submittal_event(
                            str(submittal_id), action, payload,
                            webhook_payload=webhook_payload, source=source,
                        )
                    except Exception as event_error:
                        logger.warning(
                            "submittal_event_create_failed",
                            submittal_id=submittal_id,
                            action="updated",
                            error=str(event_error),
                            error_type=type(event_error).__name__,
                            exc_info=True,
                        )
            except Exception as event_error:
                logger.warning(
                    "submittal_event_build_failed",
                    submittal_id=submittal_id,
                    action="updated",
                    error=str(event_error),
                    error_type=type(event_error).__name__,
                    exc_info=True,
                )

            if ball_updated:
                logger.info(
                    "ball_in_court_updated",
                    submittal_id=submittal_id,
                    old=db_ball_value,
                    new=ball_in_court,
                )
            if status_updated:
                logger.info(
                    "submittal_status_updated",
                    submittal_id=submittal_id,
                    old=db_status_value,
                    new=status,
                )
            if title_updated:
                logger.info(
                    "submittal_title_updated",
                    submittal_id=submittal_id,
                    old=db_title_value,
                    new=title,
                )
            if manager_updated:
                logger.info(
                    "submittal_manager_updated",
                    submittal_id=submittal_id,
                    old=db_manager_value,
                    new=submittal_manager,
                )
            if order_bumped:
                logger.info("submittal_order_bumped", submittal_id=submittal_id)
        else:
            logger.debug(
                "submittal_update_skipped",
                submittal_id=submittal_id,
                reason="already_in_sync",
                ball_in_court=ball_in_court,
                status=status,
            )
        return ball_updated, status_updated, title_updated, manager_updated, record, ball_in_court, status

    except Exception as e:
        logger.error(
            "submittal_update_failed",
            submittal_id=submittal_id,
            project_id=project_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return False, False, False, False, None, None, None

# Get Viewer URL for Job (without Trello updates)
def get_viewer_url_for_job(job_number, release_number):
    '''
    Function to get procore viewer_url for a job without updating Trello.
    This is used for backfilling viewer_urls into the database.
    
    Args:
        job_number: The job number (integer)
        release_number: The release number (string)
    
    Returns:
        dict with viewer_url if found, None otherwise
        Returns dict with error information if any step fails
    '''
    try:
        # Get companies list
        company_id = get_companies_list()
        if not company_id:
            return {
                "success": False,
                "error": "No Procore company_id returned",
                "job": job_number,
                "release": release_number
            }

        # Get project by company id
        project_id = get_projects_by_company_id(company_id, job_number)
        if not project_id:
            return {
                "success": False,
                "error": f"No Procore project found for job={job_number} company_id={company_id}",
                "job": job_number,
                "release": release_number
            }

        # Get submittals by project id
        identifier = f"{job_number}-{release_number}"
        submittals = get_submittals_by_project_id(project_id, identifier)
        if not submittals:
            return {
                "success": False,
                "error": f"No Procore submittals found for project_id={project_id} identifier={identifier}",
                "job": job_number,
                "release": release_number
            }
        
        final_pdfs = get_final_pdf_viewers(project_id, submittals)
        if not final_pdfs:
            return {
                "success": False,
                "error": f"No final PDF viewers found for project_id={project_id} identifier={identifier}",
                "job": job_number,
                "release": release_number
            }

        # Extract viewer urls from final pdfs
        viewer_url = final_pdfs[0]["viewer_url"]
        submittal_id = final_pdfs[0].get("submittal_id")

        return {
            "success": True,
            "viewer_url": viewer_url,
            "submittal_id": submittal_id,
            "job": job_number,
            "release": release_number
        }
    except Exception as e:
        logger.error(
            "viewer_url_fetch_failed",
            job=job_number,
            release=release_number,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return {
            "success": False,
            "error": f"Exception: {str(e)}",
            "job": job_number,
            "release": release_number
        }


# Add Procore Link to Trello Card
def add_procore_link_to_trello_card(job, release):
    '''
    Function to add procore drafting document link to related trello card
    '''
    logger.debug("procore_link_lookup_started", job=job, release=release)
    job_record = Releases.query.filter_by(job=job, release=release).first()
    if not job_record:
        return None
    logger.debug("release_record_found", job=job, release=release, release_id=job_record.id)
    job_number = job_record.job
    release_number = job_record.release
    card_id = job_record.trello_card_id
    if not card_id:
        return None

    # Get companies list
    company_id = get_companies_list()
    logger.debug("company_id_fetched", company_id=company_id)
    if not company_id:
        logger.error("procore_company_id_missing", job=job, release=release)
        return None

    # Get project by company id
    project_id = get_projects_by_company_id(company_id, job_number)
    logger.debug("project_id_fetched", project_id=project_id, job=job_number)
    if not project_id:
        logger.error(
            "procore_project_not_found",
            job=job_number,
            release=release_number,
            company_id=company_id,
        )
        return None

    # Get submittals by project id
    # job-release
    identifier = f"{job_number}-{release_number}"
    logger.debug("submittal_identifier_built", identifier=identifier)
    submittals = get_submittals_by_project_id(project_id, identifier)
    if not submittals:
        logger.error("procore_submittals_not_found", project_id=project_id, identifier=identifier)
        return None
    final_pdfs = get_final_pdf_viewers(project_id, submittals)
    if not final_pdfs:
        return None

    # Extract viewer urls from final pdfs
    viewer_url = final_pdfs[0]["viewer_url"]
    submittal_id = final_pdfs[0].get("submittal_id")

    # Add procore link to trello card
    add_procore_link(card_id, viewer_url)

    # Persist viewer URL + submittal_id on job record
    job_record.viewer_url = viewer_url
    if submittal_id is not None:
        job_record.procore_submittal_id = str(submittal_id)
    db.session.commit()

    return {
        "card_id": card_id,
        "viewer_url": viewer_url,
        "submittal_id": submittal_id,
    }


def get_drafting_workload():
    '''
    Function to get submittals for drafting workload.
    Returns a list of dicts with submittal_id and project_id for each submittal.
    '''
    # Grab procore instance
    procore = get_procore_client()
    # Collect projects
    projects = procore.get_projects(cfg.PROD_PROCORE_COMPANY_ID)
    
    # Iterate through projects collecting open submittals
    all_submittals = []
    for project in projects:
        if project['id'] == 589044:
            continue
        submittals = procore.get_submittals_for_drafting_workload(project['id'])
        logger.debug("project_submittals_fetched", project_id=project['id'], count=len(submittals))
        
        # Extract submittal_id and project_id for each submittal
        for submittal in submittals:
            if isinstance(submittal, dict) and 'id' in submittal:
                all_submittals.append({
                    'submittal_id': str(submittal['id']),
                    'project_id': project['id']
                })

    logger.debug("drafting_workload_fetched", count=len(all_submittals))
    return all_submittals


def cross_reference_db_vs_api():
    """
    Cross-reference database submittals with Procore API response.
    Finds submittals that exist in DB but not in the API response.
    Filters DB submittals to match the same status and type criteria as the API call.
    
    Returns:
        dict with:
            - db_only_submittals: List of Submittals records in DB but not in API
            - api_submittal_ids: Set of submittal IDs from API
            - db_submittal_ids: Set of submittal IDs from DB (filtered)
            - missing_in_api: Count of submittals in DB but not in API
    """
    logger.debug("db_api_cross_reference_started")

    # Get submittals from API
    api_submittals = get_drafting_workload()
    api_submittal_ids = {s['submittal_id'] for s in api_submittals}
    logger.debug("api_submittals_fetched", count=len(api_submittals), unique_count=len(api_submittal_ids))

    # Debug: Show sample API submittals
    if api_submittals:
        for i, sub in enumerate(api_submittals[:5]):
            logger.debug(
                "api_submittal_sample",
                index=i + 1,
                submittal_id=sub.get('submittal_id'),
                submittal_id_type=type(sub.get('submittal_id')).__name__,
                project_id=sub.get('project_id'),
            )
        logger.debug(
            "api_submittal_id_types",
            types=sorted({type(sid).__name__ for sid in api_submittal_ids}),
        )
    
    # Filter DB submittals to match API criteria:
    # - status: "Open" (status_id 203238 in API)
    # - type: "Drafting Release Review" or "Submittal for GC  Approval" or "Submittal for GC Approval"
    valid_types = [
        "Drafting Release Review",
        "Submittal for GC  Approval",
        "Submittal for GC Approval",
        "Submittal for Gc  Approval",
        "Submittal for Gc Approval",
        "Submittal For Gc  Approval",
        "Submittal For Gc Approval",
    ]
    
    logger.debug("db_submittal_filter_applied", status_filter="Open", type_filter=valid_types)

    # First, check total count in DB
    total_db_count = Submittals.query.count()
    logger.debug("db_submittal_total", count=total_db_count)

    # Check count by status
    status_counts = db.session.query(
        Submittals.status,
        db.func.count(Submittals.id)
    ).group_by(Submittals.status).all()
    logger.debug("db_submittal_status_counts", counts=dict(status_counts))

    # Check count by type
    type_counts = db.session.query(
        Submittals.type,
        db.func.count(Submittals.id)
    ).group_by(Submittals.type).all()
    logger.debug("db_submittal_type_counts", counts=dict(type_counts[:10]))

    # Apply filters
    db_submittals = Submittals.query.filter(
        Submittals.status == "Open",
        Submittals.type.in_(valid_types)
    ).all()

    logger.debug("db_submittals_filtered", count=len(db_submittals))

    # Debug: Show sample DB submittals
    if db_submittals:
        for i, sub in enumerate(db_submittals[:5]):
            logger.debug(
                "db_submittal_sample",
                index=i + 1,
                submittal_id=sub.submittal_id,
                submittal_id_type=type(sub.submittal_id).__name__,
                project_id=sub.procore_project_id,
                submittal_status=sub.status,
                submittal_type=sub.type,
            )
        logger.debug(
            "db_submittal_id_types",
            types=sorted({type(s.submittal_id).__name__ for s in db_submittals}),
        )

    db_submittal_ids = {s.submittal_id for s in db_submittals}
    logger.debug("db_submittal_ids_extracted", count=len(db_submittal_ids))

    # Debug: Check for type mismatches
    api_id_types = {type(sid).__name__ for sid in api_submittal_ids}
    db_id_types = {type(sid).__name__ for sid in db_submittal_ids}
    logger.debug("submittal_id_types_compared", api_types=sorted(api_id_types), db_types=sorted(db_id_types))

    if api_id_types != db_id_types:
        logger.warning(
            "submittal_id_type_mismatch",
            api_types=sorted(api_id_types),
            db_types=sorted(db_id_types),
        )
        # Convert both to strings for comparison
        api_submittal_ids_str = {str(sid) for sid in api_submittal_ids}
        db_submittal_ids_str = {str(sid) for sid in db_submittal_ids}
        logger.debug(
            "submittal_ids_stringified",
            api_count=len(api_submittal_ids_str),
            db_count=len(db_submittal_ids_str),
        )

        # Use string comparison
        db_only_ids = db_submittal_ids_str - api_submittal_ids_str
        logger.debug("db_only_ids_found", count=len(db_only_ids), comparison="string")
    else:
        # Direct comparison
        db_only_ids = db_submittal_ids - api_submittal_ids
        logger.debug("db_only_ids_found", count=len(db_only_ids), comparison="direct")
    
    # Find submittals in DB but not in API
    # Convert db_submittal_ids to strings if needed for matching
    if api_id_types != db_id_types:
        api_submittal_ids_str = {str(sid) for sid in api_submittal_ids}
        db_only_submittals = [s for s in db_submittals if str(s.submittal_id) in db_only_ids]
    else:
        db_only_submittals = [s for s in db_submittals if s.submittal_id in db_only_ids]

    logger.debug("db_only_submittals_found", count=len(db_only_submittals))

    # Debug: Show sample orphaned submittals
    if db_only_submittals:
        for i, sub in enumerate(db_only_submittals[:5]):
            logger.debug(
                "orphaned_submittal_sample",
                index=i + 1,
                submittal_id=sub.submittal_id,
                project_id=sub.procore_project_id,
                title=sub.title[:50] if sub.title else None,
                submittal_status=sub.status,
                submittal_type=sub.type,
            )
    
    # Group by project_id for easier analysis
    db_only_by_project = {}
    for submittal in db_only_submittals:
        project_id = submittal.procore_project_id
        if project_id not in db_only_by_project:
            db_only_by_project[project_id] = []
        db_only_by_project[project_id].append(submittal)

    # Debug: Show projects with orphaned submittals
    if db_only_by_project:
        for project_id, submittals in list(db_only_by_project.items())[:10]:
            logger.debug("project_orphan_count", project_id=project_id, count=len(submittals))

    # Summary
    logger.debug(
        "db_api_cross_reference_complete",
        api_count=len(api_submittal_ids),
        db_count=len(db_submittal_ids),
        orphan_count=len(db_only_submittals),
        orphan_project_count=len(db_only_by_project),
    )

    return {
        'db_only_submittals': db_only_submittals,
        'db_only_by_project': db_only_by_project,
        'api_submittal_ids': api_submittal_ids,
        'db_submittal_ids': db_submittal_ids,
        'missing_in_api': len(db_only_submittals),
        'api_count': len(api_submittal_ids),
        'db_count': len(db_submittal_ids)
    }


def check_webhook_health(project_ids=None):
    """
    Check webhook health for specified projects or all projects with submittals in DB.
    
    Args:
        project_ids: Optional list of project IDs to check. If None, checks all projects
                     that have submittals in the database.
    
    Returns:
        dict with:
            - projects_with_webhooks: List of project IDs that have webhooks
            - projects_without_webhooks: List of project IDs missing webhooks
            - webhook_details: Dict mapping project_id to webhook info
            - broken_webhooks: List of projects with webhooks that appear broken
    """
    logger.debug("webhook_health_check_started")
    procore = get_procore_client()
    
    # If no project_ids provided, get all unique project IDs from DB
    # Filter to match the same criteria as the API call (status=Open, valid types)
    if project_ids is None:
        valid_types = [
            "Drafting Release Review",
            "Submittal for GC  Approval",
            "Submittal for GC Approval"
        ]
        db_projects = db.session.query(Submittals.procore_project_id).filter(
            Submittals.status == "Open",
            Submittals.type.in_(valid_types)
        ).distinct().all()
        project_ids = [str(p[0]) for p in db_projects if p[0]]
        logger.debug("webhook_check_projects_selected", count=len(project_ids), selection="db_filtered")
    else:
        # Convert to strings for consistency
        project_ids = [str(pid) for pid in project_ids]
        logger.debug("webhook_check_projects_selected", count=len(project_ids), selection="specified")
    
    projects_with_webhooks = []
    projects_without_webhooks = []
    webhook_details = {}
    broken_webhooks = []
    
    for project_id in project_ids:
        try:
            # List webhooks for this project
            webhooks = procore.list_project_webhooks(int(project_id), 'mile-high-metal-works')
            
            if not webhooks or len(webhooks) == 0:
                projects_without_webhooks.append(project_id)
                webhook_details[project_id] = {
                    'has_webhook': False,
                    'webhook_count': 0,
                    'webhooks': []
                }
                logger.warning("project_webhooks_missing", project_id=project_id)
            else:
                projects_with_webhooks.append(project_id)
                
                # Check webhook details and triggers
                webhook_info = []
                for webhook in webhooks:
                    hook_id = webhook.get('id')
                    if hook_id:
                        try:
                            # Get webhook details
                            details = procore.get_webhook_details(int(project_id), hook_id)
                            triggers = procore.get_webhook_triggers(int(project_id), hook_id)
                            
                            # Check if webhook has the required triggers (create and update for Submittals)
                            has_create = any(
                                t.get('resource_name') == 'Submittals' and 
                                t.get('event_type') == 'create'
                                for t in triggers
                            )
                            has_update = any(
                                t.get('resource_name') == 'Submittals' and 
                                t.get('event_type') == 'update'
                                for t in triggers
                            )
                            
                            webhook_info.append({
                                'id': hook_id,
                                'destination_url': details.get('destination_url'),
                                'namespace': details.get('namespace'),
                                'has_create_trigger': has_create,
                                'has_update_trigger': has_update,
                                'triggers': triggers,
                                'is_healthy': has_create and has_update
                            })
                            
                            # Mark as broken if missing required triggers
                            if not (has_create and has_update):
                                if project_id not in broken_webhooks:
                                    broken_webhooks.append(project_id)
                        except Exception as e:
                            logger.error(
                                "webhook_check_failed",
                                webhook_id=hook_id,
                                project_id=project_id,
                                error=str(e),
                                error_type=type(e).__name__,
                                exc_info=True,
                            )
                            webhook_info.append({
                                'id': hook_id,
                                'error': str(e)
                            })
                
                webhook_details[project_id] = {
                    'has_webhook': True,
                    'webhook_count': len(webhooks),
                    'webhooks': webhook_info
                }
                
        except Exception as e:
            logger.error(
                "project_webhook_check_failed",
                project_id=project_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            projects_without_webhooks.append(project_id)
            webhook_details[project_id] = {
                'has_webhook': False,
                'error': str(e)
            }
    
    logger.debug(
        "webhook_health_check_complete",
        with_webhooks=len(projects_with_webhooks),
        without_webhooks=len(projects_without_webhooks),
        broken=len(broken_webhooks),
    )
    
    return {
        'projects_with_webhooks': projects_with_webhooks,
        'projects_without_webhooks': projects_without_webhooks,
        'broken_webhooks': broken_webhooks,
        'webhook_details': webhook_details,
        'total_checked': len(project_ids)
    }


def comprehensive_health_scan(skip_user_prompt=False):
    """
    Comprehensive health scan for orphaned submittals:
    1. Find submittals in DB but not in API response
    2. Check webhooks for projects with orphaned submittals
    3. Fetch full submittal data from API for each orphaned submittal
    4. Compare ball_in_court and status between DB and API
    5. List all differences and provide recommendations
    
    Args:
        skip_user_prompt: If True, skip the interactive user prompt for updating records.
                          Use this when calling from API endpoints.
    
    Returns:
        dict with:
            - orphaned_submittals: List of orphaned submittal analysis
            - webhook_status: Webhook health for orphaned projects
            - summary: Summary statistics and recommendations
            - differences: Detailed list of all mismatches
            - updated_count: Number of records updated (if user confirmed)
    """
    logger.debug("health_scan_started")

    # Step 1: Find orphaned submittals
    logger.debug("orphan_scan_started")
    cross_ref = cross_reference_db_vs_api()
    orphaned_submittals = cross_ref['db_only_submittals']
    orphaned_by_project = cross_ref['db_only_by_project']

    if not orphaned_submittals:
        logger.debug("orphan_scan_clean")
        return {
            'orphaned_submittals': [],
            'webhook_status': None,
            'summary': {
                'total_orphaned': 0,
                'projects_with_orphans': 0,
                'sync_issues': 0,
                'deleted_submittals': 0,
                'api_fetch_errors': 0,
                'webhook_issues': 0,
                'projects_missing_webhooks': 0
            },
            'differences': {
                'sync_issues': [],
                'deleted_submittals': [],
                'api_fetch_errors': []
            },
            'updated_count': 0
        }
    
    logger.debug(
        "orphans_found",
        count=len(orphaned_submittals),
        project_count=len(orphaned_by_project),
    )

    # Step 2: Check webhooks for projects with orphaned submittals
    logger.debug("orphan_webhook_check_started")
    orphaned_project_ids = list(orphaned_by_project.keys())
    webhook_status = check_webhook_health(orphaned_project_ids)
    logger.debug(
        "orphan_webhook_check_complete",
        projects_missing_webhooks=len(webhook_status['projects_without_webhooks']),
    )

    # Step 3 & 4: Fetch API data and compare for each orphaned submittal
    logger.debug("orphan_comparison_started")
    procore = get_procore_client()
    differences = []
    sync_issues = []
    deleted_submittals = []
    api_fetch_errors = []
    
    for submittal in orphaned_submittals:
        submittal_id = submittal.submittal_id
        project_id = submittal.procore_project_id
        
        try:
            # Fetch full submittal data from API
            api_submittal_data = get_submittal_by_id(int(project_id), int(submittal_id))
            
            if not api_submittal_data or not isinstance(api_submittal_data, dict):
                # Submittal doesn't exist in API - likely deleted/archived
                deleted_submittals.append({
                    'submittal_id': submittal_id,
                    'project_id': project_id,
                    'project_name': submittal.project_name,
                    'title': submittal.title,
                    'db_status': submittal.status,
                    'db_ball_in_court': submittal.ball_in_court,
                    'recommendation': 'Consider removing from DB or marking as archived'
                })
                logger.warning("submittal_missing_in_api", submittal_id=submittal_id, project_id=project_id)
                continue
            
            # Parse ball_in_court from API data
            parsed = parse_ball_in_court_from_submittal(api_submittal_data)
            api_ball_in_court = parsed.get("ball_in_court") if parsed else None
            
            # Extract status from API data
            status_obj = api_submittal_data.get("status")
            if isinstance(status_obj, dict):
                api_status = status_obj.get("name")
            elif isinstance(status_obj, str):
                api_status = status_obj
            else:
                api_status = None
            api_status = str(api_status).strip() if api_status else None
            
            # Compare with DB
            db_ball_in_court = submittal.ball_in_court if submittal.ball_in_court else None
            db_status = submittal.status if submittal.status else None
            
            ball_mismatch = str(db_ball_in_court or "") != str(api_ball_in_court or "")
            status_mismatch = str(db_status or "") != str(api_status or "")
            
            if ball_mismatch or status_mismatch:
                # Sync issue - submittal exists in API but values don't match
                diff = {
                    'submittal_id': submittal_id,
                    'project_id': project_id,
                    'project_name': submittal.project_name,
                    'title': submittal.title,
                    'ball_in_court': {
                        'db': db_ball_in_court,
                        'api': api_ball_in_court,
                        'mismatch': ball_mismatch
                    },
                    'status': {
                        'db': db_status,
                        'api': api_status,
                        'mismatch': status_mismatch
                    },
                    'recommendation': 'Sync issue - DB values are out of date. Webhook may not be working or submittal was updated outside of webhook flow.'
                }
                differences.append(diff)
                sync_issues.append(diff)
                logger.warning(
                    "submittal_sync_mismatch",
                    submittal_id=submittal_id,
                    ball_mismatch=ball_mismatch,
                    status_mismatch=status_mismatch,
                )
            else:
                # Values match - submittal exists in API but wasn't in the filtered API response
                # This could mean status/type changed, or it's filtered out for another reason
                logger.debug("submittal_values_match", submittal_id=submittal_id)

        except Exception as e:
            # Error fetching from API
            api_fetch_errors.append({
                'submittal_id': submittal_id,
                'project_id': project_id,
                'project_name': submittal.project_name,
                'title': submittal.title,
                'error': str(e),
                'recommendation': 'Check API access and submittal permissions'
            })
            logger.error(
                "submittal_fetch_failed",
                submittal_id=submittal_id,
                project_id=project_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

    logger.debug(
        "orphan_comparison_complete",
        sync_issues=len(sync_issues),
        deleted_submittals=len(deleted_submittals),
        api_fetch_errors=len(api_fetch_errors),
    )
    
    # Compile results
    summary = {
        'total_orphaned': len(orphaned_submittals),
        'projects_with_orphans': len(orphaned_by_project),
        'sync_issues': len(sync_issues),
        'deleted_submittals': len(deleted_submittals),
        'api_fetch_errors': len(api_fetch_errors),
        'webhook_issues': len(webhook_status['projects_without_webhooks']),
        'projects_missing_webhooks': len(webhook_status['projects_without_webhooks'])
    }
    
    # Log detailed differences
    if sync_issues:
        for issue in sync_issues:
            logger.debug(
                "sync_issue_detail",
                submittal_id=issue['submittal_id'],
                project_id=issue['project_id'],
                project_name=issue['project_name'],
                title=issue['title'],
            )
            if issue['ball_in_court']['mismatch']:
                logger.debug(
                    "sync_issue_ball_in_court",
                    submittal_id=issue['submittal_id'],
                    old=issue['ball_in_court']['db'],
                    new=issue['ball_in_court']['api'],
                )
            if issue['status']['mismatch']:
                logger.debug(
                    "sync_issue_status",
                    submittal_id=issue['submittal_id'],
                    old=issue['status']['db'],
                    new=issue['status']['api'],
                )

    if deleted_submittals:
        for deleted in deleted_submittals:
            logger.debug(
                "deleted_submittal_detail",
                submittal_id=deleted['submittal_id'],
                project_id=deleted['project_id'],
                project_name=deleted['project_name'],
                title=deleted['title'],
                db_status=deleted['db_status'],
                db_ball_in_court=deleted['db_ball_in_court'],
            )

    if api_fetch_errors:
        for error in api_fetch_errors:
            logger.debug(
                "api_fetch_error_detail",
                submittal_id=error['submittal_id'],
                project_id=error['project_id'],
                project_name=error['project_name'],
                title=error['title'],
                error=error['error'],
            )

    if webhook_status['projects_without_webhooks']:
        for project_id in webhook_status['projects_without_webhooks']:
            logger.debug("project_webhook_missing_detail", project_id=project_id)

    logger.info(
        "health_scan_complete",
        total_orphaned=summary['total_orphaned'],
        projects_with_orphans=summary['projects_with_orphans'],
        sync_issues=summary['sync_issues'],
        deleted_submittals=summary['deleted_submittals'],
        api_fetch_errors=summary['api_fetch_errors'],
        projects_missing_webhooks=summary['projects_missing_webhooks'],
    )
    
    # Ask user if they want to update DB records to match API (only if not skipping prompt)
    updated_count = 0
    if sync_issues and not skip_user_prompt:
        logger.info("sync_fix_prompted", count=len(sync_issues))
        user_input = input("\nWould you like to update DB records to match API values? (yes/no): ").strip().lower()

        if user_input == 'yes':
            logger.debug("sync_fix_confirmed", count=len(sync_issues))
            for issue in sync_issues:
                try:
                    # Find the DB record
                    db_record = Submittals.query.filter_by(submittal_id=issue['submittal_id']).first()
                    if not db_record:
                        logger.warning("submittal_record_missing", submittal_id=issue['submittal_id'])
                        continue

                    # Update ball_in_court if there's a mismatch
                    if issue['ball_in_court']['mismatch']:
                        old_value = db_record.ball_in_court
                        db_record.ball_in_court = issue['ball_in_court']['api']
                        logger.info(
                            "ball_in_court_updated",
                            submittal_id=issue['submittal_id'],
                            old=old_value,
                            new=issue['ball_in_court']['api'],
                            source="health_scan",
                        )

                    # Update status if there's a mismatch
                    if issue['status']['mismatch']:
                        old_value = db_record.status
                        db_record.status = issue['status']['api']
                        logger.info(
                            "submittal_status_updated",
                            submittal_id=issue['submittal_id'],
                            old=old_value,
                            new=issue['status']['api'],
                            source="health_scan",
                        )

                    # Update last_updated timestamp
                    db_record.last_updated = datetime.utcnow()
                    updated_count += 1

                except Exception as e:
                    logger.error(
                        "submittal_update_failed",
                        submittal_id=issue['submittal_id'],
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True,
                    )

            # Commit all changes
            try:
                db.session.commit()
                logger.info("sync_fix_committed", count=updated_count)
            except Exception as e:
                db.session.rollback()
                logger.error(
                    "sync_fix_commit_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                )
        else:
            logger.debug("sync_fix_declined")
    
    return {
        'orphaned_submittals': orphaned_submittals,
        'webhook_status': webhook_status,
        'summary': summary,
        'differences': {
            'sync_issues': sync_issues,
            'deleted_submittals': deleted_submittals,
            'api_fetch_errors': api_fetch_errors
        },
        'updated_count': updated_count
    }


if __name__ == "__main__":
    from app import create_app
    app = create_app()
    # app context
    with app.app_context():

        # Comprehensive health scan
        result = comprehensive_health_scan()
        logger.info(
            "health_scan_summary",
            total_orphaned=result['summary']['total_orphaned'],
            projects_with_orphans=result['summary']['projects_with_orphans'],
            sync_issues=result['summary']['sync_issues'],
            deleted_submittals=result['summary']['deleted_submittals'],
            api_fetch_errors=result['summary']['api_fetch_errors'],
            projects_missing_webhooks=result['summary']['projects_missing_webhooks'],
        )
        if 'updated_count' in result:
            logger.info("health_scan_records_updated", count=result['updated_count'])
