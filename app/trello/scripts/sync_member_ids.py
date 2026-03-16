"""
Script to sync Trello board member IDs into the local users table.

Fetches all board members from Trello, matches them against local User records
by full name (first_name + last_name vs Trello fullName, case-insensitive),
and writes the Trello member ID to user.trello_id.

Usage:
    python -m app.trello.scripts.sync_member_ids [--dry-run] [--force]

Flags:
    --dry-run   Print what would change without committing to the database
    --force     Overwrite trello_id even if it is already set
"""

import argparse
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import db, User
from app.trello.api import get_membership_by_board, get_member_by_id


def build_member_lookup():
    """Return a dict keyed by normalized fullName → full member object."""
    memberships = get_membership_by_board()
    lookup = {}
    for m in memberships:
        member = get_member_by_id(m["idMember"])
        full_name = (member.get("fullName") or "").strip().lower()
        if full_name:
            lookup[full_name] = member
    return lookup


def main():
    parser = argparse.ArgumentParser(
        description="Sync Trello board member IDs into the local users table",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview matches without writing
  python -m app.trello.scripts.sync_member_ids --dry-run

  # Apply updates
  python -m app.trello.scripts.sync_member_ids

  # Overwrite existing trello_id values
  python -m app.trello.scripts.sync_member_ids --force
        """,
    )
    parser.add_argument("--dry-run", action="store_true", help="Print changes without committing")
    parser.add_argument("--force", action="store_true", help="Overwrite existing trello_id values")
    args = parser.parse_args()

    print("Fetching Trello board members...")
    members = build_member_lookup()
    print(f"  Found {len(members)} board member(s): {', '.join(members.keys())}")

    print()

    app = create_app()
    with app.app_context():
        users = User.query.all()

        matched = []
        skipped = []
        unmatched = []

        for user in users:
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip().lower()
            trello_member = members.get(full_name)

            # Fallback: Trello member only has a first name — match against user.first_name
            if trello_member is None:
                first = (user.first_name or "").strip().lower()
                trello_member = members.get(first)

            if trello_member is None:
                unmatched.append(f"{user.username} ({full_name or 'no name'})")
                continue

            if user.trello_id and not args.force:
                skipped.append((user.username, user.trello_id))
                continue

            matched.append((user, trello_member))

        # Apply updates
        for user, member in matched:
            old_id = user.trello_id
            if not args.dry_run:
                user.trello_id = member["id"]
            action = "[DRY RUN] would set" if args.dry_run else "set"
            old_str = f" (was: {old_id})" if old_id else ""
            print(f"  {action} trello_id for '{user.username}'{old_str} → {member['id']}")

        if not args.dry_run and matched:
            db.session.commit()

        # Summary
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Matched / updated : {len(matched)}")
        print(f"  Skipped (already set, no --force): {len(skipped)}")
        print(f"  Unmatched (no Trello member found): {len(unmatched)}")

        if skipped:
            print()
            print("Skipped users:")
            for username, existing_id in skipped:
                print(f"  {username} → {existing_id}")

        if unmatched:
            print()
            print("Unmatched users (no Trello board member with same full name):")
            for username in unmatched:
                print(f"  {username}")

        if args.dry_run:
            print()
            print("(dry run — no changes written)")


if __name__ == "__main__":
    main()
