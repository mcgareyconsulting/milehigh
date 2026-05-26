"""
One-off prod data fix: set the Trello member id for the Fab Shop user.

The Fab Shop account couldn't be auto-matched by sync_member_ids because its
DB name ("Fab Shop") differs from its Trello fullName ("fabshop"). The id below
was confirmed directly from the production Trello board membership:
    username=fabshop16  fullName=fabshop  id=646cd06fb7d7d5648494ab82

Guarded + idempotent: only updates users.id=26 when trello_id IS NULL, and
refuses if another user already holds the target id.

Usage:
    python scripts/set_fabshop_trello_id.py --yes
"""
import argparse
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app.config  # noqa: F401  (loads .env)
from app.db_config import get_database_config
from sqlalchemy import create_engine, text

USER_ID = 26
USER_USERNAME = "fabshop@mhmw.com"
TARGET_TID = "646cd06fb7d7d5648494ab82"


def main():
    parser = argparse.ArgumentParser(description="Set Fab Shop trello_id (sandbox or production).")
    parser.add_argument("-y", "--yes", action="store_true", help="Apply the update.")
    parser.add_argument("--env", choices=["sandbox", "production"], default="production",
                        help="Target database environment (default: production).")
    args = parser.parse_args()

    url, _ = get_database_config(args.env)
    print(f"ENV: {args.env}")
    red = url
    if "@" in red:
        scheme, rest = red.split("://", 1)
        creds, host = rest.split("@", 1)
        red = f"{scheme}://{creds.split(':', 1)[0]}:***@{host}"
    print(f"{args.env.upper()} DB: {red}")

    eng = create_engine(url, connect_args={"sslmode": "require", "connect_timeout": 10})
    try:
        with eng.connect() as c:
            target = c.execute(text(
                "SELECT id, first_name, last_name, username, trello_id FROM users WHERE id=:i"
            ), {"i": USER_ID}).fetchone()
            if not target:
                print(f"✗ No user with id={USER_ID}. Aborting.")
                return 1
            if target[3] != USER_USERNAME:
                print(f"✗ Safety check failed: id={USER_ID} username is {target[3]!r}, "
                      f"expected {USER_USERNAME!r}. Aborting.")
                return 1
            print(f"User: id={target[0]} {target[1]} {target[2]} ({target[3]}) "
                  f"current trello_id={target[4] or '— NONE —'}")

            holder = c.execute(text("SELECT id, username FROM users WHERE trello_id=:t"),
                               {"t": TARGET_TID}).fetchone()
            if holder and holder[0] != USER_ID:
                print(f"✗ trello_id {TARGET_TID} already held by id={holder[0]} ({holder[1]}). Aborting.")
                return 1
            if target[4] == TARGET_TID:
                print("✓ Already set. Nothing to do.")
                return 0
            if target[4]:
                print(f"✗ User already has a different trello_id ({target[4]}). Aborting (not overwriting).")
                return 1

        if not args.yes:
            print("\n(dry run — pass --yes to apply)")
            return 0

        with eng.begin() as c:
            res = c.execute(text(
                "UPDATE users SET trello_id=:t WHERE id=:i AND trello_id IS NULL"
            ), {"t": TARGET_TID, "i": USER_ID})
            print(f"rows updated: {res.rowcount}")
            row = c.execute(text(
                "SELECT id, username, trello_id FROM users WHERE id=:i"
            ), {"i": USER_ID}).fetchone()
            print(f"✓ verify → id={row[0]} username={row[1]} trello_id={row[2]}")
        return 0
    finally:
        eng.dispose()


if __name__ == "__main__":
    sys.exit(main())
