"""
Create (or update) a subcontractor login for hand-testing the sub portal.

Upserts ONE Subcontractor row by email: sets the password, activates the account,
and scopes it to an installer crew (validated against the roster the admin Crew
picker offers, so the account sees exactly what a real scoped account would).

Dry-run by default — prints what it would do. Pass --apply to write.

    .venv/bin/python -m scripts.seed_subcontractor_login \\
        --email sam@acme.test --password 'pick-a-real-one' \\
        --company "Acme Install" --contact "Sam Sub" --crew "Saul 2" --apply

Respects ENVIRONMENT from .env (local / sandbox / production) like the app does.
Never prints the password back.
"""
import argparse
from datetime import datetime

from app import create_app
from app.auth.utils import hash_password
from app.brain.subs.service import assignable_installer_teams
from app.models import Subcontractor, db


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True, help="min 8 chars, same rule as accept-invite")
    parser.add_argument("--company", default=None, help="company_name (required when creating)")
    parser.add_argument("--contact", default=None, help="contact_name (required when creating)")
    parser.add_argument("--crew", default=None, help="installer crew to scope to (only needed when the company is not in SUB_COMPANY_CREWS)")
    parser.add_argument("--phone", default=None, help="contact phone")
    parser.add_argument("--apply", action="store_true", help="Write the row. Default is dry-run.")
    args = parser.parse_args()

    if len(args.password) < 8:
        parser.error("--password must be at least 8 characters")

    app = create_app()
    with app.app_context():
        print(f"environment: {app.config.get('ENVIRONMENT')}  db host: {db.engine.url.host or 'sqlite'}")
        email = args.email.strip().lower()
        sub = Subcontractor.query.filter_by(email=email).first()

        crew = None
        if args.crew:
            roster = assignable_installer_teams()
            crew = next((t for t in roster if t.casefold() == args.crew.strip().casefold()), None)
            if crew is None:
                parser.error(f"--crew {args.crew!r} is not assignable. Roster: {roster}")

        if sub is None:
            if not (args.company and args.contact):
                parser.error("--company and --contact are required to create a new account")
            print(f"CREATE subcontractor email={email} company={args.company!r} "
                  f"contact={args.contact!r} crew={crew!r}")
        else:
            print(f"UPDATE subcontractor id={sub.id} email={email} "
                  f"(company={sub.company_name!r}, contact={sub.contact_name!r}, "
                  f"crew {sub.installer_team!r} -> {crew if args.crew else sub.installer_team!r}, "
                  f"active {sub.is_active} -> True, password reset)")

        if not args.apply:
            print("Dry-run: nothing written. Re-run with --apply.")
            return

        now = datetime.utcnow()
        if sub is None:
            sub = Subcontractor(
                company_name=args.company.strip(),
                contact_name=args.contact.strip(),
                email=email,
                invited_at=now,
            )
            db.session.add(sub)
        else:
            if args.company:
                sub.company_name = args.company.strip()
            if args.contact:
                sub.contact_name = args.contact.strip()
        if args.phone:
            sub.phone = args.phone.strip()
        sub.password_hash = hash_password(args.password)
        sub.is_active = True
        sub.invite_accepted_at = sub.invite_accepted_at or now
        sub.invite_token_hash = None
        sub.invite_token_expires_at = None
        if args.crew:
            sub.installer_team = crew
        db.session.commit()
        print(f"OK subcontractor id={sub.id} ready: sign in at /sub/login with {email}")


if __name__ == "__main__":
    main()
