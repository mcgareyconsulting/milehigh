"""
Backfill internal_user_id on ReleaseEvents sourced from Trello.

Finds all ReleaseEvents where source="Trello" and internal_user_id is NULL,
then looks up the external_user_id against users.trello_id and sets
internal_user_id from the matched user record.

Usage:
    python -m app.trello.scripts.backfill_release_event_users [--dry-run]
"""

import argparse
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import db, User, ReleaseEvents


def main():
    parser = argparse.ArgumentParser(
        description="Backfill internal_user_id on Trello-sourced ReleaseEvents",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print changes without committing")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        events = (
            ReleaseEvents.query
            .filter(
                ReleaseEvents.source == "Trello",
                ReleaseEvents.internal_user_id.is_(None),
                ReleaseEvents.external_user_id.isnot(None),
            )
            .all()
        )

        print(f"Found {len(events)} Trello ReleaseEvent(s) with no internal_user_id.")

        if not events:
            return

        # Build trello_id → User lookup
        trello_ids = {e.external_user_id for e in events}
        users = User.query.filter(User.trello_id.in_(trello_ids)).all()
        user_by_trello_id = {u.trello_id: u for u in users}

        print(f"Matched {len(user_by_trello_id)} unique Trello ID(s) to local users.")
        print()

        updated = []
        unmatched_ids = defaultdict(int)

        for event in events:
            user = user_by_trello_id.get(event.external_user_id)
            if user is None:
                unmatched_ids[event.external_user_id] += 1
                continue

            action = "[DRY RUN] would set" if args.dry_run else "set"
            print(f"  {action} internal_user_id={user.id} ({user.username}) on event id={event.id} (external={event.external_user_id})")

            if not args.dry_run:
                event.internal_user_id = user.id

            updated.append(event)

        if not args.dry_run and updated:
            db.session.commit()

        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Updated : {len(updated)}")
        print(f"  No matching user (trello_id not in users table): {sum(unmatched_ids.values())}")

        if unmatched_ids:
            print()
            print("Unmatched Trello IDs:")
            for trello_id, count in sorted(unmatched_ids.items()):
                print(f"  {trello_id}  ({count} event(s))")

        if args.dry_run:
            print()
            print("(dry run — no changes written)")


if __name__ == "__main__":
    main()
