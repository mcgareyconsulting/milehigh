"""
Create a user in the users table using the app's password hashing.
Use this instead of raw SQL so the hash is stored correctly (e.g. for PostgreSQL).

Usage:
  python -m app.scripts.create_user myusername mypassword
  python -m app.scripts.create_user myusername mypassword --admin

Uses ENVIRONMENT / .env to pick the database (local, sandbox, or production).
"""

import argparse
import sys


def create_user(username: str, password: str, admin: bool = False) -> int:
    from app import create_app
    from app.models import User, db
    from app.auth.utils import hash_password

    app = create_app()
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"User {username!r} already exists.")
            return 1
        user = User(
            username=username,
            password_hash=hash_password(password),
            is_active=True,
            is_admin=admin,
        )
        db.session.add(user)
        db.session.commit()
        print(f"Created user {username!r} (id={user.id}, admin={admin})")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Create a user with a properly hashed password",
        epilog="Example: python -m app.scripts.create_user jdoe secretpass --admin",
    )
    parser.add_argument("username", help="Login username")
    parser.add_argument("password", help="Password (will be hashed)")
    parser.add_argument("--admin", action="store_true", help="Grant admin privileges")
    args = parser.parse_args()
    return create_user(args.username, args.password, admin=args.admin)


if __name__ == "__main__":
    sys.exit(main())
