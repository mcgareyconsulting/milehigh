"""
Audit active Releases against the Trello board.

Read-only — reports which active Releases are missing cards in the
primary Trello lists, and flags stage mismatches.

Usage:
    python -m app.trello.scripts.audit_releases
"""

import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import Releases, db
from app.trello.api import get_all_trello_cards


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


def audit():
    """Compare active Releases against Trello primary lists."""
    print(f"\n{'=' * 70}")
    print("  RELEASE vs TRELLO AUDIT")
    print(f"{'=' * 70}")
    print(f"  Database: {db.engine.url}")

    active_releases = Releases.query.filter(Releases.is_archived == False).all()
    print(f"  Active Releases:          {len(active_releases)}")

    print("  Fetching Trello cards...")
    board_cards = get_all_trello_cards()
    primary_cards = [c for c in board_cards if c["list_name"] in PRIMARY_LISTS]
    print(f"  Total cards on board:     {len(board_cards)}")
    print(f"  Cards in primary lists:   {len(primary_cards)}")

    # Build Trello lookups (primary lists only)
    card_by_id = {c["id"]: c for c in primary_cards}
    card_by_key = {}
    for c in primary_cards:
        parsed = _parse_job_release(c["name"])
        if parsed:
            card_by_key[parsed] = c

    # Match each active Release to a Trello card
    matched = []
    missing_from_trello = []
    stage_mismatches = []

    for rel in active_releases:
        card = None
        if rel.trello_card_id:
            card = card_by_id.get(rel.trello_card_id)
        if not card:
            key = (rel.job, str(rel.release))
            card = card_by_key.get(key)

        if not card:
            missing_from_trello.append(rel)
        else:
            matched.append((rel, card))
            db_stage = rel.stage or "(none)"
            trello_list = card["list_name"]
            if db_stage != trello_list:
                stage_mismatches.append((rel, db_stage, trello_list))

    print(f"\n  Matched to primary list:  {len(matched)}")
    print(f"  MISSING from board:       {len(missing_from_trello)}")
    print(f"  Stage mismatches:         {len(stage_mismatches)}")

    if missing_from_trello:
        # Check if any of the missing ones exist in non-primary lists
        all_card_by_key = {}
        for c in board_cards:
            parsed = _parse_job_release(c["name"])
            if parsed:
                all_card_by_key.setdefault(parsed, []).append(c)

        found_elsewhere = []
        truly_missing = []
        for rel in sorted(missing_from_trello, key=lambda r: (r.job, r.release)):
            key = (rel.job, str(rel.release))
            if key in all_card_by_key:
                for card in all_card_by_key[key]:
                    found_elsewhere.append((rel, card))
            else:
                truly_missing.append(rel)

        if found_elsewhere:
            print(f"\n  FOUND IN OTHER LISTS ({len(found_elsewhere)}):")
            print(f"  {'Job-Rel':<14} {'Name':<28} {'List':<25} {'DB Stage':<20}")
            print("  " + "-" * 87)
            for rel, card in found_elsewhere:
                print(
                    f"  {rel.job}-{rel.release:<8} "
                    f"{(rel.job_name or '')[:26]:<28} "
                    f"{card['list_name'][:23]:<25} "
                    f"{rel.stage or '(none)'}"
                )

        if truly_missing:
            print(f"\n  TRULY MISSING — NOT ON BOARD AT ALL ({len(truly_missing)}):")
            print(f"  {'Job-Rel':<14} {'Name':<32} {'DB Stage':<25}")
            print("  " + "-" * 71)
            for rel in truly_missing:
                print(
                    f"  {rel.job}-{rel.release:<8} "
                    f"{(rel.job_name or '')[:30]:<32} "
                    f"{rel.stage or '(none)'}"
                )

    if stage_mismatches:
        print(f"\n  STAGE MISMATCHES ({len(stage_mismatches)}):")
        print(f"  {'Job-Rel':<14} {'DB Stage':<25} {'Trello List':<25}")
        print("  " + "-" * 64)
        for rel, db_stage, trello_list in sorted(
            stage_mismatches, key=lambda x: (x[0].job, x[0].release)
        ):
            print(f"  {rel.job}-{rel.release:<8} {db_stage:<25} -> {trello_list:<25}")

    print(f"\n{'=' * 70}")
    print("  AUDIT COMPLETE")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        audit()
