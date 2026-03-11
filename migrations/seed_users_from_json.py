"""
Ingest docs/users.json into the users table.

For each entry:
  - Match existing user by username (email, case-insensitive) or procore_id
  - If found: update first_name, last_name, procore_id
  - If not found: create with username=email.lower(), random password,
    first_name, last_name, procore_id (user must set their own password later)

Usage:
    python migrations/seed_users_from_json.py
    python migrations/seed_users_from_json.py --dry-run
"""

import json
import os
import sys
import uuid

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from app import create_app
from app.models import User, db
from app.auth.utils import hash_password

USERS_JSON = os.path.join(ROOT_DIR, "docs", "users.json")


def seed(dry_run: bool = False) -> bool:
    with open(USERS_JSON) as f:
        entries = json.load(f)

    app = create_app()
    with app.app_context():
        created, updated, skipped = 0, 0, 0

        for entry in entries:
            email = entry["email"].lower()
            first_name = entry["first_name"]
            last_name = entry["last_name"]
            procore_id = str(entry["procore_id"]) if entry.get("procore_id") else None

            # Match by procore_id first, then username
            user = None
            if procore_id:
                user = User.query.filter_by(procore_id=procore_id).first()
            if user is None:
                user = User.query.filter(
                    db.func.lower(User.username) == email
                ).first()

            if user:
                changed = False
                if user.first_name != first_name:
                    user.first_name = first_name
                    changed = True
                if user.last_name != last_name:
                    user.last_name = last_name
                    changed = True
                if procore_id and user.procore_id != procore_id:
                    user.procore_id = procore_id
                    changed = True

                if changed:
                    status = "updated"
                    updated += 1
                else:
                    status = "no change"
                    skipped += 1

                print(f"  {'[DRY RUN] ' if dry_run else ''}{status}: {email}")
                if not dry_run and changed:
                    db.session.add(user)
            else:
                # Create new user with a random password
                print(f"  {'[DRY RUN] ' if dry_run else ''}creating: {email}")
                if not dry_run:
                    random_pw = uuid.uuid4().hex
                    new_user = User(
                        username=email,
                        password_hash=hash_password(random_pw),
                        first_name=first_name,
                        last_name=last_name,
                        procore_id=procore_id,
                        is_active=True,
                        is_admin=False,
                    )
                    db.session.add(new_user)
                created += 1

        if not dry_run:
            db.session.commit()
            print(f"\n✓ Done: {created} created, {updated} updated, {skipped} unchanged.")
        else:
            print(f"\n[DRY RUN] Would: {created} create, {updated} update, {skipped} unchanged.")

    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed users table from docs/users.json.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    try:
        seed(dry_run=args.dry_run)
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
