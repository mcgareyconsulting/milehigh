"""
@milehigh-header
schema_version: 1
purpose: Populate missing Trello metadata on Releases rows by matching cards from the board to DB records.
exports:
  backfill: Match active releases to Trello cards and backfill 7 Trello columns.
  _apply_trello_fields: Set Trello columns on a release from a card dict, returning changes.
  _parse_job_release: Extract (job_int, release_str) tuple from a Trello card name.
imports_from: [app, app.models, app.trello.api, app.trello.utils, dotenv, argparse]
imported_by: []
invariants:
  - Read-only on Trello; only writes to the local DB.
  - Supports --dry-run to preview without committing.
  - Requires Flask app context (created via create_app at __main__).
  - Invoked directly: python -m app.trello.scripts.backfill_trello_data [--dry-run]
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Backfill Trello card data onto the Releases table.

Fetches all cards from primary Trello lists, matches them to active
releases by card ID or name pattern, and updates the 7 Trello columns
on each matched release. Read-only on Trello — only writes to the DB.

Usage:
    python -m app.trello.scripts.backfill_trello_data [--dry-run]
"""

import argparse
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import Releases, db
from app.trello.api import get_all_trello_cards
from app.trello.utils import parse_trello_datetime


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


def _apply_trello_fields(release, card):
    """Set the 7 Trello columns on a release from a card dict.

    Returns list of (field, old, new) for fields that changed.
    """
    changes = []
    mapping = [
        ("trello_card_id", card["id"]),
        ("trello_card_name", card["name"]),
        ("trello_list_id", card["list_id"]),
        ("trello_list_name", card["list_name"]),
        ("trello_card_description", card.get("desc", "")),
    ]

    # Parse due date
    due_val = card.get("due")
    if due_val:
        parsed = parse_trello_datetime(due_val)
        new_date = parsed.date() if parsed else None
    else:
        new_date = None
    mapping.append(("trello_card_date", new_date))

    for field, new_val in mapping:
        old_val = getattr(release, field)
        if str(old_val or "") != str(new_val or ""):
            changes.append((field, old_val, new_val))
        setattr(release, field, new_val)

    return changes


def backfill(dry_run=False):
    """Match active releases to Trello cards and backfill Trello columns."""
    print(f"\n{'=' * 70}")
    print("  BACKFILL TRELLO DATA ONTO RELEASES")
    print(f"{'=' * 70}")
    print(f"  Database: {db.engine.url}")
    if dry_run:
        print("  Mode: DRY RUN (no DB changes)")

    # Fetch cards
    print("  Fetching Trello cards...")
    all_cards = get_all_trello_cards()
    primary_cards = [c for c in all_cards if c["list_name"] in PRIMARY_LISTS]
    print(f"  Total cards on board:     {len(all_cards)}")
    print(f"  Cards in primary lists:   {len(primary_cards)}")

    # Build lookups
    card_by_id = {c["id"]: c for c in primary_cards}
    card_by_key = {}
    duplicates = []
    for c in primary_cards:
        parsed = _parse_job_release(c["name"])
        if parsed:
            if parsed in card_by_key:
                duplicates.append((parsed, card_by_key[parsed], c))
            else:
                card_by_key[parsed] = c

    if duplicates:
        print(f"\n  WARNING: {len(duplicates)} duplicate card matches:")
        for key, c1, c2 in duplicates:
            print(f"    {key[0]}-{key[1]}: '{c1['name'][:30]}' in {c1['list_name']}"
                  f" vs '{c2['name'][:30]}' in {c2['list_name']}")

    # Load releases
    active_releases = Releases.query.filter(Releases.is_archived == False).all()
    print(f"  Active Releases:          {len(active_releases)}")

    # Match and backfill
    matched_by_id = 0
    matched_by_name = 0
    unmatched = []
    updated_count = 0
    total_field_changes = 0

    for rel in sorted(active_releases, key=lambda r: (r.job, str(r.release))):
        card = None

        # Try by existing card ID
        if rel.trello_card_id:
            card = card_by_id.get(rel.trello_card_id)
            if card:
                matched_by_id += 1

        # Fallback to name parse
        if not card:
            key = (rel.job, str(rel.release))
            card = card_by_key.get(key)
            if card:
                matched_by_name += 1

        if not card:
            unmatched.append(rel)
            continue

        changes = _apply_trello_fields(rel, card)
        if changes:
            updated_count += 1
            total_field_changes += len(changes)

    total_matched = matched_by_id + matched_by_name

    # Report
    print(f"\n  Matched:                  {total_matched}")
    print(f"    By card_id:             {matched_by_id}")
    print(f"    By name parse:          {matched_by_name}")
    prefix = "Would update" if dry_run else "Updated"
    print(f"  {prefix}:          {updated_count} releases ({total_field_changes} field changes)")
    print(f"  Unmatched:                {len(unmatched)}")

    if unmatched:
        print(f"\n  UNMATCHED RELEASES:")
        print(f"  {'Job-Rel':<14} {'Name':<30} {'Has card_id?'}")
        print("  " + "-" * 60)
        for rel in unmatched:
            has_id = "Yes" if rel.trello_card_id else "No"
            print(f"  {rel.job}-{str(rel.release):<8} {(rel.job_name or '')[:28]:<30} {has_id}")

    # Commit
    if not dry_run and (updated_count > 0):
        db.session.commit()
        print(f"\n  Committed {updated_count} release updates.")
    elif dry_run:
        db.session.rollback()

    print(f"\n{'=' * 70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Trello data onto Releases table")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no DB changes")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        backfill(dry_run=args.dry_run)
