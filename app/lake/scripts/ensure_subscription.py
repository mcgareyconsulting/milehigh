"""Idempotently ensure the BB-mail Graph subscription is live and non-expiring.

Reconciles against Graph: creates the subscription if missing/lapsed, renews it if
nearing expiry, or skips if healthy. This is the SAME function the renewal
scheduler job calls — running it by hand is safe and just fast-forwards the state.

Like create_subscription, a create/renew triggers Graph's synchronous validation,
so the endpoint at GRAPH_NOTIFICATION_URL must be live when this runs.

Usage:
    python -m app.lake.scripts.ensure_subscription
    python -m app.lake.scripts.ensure_subscription --mailbox bb@mhmw.com
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
    parser = argparse.ArgumentParser(description="Ensure/renew the BB-mail Graph subscription.")
    parser.add_argument("--mailbox", help="Mailbox to watch (default: BB_MAILBOX).")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        try:
            result = graph_subscription.ensure(args.mailbox)
        except graph_subscription.SubscriptionConfigError as exc:
            print(f"✗ {exc}")
            raise SystemExit(1)

        icon = {"created": "✓ created", "renewed": "✓ renewed", "skipped": "• already healthy"}
        print(icon.get(result["action"], result["action"]))
        print(f"  subscription_id: {result['subscription_id']}")
        print(f"  mailbox:         {result['mailbox']}")


if __name__ == "__main__":
    main()
