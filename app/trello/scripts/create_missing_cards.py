"""
Interactively create Trello cards for releases missing from the board.

Scans active Releases against all Trello cards to find "truly missing"
releases (no card anywhere on the board), then prompts to create each one.
Logs created cards to a CSV for client reporting.

Usage:
    python -m app.trello.scripts.create_missing_cards [--dry-run]
"""

import argparse
import csv
import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import Releases, db
from app.trello.api import (
    get_all_trello_cards,
    get_list_by_name,
    get_trello_card_by_id,
    update_job_record_with_trello_data,
)
from app.trello.card_creation import (
    build_card_title,
    build_card_description,
    create_trello_card_core,
    apply_card_post_creation_features,
)
from app.trello.scanner import get_expected_trello_list_from_stage


PRIMARY_LISTS = [
    "Released",
    "Fit Up Complete.",
    "Paint complete",
    "Store at MHMW for shipping",
    "Shipping planning",
    "Shipping completed",
]


def _parse_job_release(card_name):
    """Parse job-release from a card name like '170-287 Garrett ...'"""
    parts = card_name.split(" ", 1)
    if not parts:
        return None
    token = parts[0]
    if "-" not in token:
        return None
    job_str, release_str = token.split("-", 1)
    try:
        return (int(job_str), release_str)
    except ValueError:
        return None


def _find_truly_missing():
    """Return list of Releases rows that have no Trello card anywhere on the board."""
    print("  Fetching Trello cards...")
    board_cards = get_all_trello_cards()
    primary_cards = [c for c in board_cards if c["list_name"] in PRIMARY_LISTS]

    print(f"  Total cards on board:     {len(board_cards)}")
    print(f"  Cards in primary lists:   {len(primary_cards)}")

    # Build lookups for primary lists
    card_by_id = {c["id"]: c for c in primary_cards}
    card_by_key = {}
    for c in primary_cards:
        parsed = _parse_job_release(c["name"])
        if parsed:
            card_by_key[parsed] = c

    # Build lookup for ALL board cards
    all_card_by_key = {}
    for c in board_cards:
        parsed = _parse_job_release(c["name"])
        if parsed:
            all_card_by_key.setdefault(parsed, []).append(c)

    active_releases = Releases.query.filter(Releases.is_archived == False).all()
    print(f"  Active Releases:          {len(active_releases)}")

    # First pass: find releases missing from primary lists
    missing_from_primary = []
    for rel in active_releases:
        card = None
        if rel.trello_card_id:
            card = card_by_id.get(rel.trello_card_id)
        if not card:
            key = (rel.job, str(rel.release))
            card = card_by_key.get(key)
        if not card:
            missing_from_primary.append(rel)

    # Second pass: check if missing ones exist anywhere on board
    truly_missing = []
    for rel in sorted(missing_from_primary, key=lambda r: (r.job, r.release)):
        key = (rel.job, str(rel.release))
        if key not in all_card_by_key:
            truly_missing.append(rel)

    print(f"  Missing from primary:     {len(missing_from_primary)}")
    print(f"  Truly missing (no card):  {len(truly_missing)}")
    return truly_missing


def _create_card_for_release(rel):
    """Create a Trello card for a Release and update the DB row.

    Returns dict with card info on success, or None on failure.
    """
    # Determine target list
    list_name = get_expected_trello_list_from_stage(rel.stage)
    if not list_name:
        list_name = "Released"  # fallback

    target_list = get_list_by_name(list_name)
    if not target_list:
        print(f"    ERROR: List '{list_name}' not found on board")
        return None
    list_id = target_list["id"]

    # Build card
    card_title = build_card_title(rel.job, rel.release, rel.job_name, rel.description)
    card_desc = build_card_description(
        description=rel.description,
        install_hrs=rel.install_hrs,
        paint_color=rel.paint_color,
        pm=rel.pm,
        by=rel.by,
        released=rel.released,
    )

    # Create card
    result = create_trello_card_core(card_title, card_desc, list_id)
    if not result["success"]:
        print(f"    ERROR: {result['error']}")
        return None

    card_id = result["card_id"]
    card_data = result["card_data"]
    card_url = card_data.get("url", "")
    print(f"    Card created: {card_id}")

    # Post-creation features (fab_order, notes, FC Drawing, mirror for all)
    apply_card_post_creation_features(
        card_id=card_id,
        list_id=list_id,
        job_record=rel,
        fab_order=rel.fab_order,
        notes=rel.notes,
        create_mirror=True,
    )

    # Update DB — use the same function as the normal Excel→Trello flow
    update_job_record_with_trello_data(rel, card_data)

    # Confirm card exists
    verify = get_trello_card_by_id(card_id)
    if verify:
        print(f"    Confirmed on board in list: {list_name}")
    else:
        print(f"    WARNING: Could not verify card {card_id}")

    return {
        "job": rel.job,
        "release": rel.release,
        "job_name": rel.job_name or "",
        "description": rel.description or "",
        "stage": rel.stage or "",
        "trello_list": list_name,
        "trello_card_id": card_id,
        "trello_card_url": card_url,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def run(dry_run=False):
    """Find truly missing releases and interactively create cards."""
    print(f"\n{'=' * 70}")
    print("  CREATE MISSING TRELLO CARDS")
    print(f"{'=' * 70}")
    print(f"  Database: {db.engine.url}")
    if dry_run:
        print("  Mode: DRY RUN (no cards will be created)")

    truly_missing = _find_truly_missing()

    if not truly_missing:
        print(f"\n  All releases have Trello cards. Nothing to do.")
        print(f"{'=' * 70}\n")
        return

    # Display summary
    print(f"\n  {'#':<4} {'Job-Rel':<14} {'Name':<25} {'Stage':<28} {'Target List'}")
    print("  " + "-" * 95)
    for i, rel in enumerate(truly_missing, 1):
        target = get_expected_trello_list_from_stage(rel.stage) or "Released"
        print(
            f"  {i:<4} {rel.job}-{rel.release:<8} "
            f"{(rel.job_name or '')[:23]:<25} "
            f"{(rel.stage or '(none)')[:26]:<28} "
            f"{target}"
        )

    if dry_run:
        print(f"\n  [DRY RUN] {len(truly_missing)} cards would be created.")
        print(f"{'=' * 70}\n")
        return

    # Interactive loop
    created = []
    skipped = 0
    print(f"\n  Ready to create {len(truly_missing)} cards. [y]es / [n]o / [q]uit\n")

    for i, rel in enumerate(truly_missing, 1):
        target = get_expected_trello_list_from_stage(rel.stage) or "Released"
        print(f"  [{i}/{len(truly_missing)}] {rel.job}-{rel.release} "
              f"{(rel.job_name or '')[:25]} | {(rel.description or '')[:25]}")
        print(f"           stage={rel.stage or '(none)'} → list={target}"
              f"  fab_order={rel.fab_order or 'None'}")

        while True:
            choice = input("    Create card? [y/n/q]: ").strip().lower()
            if choice in ("y", "n", "q"):
                break
            print("    Please enter y, n, or q")

        if choice == "q":
            print("    Quitting.")
            break
        if choice == "n":
            skipped += 1
            print("    Skipped.")
            continue

        info = _create_card_for_release(rel)
        if info:
            created.append(info)

    # Write CSV report
    if created:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", f"created_cards_{ts}.csv"
        )
        csv_path = os.path.normpath(csv_path)
        fieldnames = [
            "job", "release", "job_name", "description", "stage",
            "trello_list", "trello_card_id", "trello_card_url", "created_at",
        ]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(created)
        print(f"\n  Report written to: {csv_path}")

    # Summary
    print(f"\n  Created: {len(created)}  Skipped: {skipped}  "
          f"Remaining: {len(truly_missing) - len(created) - skipped}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Interactively create Trello cards for missing releases"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, no cards created")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        run(dry_run=args.dry_run)
