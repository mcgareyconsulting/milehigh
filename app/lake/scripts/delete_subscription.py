"""Delete Graph change-notification subscriptions — cleanup for dev/reprovision.

Every ngrok restart orphans the previous subscription (Graph keeps POSTing at a
dead tunnel), so this is the "start fresh" tool. It lists what Graph currently
holds for this app, then deletes either one id, our stored BB-mail one, or all.

Usage:
    # Show every subscription this app owns (no deletion)
    python -m app.lake.scripts.delete_subscription --list

    # Delete one specific subscription
    python -m app.lake.scripts.delete_subscription --subscription-id <id>

    # Delete our stored BB-mail subscription (default)
    python -m app.lake.scripts.delete_subscription

    # Delete ALL subscriptions this app owns (clears orphaned ngrok ones)
    python -m app.lake.scripts.delete_subscription --all
"""
import argparse
import os

# This one-off may run in a prod shell where IS_RENDER_SCHEDULER is set; never let
# create_app() boot a second background scheduler against prod (mirrors
# app/procore/scripts/reconcile_bic.py).
os.environ.pop("IS_RENDER_SCHEDULER", None)
os.environ.pop("WERKZEUG_RUN_MAIN", None)

from app import create_app
from app.lake.ingest import graph_subscription
from app.lake.ingest.m365_mail import SOURCE
from app.models import GraphSubscription


def _print_remote(subs):
    if not subs:
        print("(no subscriptions currently held by this app)")
        return
    print(f"{len(subs)} subscription(s) held by this app:")
    for s in subs:
        print(f"  - {s.get('id')}  exp={s.get('expirationDateTime')}")
        print(f"      resource: {s.get('resource')}")
        print(f"      notifyUrl: {s.get('notificationUrl')}")


def main():
    parser = argparse.ArgumentParser(description="Delete BB-mail Graph subscription(s).")
    parser.add_argument("--subscription-id", help="Delete this specific subscription id.")
    parser.add_argument("--all", action="store_true", help="Delete ALL subscriptions this app owns.")
    parser.add_argument("--list", action="store_true", help="List subscriptions and exit (no deletion).")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        remote = graph_subscription.list_remote()
        _print_remote(remote)
        if args.list:
            return

        # Decide the target set.
        if args.subscription_id:
            targets = [args.subscription_id]
        elif args.all:
            targets = [s.get("id") for s in remote if s.get("id")]
        else:
            row = GraphSubscription.query.filter_by(source=SOURCE).first()
            if row is None or not row.subscription_id:
                print("\nNo stored BB-mail subscription to delete. "
                      "Use --subscription-id or --all to target Graph directly.")
                return
            targets = [row.subscription_id]

        if not targets:
            print("\nNothing to delete.")
            return

        print(f"\nWill delete {len(targets)} subscription(s): {targets}")
        if not args.yes:
            resp = input("Proceed? (yes/no): ")
            if resp.lower() != "yes":
                print("Cancelled.")
                return

        for sub_id in targets:
            graph_subscription.delete_subscription(sub_id)
            print(f"✓ deleted {sub_id}")


if __name__ == "__main__":
    main()
