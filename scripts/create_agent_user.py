"""
Create (or update) an AGENT login — a non-human user account for an external bot
(e.g. a Grok agent) that performs actions in the Brain.

Why a separate account: every audit row (ReleaseEvents, SubmittalEvents, board
activity, issue changes, photo uploads, ...) is attributed to the session's
users.id. A bot signed in with an employee's personal credentials is
indistinguishable from that employee. With its own account the bot's rows carry
its own id, and user_display_name() tags it "(agent)" in every events view.

Upserts ONE User row by username (email). Sets password directly (password_set=True,
so the first-login flow never applies), marks is_agent=True, records the sponsoring
employee, and assigns a role. The agent's OWN role flags govern what it may do —
nothing is inherited from the sponsor.

Dry-run by default — prints what it would do. Pass --apply to write.

    .venv/bin/python -m scripts.create_agent_user \\
        --username grok-bot@mhmw.com --name "Grok Bot" \\
        --sponsor doug@mhmw.com --role default \\
        --password 'pick-a-real-one' --apply

Respects ENVIRONMENT from .env (local / sandbox / production) like the app does.
Never prints the password back. Requires migrations/add_agent_users.py to have run.
"""
import argparse

from app import create_app
from app.auth.utils import hash_password
from app.brain.directory.routes import ROLE_FLAGS, employee_role_key
from app.models import User, db


def _split_name(name: str):
    parts = name.strip().split(None, 1)
    if not parts:
        return "", ""
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", required=True, help="login email for the agent, e.g. grok-bot@mhmw.com")
    parser.add_argument("--name", default=None, help='display name, e.g. "Grok Bot" (required when creating)')
    parser.add_argument("--sponsor", default=None, help="username (email) of the employee who vouches for the agent")
    parser.add_argument("--role", default=None, choices=sorted(ROLE_FLAGS),
                        help="permission role (default role 'default' when creating)")
    parser.add_argument("--password", default=None, help="min 8 chars (required when creating)")
    parser.add_argument("--apply", action="store_true", help="Write the row. Default is dry-run.")
    args = parser.parse_args()

    if args.password is not None and len(args.password) < 8:
        parser.error("--password must be at least 8 characters")

    app = create_app()
    with app.app_context():
        print(f"environment: {app.config.get('ENVIRONMENT')}  db host: {db.engine.url.host or 'sqlite'}")
        username = args.username.strip().lower()
        user = User.query.filter(db.func.lower(User.username) == username).first()

        if user is not None and not user.is_agent:
            parser.error(f"{username} exists and is a HUMAN account; refusing to convert it into an agent")

        sponsor = None
        if args.sponsor:
            sponsor = User.query.filter(db.func.lower(User.username) == args.sponsor.strip().lower()).first()
            if sponsor is None:
                parser.error(f"--sponsor {args.sponsor!r} not found")
            if sponsor.is_agent:
                parser.error("--sponsor must be a human account, not another agent")
            if not sponsor.is_active:
                parser.error("--sponsor is an inactive account")

        role = args.role
        if user is None:
            if not (args.name and args.password):
                parser.error("--name and --password are required to create a new agent")
            role = role or "default"
            first, last = _split_name(args.name)
            print(f"CREATE agent username={username} name={args.name!r} role={role} "
                  f"sponsor={sponsor.username if sponsor else None!r}")
        else:
            first, last = _split_name(args.name) if args.name else (user.first_name, user.last_name)
            print(f"UPDATE agent id={user.id} username={username} "
                  f"(name {user.first_name!r} {user.last_name!r} -> {first!r} {last!r}, "
                  f"role {employee_role_key(user)} -> {role or employee_role_key(user)}, "
                  f"sponsor {user.agent_sponsor_user_id!r} -> "
                  f"{sponsor.id if sponsor else user.agent_sponsor_user_id!r}, "
                  f"password {'reset' if args.password else 'unchanged'}, active -> True)")

        if not args.apply:
            print("Dry-run: nothing written. Re-run with --apply.")
            return

        if user is None:
            user = User(
                username=username,
                password_hash=hash_password(args.password),
                password_set=True,
                is_active=True,
                is_agent=True,
                first_name=first,
                last_name=last,
            )
            db.session.add(user)
        else:
            user.first_name, user.last_name = first, last
            if args.password:
                user.password_hash = hash_password(args.password)
                user.password_set = True
        if role:
            user.is_admin, user.is_drafter = ROLE_FLAGS[role]
        if sponsor is not None:
            user.agent_sponsor_user_id = sponsor.id
        user.is_active = True
        db.session.commit()
        print(f"OK agent id={user.id} ready: sign in at /login with {username}; "
              f"its audit rows will read \"{first} {last}\".strip() + \" (agent)\"")


if __name__ == "__main__":
    main()
