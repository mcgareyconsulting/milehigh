"""Local-only demo bootstrap for the meeting -> checklist demo.

Creates the full schema (incl. meetings/checklist_items) in the LOCAL sqlite db and
seeds the reviewer/admin + an owner roster so the Opus extractor's owner_name values
resolve to real User rows. Run with ENVIRONMENT=local so it never touches sandbox.

    ENVIRONMENT=local python demo_bootstrap.py
"""
import os

assert os.environ.get("ENVIRONMENT", "").lower() == "local", \
    "Refusing to run unless ENVIRONMENT=local (safety: do not seed sandbox/prod)."

from app import create_app
from app.models import db, User
from app.auth.utils import hash_password

DEMO_PASSWORD = "demo"

# (username, first_name, last_name, is_admin) — first_name is what owner-resolution
# matches on (case-insensitive). Reviewer must be boneill@mhmw.com per config default.
ROSTER = [
    ("boneill@mhmw.com", "Bill", "O'Neill", True),   # admin + reviewer + login
    ("danny@mhmw.com",   "Danny",  "",  True),
    ("gary@mhmw.com",    "Gary",   "Almeida", False),
    ("jay@mhmw.com",     "Jay",    "", False),
    ("greg@mhmw.com",    "Greg",   "", False),
    ("eduardo@mhmw.com", "Eduardo","", False),
    ("benny@mhmw.com",   "Benny",  "", False),
    ("garrett@mhmw.com", "Garrett","", False),
    ("tyler@mhmw.com",   "Tyler",  "", False),
    ("doug@mhmw.com",    "Doug",   "", False),
    ("jake@mhmw.com",    "Jake",   "", False),
    ("mike@mhmw.com",    "Mike",   "Fogg", False),
    ("colton@mhmw.com",  "Colton", "", False),
    ("natalie@mhmw.com", "Natalie","", False),
    ("sal@mhmw.com",     "Sal",    "", False),
    ("zach@mhmw.com",    "Zach",   "", False),
    ("dalton@mhmw.com",  "Dalton", "Rauer", False),
    ("luis@mhmw.com",    "Luis",   "Solano", False),
    ("david@mhmw.com",   "David",  "Servold", True),
    ("laura@mhmw.com",   "Laura",  "", False),
]


def main():
    app = create_app()
    with app.app_context():
        db.create_all()  # fresh sqlite -> creates every table incl. meetings/checklist_items
        created = 0
        for username, first, last, is_admin in ROSTER:
            u = User.query.filter_by(username=username).first()
            if u:
                continue
            db.session.add(User(
                username=username, first_name=first, last_name=last,
                password_hash=hash_password(DEMO_PASSWORD),
                password_set=True, is_active=True,
                is_admin=is_admin, is_drafter=False,
            ))
            created += 1
        db.session.commit()
        total = User.query.count()
        print(f"Seeded {created} new users ({total} total). Login: boneill@mhmw.com / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
