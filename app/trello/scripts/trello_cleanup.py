"""
Trello cleanup script: finds Job records missing Trello cards, creates them
in the correct list, syncs the Releases shadow table, and archives completed rows.

Usage:
    python -m app.trello.scripts.trello_cleanup [--dry-run] [--verbose]
"""

import argparse
import math
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

import requests
from app import create_app
from app.config import Config as cfg
from app.models import Job, Releases, db
from app.sync.services.trello_list_mapper import TrelloListMapper
from app.trello.api import (
    get_all_trello_cards,
    get_list_by_name,
    get_list_name_by_id,
    safe_float,
    safe_string,
    update_card_custom_field_number,
    add_comment_to_trello_card,
    calculate_installation_duration,
)
from app.trello.api import to_date
from app.trello.utils import parse_trello_datetime
from app.api.helpers import get_stage_group_from_stage


def find_missing_cards(verbose=False):
    """Find Job records that are missing Trello cards.

    Returns list of Job records that either have no trello_card_id or whose
    card no longer exists on the board.
    """
    # Get all cards currently on the board
    print("Fetching all Trello cards from board...")
    board_cards = get_all_trello_cards()
    board_card_ids = {c["id"] for c in board_cards}
    print(f"  Found {len(board_card_ids)} cards on board")

    # Query all Job records
    all_jobs = Job.query.all()
    print(f"  Found {len(all_jobs)} total Job records in database")

    missing = []
    orphaned = []  # have a card_id but card no longer exists on board

    for job in all_jobs:
        if not job.trello_card_id:
            missing.append(job)
        elif job.trello_card_id not in board_card_ids:
            orphaned.append(job)

    if verbose:
        for job in missing:
            print(f"    MISSING: {job.job}-{job.release} {job.job_name}")
        for job in orphaned:
            print(
                f"    ORPHANED (card deleted): {job.job}-{job.release} "
                f"{job.job_name} (was {job.trello_card_id})"
            )

    print(f"\n  {len(missing)} records with no Trello card")
    print(f"  {len(orphaned)} records with deleted Trello card")

    # Clear stale card IDs on orphaned records so they get recreated
    for job in orphaned:
        job.trello_card_id = None
        job.trello_card_name = None
        job.trello_list_id = None
        job.trello_list_name = None
        job.trello_card_date = None

    return missing + orphaned


def build_card_title(job):
    """Build Trello card title matching the format from create_trello_card_from_excel_data."""
    return f"{job.job}-{job.release} {job.job_name} {job.description or ''}"


def build_card_description(job):
    """Build Trello card description matching the format from create_trello_card_from_excel_data."""
    parts = []
    if job.description:
        parts.append(f"**Description:** {job.description}")
    if job.install_hrs:
        parts.append(f"**Install HRS:** {job.install_hrs}")
        num_guys = 2
        parts.append(f"**Number of Guys:** {num_guys}")
        duration = calculate_installation_duration(job.install_hrs, num_guys)
        if duration is not None:
            parts.append(f"**Installation Duration:** {duration} days")
    if job.paint_color:
        parts.append(f"**Paint color:** {job.paint_color}")
    if job.pm and job.by:
        parts.append(f"**Team:** PM: {job.pm} / BY: {job.by}")
    if job.released:
        parts.append(f"**Released:** {job.released}")
    return "\n".join(parts)


def determine_list_for_job(job):
    """Determine the correct Trello list for a Job record.

    Uses TrelloListMapper, falls back to 'Released' if no stage fields match.
    """
    target_list_name = TrelloListMapper.determine_trello_list_from_db(job)
    if not target_list_name:
        target_list_name = "Released"
    return target_list_name


def create_card_for_job(job, list_name, list_id, dry_run=False, verbose=False):
    """Create a Trello card for a Job record and update the DB.

    Returns the card data dict on success, None on failure.
    """
    title = build_card_title(job)
    desc = build_card_description(job)

    if dry_run:
        print(f"  [DRY RUN] Would create card: {title} -> list '{list_name}'")
        return None

    payload = {
        "key": cfg.TRELLO_API_KEY,
        "token": cfg.TRELLO_TOKEN,
        "name": title,
        "desc": desc,
        "idList": list_id,
        "pos": "top",
    }

    response = requests.post("https://api.trello.com/1/cards", params=payload)
    response.raise_for_status()
    card_data = response.json()

    if verbose:
        print(f"  Created card {card_data['id']}")

    # Update Job record with Trello data
    job.trello_card_id = card_data["id"]
    job.trello_card_name = card_data["name"]
    job.trello_list_id = list_id
    job.trello_list_name = list_name

    due_val = card_data.get("due")
    if due_val:
        parsed = parse_trello_datetime(due_val)
        job.trello_card_date = parsed.date() if parsed else None
    else:
        job.trello_card_date = None

    job.trello_card_description = desc
    job.last_updated_at = datetime.utcnow()
    job.source_of_update = "System"

    # Fab Order custom field
    if job.fab_order is not None:
        try:
            fab_order_int = math.ceil(job.fab_order) if isinstance(job.fab_order, float) else int(job.fab_order)
            if cfg.FAB_ORDER_FIELD_ID:
                update_card_custom_field_number(
                    card_data["id"], cfg.FAB_ORDER_FIELD_ID, fab_order_int
                )
                if verbose:
                    print(f"    Set Fab Order = {fab_order_int}")
        except (ValueError, TypeError):
            pass

    # Notes as comment
    if job.notes and str(job.notes).strip() and str(job.notes).strip().lower() not in ("nan", "none"):
        add_comment_to_trello_card(card_data["id"], str(job.notes).strip())
        if verbose:
            print(f"    Added notes comment")

    return card_data


def sync_releases_for_job(job, list_name, dry_run=False, verbose=False):
    """Ensure a Releases record exists and mirrors the Job record."""
    rel = Releases.query.filter_by(job=job.job, release=job.release).one_or_none()

    stage_group = get_stage_group_from_stage(list_name)

    if rel is None:
        if dry_run:
            print(f"  [DRY RUN] Would create Releases record for {job.job}-{job.release}")
            return
        rel = Releases(
            job=job.job,
            release=job.release,
            job_name=job.job_name,
            description=job.description,
            fab_hrs=job.fab_hrs,
            install_hrs=job.install_hrs,
            paint_color=job.paint_color,
            pm=job.pm,
            by=job.by,
            released=job.released,
            fab_order=job.fab_order,
            stage=list_name,
            stage_group=stage_group,
            start_install=job.start_install,
            start_install_formula=job.start_install_formula,
            start_install_formulaTF=job.start_install_formulaTF,
            comp_eta=job.comp_eta,
            job_comp=job.job_comp,
            invoiced=job.invoiced,
            notes=job.notes,
            trello_card_id=job.trello_card_id,
            trello_card_name=job.trello_card_name,
            trello_list_id=job.trello_list_id,
            trello_list_name=job.trello_list_name,
            trello_card_description=job.trello_card_description,
            trello_card_date=job.trello_card_date,
            viewer_url=job.viewer_url,
            last_updated_at=datetime.utcnow(),
            source_of_update="System",
            is_active=True,
            is_archived=False,
        )
        db.session.add(rel)
        if verbose:
            print(f"    Created Releases record for {job.job}-{job.release}")
    else:
        if dry_run:
            print(f"  [DRY RUN] Would update Releases record for {job.job}-{job.release}")
            return
        # Update Trello fields and stage
        rel.trello_card_id = job.trello_card_id
        rel.trello_card_name = job.trello_card_name
        rel.trello_list_id = job.trello_list_id
        rel.trello_list_name = job.trello_list_name
        rel.trello_card_description = job.trello_card_description
        rel.trello_card_date = job.trello_card_date
        rel.stage = list_name
        rel.stage_group = stage_group
        rel.last_updated_at = datetime.utcnow()
        rel.source_of_update = "System"
        if verbose:
            print(f"    Updated Releases record for {job.job}-{job.release}")


def archive_completed_releases(dry_run=False, verbose=False):
    """Archive Releases rows where job_comp='X' AND invoiced='X'."""
    completed = Releases.query.filter(
        Releases.job_comp == "X",
        Releases.invoiced == "X",
        Releases.is_archived == False,
    ).all()

    print(f"\n--- Step 5: Archive completed Releases ---")
    print(f"  Found {len(completed)} completed+invoiced rows to archive")

    if dry_run:
        for rel in completed:
            print(f"  [DRY RUN] Would archive: {rel.job}-{rel.release} {rel.job_name}")
        return len(completed)

    for rel in completed:
        rel.is_archived = True
        if verbose:
            print(f"  Archived: {rel.job}-{rel.release} {rel.job_name}")

    db.session.commit()
    print(f"  Archived {len(completed)} rows")
    return len(completed)


def main():
    parser = argparse.ArgumentParser(
        description="Audit jobs table for missing Trello cards, create them, sync releases, archive old rows",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, no changes")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        # --- Step 1: Find missing cards ---
        print("--- Step 1: Find Job records missing Trello cards ---")
        missing_jobs = find_missing_cards(verbose=args.verbose)

        if not missing_jobs and not args.dry_run:
            print("\nNo missing cards found.")
        else:
            # --- Step 2 & 3: Determine lists and create cards ---
            print(f"\n--- Steps 2-3: Determine lists and create cards ---")

            # Pre-fetch list name->id mapping
            list_cache = {}
            created = 0
            failed = 0

            for job in missing_jobs:
                list_name = determine_list_for_job(job)

                # Resolve list ID (cached)
                if list_name not in list_cache:
                    list_info = get_list_by_name(list_name)
                    if not list_info:
                        print(f"  ERROR: List '{list_name}' not found on board, skipping {job.job}-{job.release}")
                        failed += 1
                        continue
                    list_cache[list_name] = list_info["id"]
                list_id = list_cache[list_name]

                identifier = f"{job.job}-{job.release}"
                print(f"  {identifier} {job.job_name} -> '{list_name}'")

                try:
                    card = create_card_for_job(job, list_name, list_id, dry_run=args.dry_run, verbose=args.verbose)
                    if card or args.dry_run:
                        created += 1
                except Exception as e:
                    print(f"  ERROR creating card for {identifier}: {e}")
                    failed += 1
                    continue

                # --- Step 4: Sync releases ---
                sync_releases_for_job(job, list_name, dry_run=args.dry_run, verbose=args.verbose)

            if not args.dry_run:
                db.session.commit()

            print(f"\n  Cards created: {created}")
            if failed:
                print(f"  Failed: {failed}")

        # --- Step 5: Archive old releases ---
        archive_completed_releases(dry_run=args.dry_run, verbose=args.verbose)

        print("\nDone.")


if __name__ == "__main__":
    main()
