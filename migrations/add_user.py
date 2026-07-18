"""
Add (or update) a single user in the users table.

Follows the seed_users_from_json.py pattern:
  - Match existing user by username (email, case-insensitive), then procore_id
  - If found: update only the fields explicitly passed on the CLI
  - If not found: create with username=email.lower() and a random password;
    password_set stays False so the first-login set-password flow kicks in
    (login page -> /api/auth/check-user -> /api/auth/set-password)

Safe to re-run (existing user with no field changes is a no-op).

Usage:
    python migrations/add_user.py kpowell@mhmw.com --first-name Kim --last-name Powell
    python migrations/add_user.py kpowell@mhmw.com --first-name Kim --last-name Powell --dry-run
    ENVIRONMENT=production python migrations/add_user.py kpowell@mhmw.com --first-name Kim --last-name Powell

Optional flags: --procore-id, --admin, --drafter, --bb-chat
"""

import os
import sys
import uuid

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from app import create_app
from app.models import User, db
from app.auth.utils import hash_password


def add_user(email, first_name=None, last_name=None, procore_id=None,
             is_admin=False, is_drafter=False, is_bb_chat=False,
             dry_run=False):
    email = email.lower().strip()
    app = create_app()
    with app.app_context():
        env = os.environ.get("ENVIRONMENT", "local")
        print(f"Environment: {env}")

        user = User.query.filter(
            db.func.lower(User.username) == email
        ).first()
        if user is None and procore_id:
            user = User.query.filter_by(procore_id=str(procore_id)).first()

        if user:
            changed = []
            for field, value in [
                ("first_name", first_name),
                ("last_name", last_name),
                ("procore_id", str(procore_id) if procore_id else None),
            ]:
                if value is not None and getattr(user, field) != value:
                    setattr(user, field, value)
                    changed.append(field)
            for flag, value in [
                ("is_admin", is_admin),
                ("is_drafter", is_drafter),
                ("is_bb_chat", is_bb_chat),
            ]:
                if value and not getattr(user, flag):
                    setattr(user, flag, True)
                    changed.append(flag)
            if not user.is_active:
                user.is_active = True
                changed.append("is_active")

            if changed:
                print(f"  {'[DRY RUN] ' if dry_run else ''}updating {email}: {', '.join(changed)}")
                if not dry_run:
                    db.session.add(user)
                    db.session.commit()
            else:
                print(f"  no change: {email} (id={user.id})")
        else:
            print(f"  {'[DRY RUN] ' if dry_run else ''}creating: {email}"
                  f" (admin={is_admin}, drafter={is_drafter}, bb_chat={is_bb_chat})")
            if not dry_run:
                new_user = User(
                    username=email,
                    password_hash=hash_password(uuid.uuid4().hex),
                    first_name=first_name,
                    last_name=last_name,
                    procore_id=str(procore_id) if procore_id else None,
                    is_active=True,
                    is_admin=is_admin,
                    is_drafter=is_drafter,
                    is_bb_chat=is_bb_chat,
                )
                db.session.add(new_user)
                db.session.commit()
                print(f"  ✓ created (id={new_user.id}); user sets their own password on first login")

    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Add or update a single user.")
    parser.add_argument("email", help="User email (becomes username, lowercased)")
    parser.add_argument("--first-name")
    parser.add_argument("--last-name")
    parser.add_argument("--procore-id")
    parser.add_argument("--admin", action="store_true", help="Grant is_admin")
    parser.add_argument("--drafter", action="store_true", help="Grant is_drafter")
    parser.add_argument("--bb-chat", action="store_true", help="Grant is_bb_chat")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    try:
        add_user(
            args.email,
            first_name=args.first_name,
            last_name=args.last_name,
            procore_id=args.procore_id,
            is_admin=args.admin,
            is_drafter=args.drafter,
            is_bb_chat=args.bb_chat,
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
