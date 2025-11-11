"""
Audit and fix shipping-related Trello cards against database records.

This script:
  * Pulls all open cards in the "Store at MHMW for shipping" and
    "Shipping planning" lists.
  * Ensures a matching `Job` record exists.
  * Updates each `Job` so Trello metadata and staging fields reflect the
    expected X-X-X-"X" flow for that list.
  * Reports cards that do not map to an existing job so they can be added
    manually.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from app.config import Config as cfg
from app.logging_config import get_logger
from app.models import Job, db
from app.trello.api import get_list_by_name
from app.trello.utils import extract_identifier


logger = get_logger(__name__)


@dataclass
class ListConfig:
    name: str
    expected_status: Dict[str, str]


@dataclass
class JobChange:
    field: str
    old: Optional[str]
    new: Optional[str]


@dataclass
class JobUpdateRecord:
    job_release: str
    job_id: int
    trello_card_id: str
    changes: List[JobChange] = field(default_factory=list)


@dataclass
class MissingCardRecord:
    list_name: str
    trello_card_id: str
    trello_card_name: str
    identifier: Optional[str]


LIST_CONFIGS: List[ListConfig] = [
    ListConfig(
        name="Store at MHMW for shipping",
        expected_status={"fitup_comp": "X", "welded": "X", "paint_comp": "X", "ship": "ST"},
    ),
    ListConfig(
        name="Shipping planning",
        expected_status={"fitup_comp": "X", "welded": "X", "paint_comp": "X", "ship": "RS"},
    ),
]


def _normalize(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def _fetch_trello_cards(list_name: str) -> List[Dict]:
    list_info = get_list_by_name(list_name)
    if not list_info:
        logger.warning("Target Trello list not found", list_name=list_name)
        return []

    url = f"https://api.trello.com/1/lists/{list_info['id']}/cards"
    params = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "filter": "open",
        "fields": "id,name,idList",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    cards = response.json()
    logger.info("Fetched Trello cards", list_name=list_name, count=len(cards))
    return cards


def _find_job_for_card(card: Dict) -> Optional[Job]:
    card_id = card.get("id")
    if not card_id:
        return None

    job = Job.query.filter_by(trello_card_id=card_id).first()
    if job:
        return job

    identifier = extract_identifier(card.get("name", ""))
    if not identifier:
        return None

    try:
        job_part, release_part = identifier.split("-", 1)
        job_number = int(job_part)
        release_number = release_part.upper()
    except (ValueError, AttributeError):
        logger.warning("Failed to parse identifier", identifier=identifier, card_id=card_id)
        return None

    return Job.query.filter_by(job=job_number, release=release_number).first()


def _apply_expected_status(job: Job, expected_status: Dict[str, str]) -> List[JobChange]:
    updates: List[JobChange] = []
    for field, expected_value in expected_status.items():
        current_value = _normalize(getattr(job, field))
        if current_value != expected_value:
            updates.append(
                JobChange(
                    field=field,
                    old=getattr(job, field),
                    new=expected_value,
                )
            )
            setattr(job, field, expected_value)
    return updates


def _ensure_trello_metadata(job: Job, card: Dict, list_name: str) -> List[JobChange]:
    changes: List[JobChange] = []
    trello_updates = {
        "trello_card_id": card.get("id"),
        "trello_list_id": card.get("idList"),
        "trello_list_name": list_name,
        "trello_card_name": card.get("name"),
    }

    for field, new_value in trello_updates.items():
        current_value = getattr(job, field)
        if current_value != new_value:
            changes.append(JobChange(field=field, old=current_value, new=new_value))
            setattr(job, field, new_value)

    return changes


def reconcile_list(session: Session, list_config: ListConfig) -> Dict[str, object]:
    cards = _fetch_trello_cards(list_config.name)
    missing_cards: List[MissingCardRecord] = []
    job_updates: List[JobUpdateRecord] = []

    for card in cards:
        job = _find_job_for_card(card)
        if not job:
            identifier = extract_identifier(card.get("name", ""))
            missing_cards.append(
                MissingCardRecord(
                    list_name=list_config.name,
                    trello_card_id=card.get("id"),
                    trello_card_name=card.get("name"),
                    identifier=identifier,
                )
            )
            logger.warning(
                "Trello card missing in database",
                card_id=card.get("id"),
                card_name=card.get("name"),
                list_name=list_config.name,
                identifier=identifier,
            )
            continue

        change_set: List[JobChange] = []
        change_set.extend(_ensure_trello_metadata(job, card, list_config.name))
        change_set.extend(_apply_expected_status(job, list_config.expected_status))

        if change_set:
            job.last_updated_at = datetime.utcnow()
            job.source_of_update = "System"
            job_updates.append(
                JobUpdateRecord(
                    job_release=f"{job.job}-{job.release}",
                    job_id=job.id,
                    trello_card_id=card.get("id"),
                    changes=change_set,
                )
            )

    if job_updates:
        session.commit()
    else:
        session.rollback()

    return {
        "list_name": list_config.name,
        "total_cards": len(cards),
        "updated_jobs": [
            {
                "job_release": record.job_release,
                "job_id": record.job_id,
                "trello_card_id": record.trello_card_id,
                "changes": [
                    {"field": change.field, "old": change.old, "new": change.new}
                    for change in record.changes
                ],
            }
            for record in job_updates
        ],
        "missing_cards": [
            {
                "list_name": missing.list_name,
                "trello_card_id": missing.trello_card_id,
                "trello_card_name": missing.trello_card_name,
                "identifier": missing.identifier,
            }
            for missing in missing_cards
        ],
    }


def run_reconciliation() -> Dict[str, object]:
    results = []
    for list_config in LIST_CONFIGS:
        result = reconcile_list(db.session, list_config)
        results.append(result)
    return {"lists": results}


def main():
    from app import create_app

    app = create_app()
    with app.app_context():
        summary = run_reconciliation()
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

