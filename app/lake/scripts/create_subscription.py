"""Create a Graph change-notification subscription for the BB mailbox.

This is the "procore-style POST" bootstrap: it fires POST /subscriptions pointing
Graph at GRAPH_NOTIFICATION_URL + /lake/graph/notifications. Graph validates that
URL synchronously, so your Flask app (or ngrok tunnel → local Flask) must be LIVE
and reachable at that URL before you run this.

Prereqs (env / .env):
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET   (app-only Graph)
    GRAPH_NOTIFICATION_URL           e.g. https://abc123.ngrok-free.app
    GRAPH_SUBSCRIPTION_CLIENT_STATE  any secret string you choose
    BB_MAILBOX                       defaults to bb@mhmw.com

Usage:
    python -m app.lake.scripts.create_subscription
    python -m app.lake.scripts.create_subscription --mailbox bb@mhmw.com
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


def main():
    parser = argparse.ArgumentParser(description="Create a BB-mail Graph subscription.")
    parser.add_argument("--mailbox", help="Mailbox to watch (default: BB_MAILBOX).")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        try:
            url = graph_subscription._notification_url()
        except graph_subscription.SubscriptionConfigError as exc:
            print(f"✗ {exc}")
            raise SystemExit(1)

        print(f"Creating subscription → notificationUrl: {url}")
        print("(Graph will validate this URL now — the endpoint must be live.)")
        print("-" * 60)
        try:
            row = graph_subscription.create_subscription(args.mailbox)
        except graph_subscription.SubscriptionConfigError as exc:
            print(f"✗ {exc}")
            raise SystemExit(1)

        print("✓ Subscription created")
        print(f"  subscription_id: {row.subscription_id}")
        print(f"  mailbox:         {row.mailbox}")
        print(f"  resource:        {row.resource}")
        print(f"  expires_at:      {row.expires_at} (UTC)")


if __name__ == "__main__":
    main()
