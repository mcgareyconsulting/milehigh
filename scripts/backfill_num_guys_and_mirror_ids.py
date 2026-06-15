"""
One-off script: backfill Releases.num_guys and Releases.mirror_trello_card_id.

 - num_guys: parsed from each release's stored Trello card description
   ("**Number of Guys:** N"). Rows with no parseable value are left NULL (the
   comp_eta formula treats NULL as the default of 2).
 - mirror_trello_card_id: resolved from the primary card's "Linked card"
   attachment (mirror shortLink) → the mirror's full card id, so inbound mirror
   webhooks can match the release directly.

Run the two column migrations first:
    python migrations/add_num_guys_to_releases.py
    python migrations/add_mirror_trello_card_id_to_releases.py

Scope: ACTIVE releases only (not archived, not soft-deleted). Archived rows are not
worth the per-row Trello API calls — they never become installer-team editing surfaces.

Usage:
    .venv/bin/python -m scripts.backfill_num_guys_and_mirror_ids           # dry-run, prints diff
    .venv/bin/python -m scripts.backfill_num_guys_and_mirror_ids --apply   # commits changes

Idempotent: re-running only fills values that are still missing/changed.
"""

import argparse
import sys

from app import create_app
from app.config import Config as cfg
from app.models import Releases, db
from app.trello.api import (
    parse_num_guys_from_description,
    get_card_attachments_by_card_id,
    get_trello_card_by_id,
    _mirror_short_link_from_attachments,
)


def resolve_mirror_card_id(primary_card_id):
    """Return the mirror card's full id for a primary card, or None.

    Rejects a "Linked card" attachment that points to a card on a different board —
    shortLinks are global, so a stray/cross-board link would otherwise resolve to the
    wrong card. The idBoard rides along in the card fetch we already make (no extra call).
    """
    result = get_card_attachments_by_card_id(primary_card_id)
    if not result.get("success"):
        return None
    short_link = _mirror_short_link_from_attachments(result.get("attachments"))
    if not short_link:
        return None
    mirror = get_trello_card_by_id(short_link)
    if not mirror:
        return None
    if mirror.get("idBoard") != cfg.TRELLO_BOARD_ID:
        print(f"  ! skipping cross-board linked card {mirror.get('id')} (board {mirror.get('idBoard')})")
        return None
    return mirror.get("id")


def run(apply: bool):
    app = create_app()
    with app.app_context():
        # Active working set only: skip archived and soft-deleted rows.
        releases = Releases.query.filter(
            Releases.is_archived.isnot(True),
            Releases.is_active.isnot(False),
        ).all()
        num_guys_updates = 0
        mirror_updates = 0
        errors = 0

        for rec in releases:
            tag = f"{rec.job}-{rec.release}"

            # num_guys from the stored description
            if rec.trello_card_description:
                parsed = parse_num_guys_from_description(rec.trello_card_description)
                if parsed and rec.num_guys != parsed:
                    print(f"  num_guys {tag}: {rec.num_guys} -> {parsed}")
                    rec.num_guys = parsed
                    num_guys_updates += 1

            # mirror_trello_card_id from the "Linked card" attachment
            if rec.trello_card_id and not rec.mirror_trello_card_id:
                try:
                    mirror_id = resolve_mirror_card_id(rec.trello_card_id)
                    if mirror_id:
                        print(f"  mirror {tag}: -> {mirror_id}")
                        rec.mirror_trello_card_id = mirror_id
                        mirror_updates += 1
                except Exception as e:
                    print(f"  ! mirror lookup failed for {tag}: {e}", file=sys.stderr)
                    errors += 1

        print(
            f"\nActive releases scanned: {len(releases)} | "
            f"num_guys updates: {num_guys_updates} | "
            f"mirror id updates: {mirror_updates} | errors: {errors}"
        )

        if apply:
            db.session.commit()
            print("Committed.")
        else:
            db.session.rollback()
            print("Dry-run — no changes written. Re-run with --apply to commit.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill num_guys and mirror_trello_card_id on releases.")
    parser.add_argument("--apply", action="store_true", help="Commit changes (default is dry-run).")
    args = parser.parse_args()
    run(args.apply)
