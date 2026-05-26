"""
End-to-end pick-up test harness: inbound email -> match -> record -> Trello (MOCK).

Drives the same provider-agnostic core the /brain/pickup/inbound-email route runs
(CloudMailin payload -> parse_inbound -> ingest_pickup_email) against an ISOLATED local
SQLite DB (never sandbox/prod) with TRELLO_MOCK on, so the Trello card is simulated.
Seeds the release you name so the match succeeds, then prints the resulting PickupOrder
+ outbox status. No Gmail, no network — feed it a fake forwarded email.

Usage:
    python scripts/pickup_e2e_test.py --job 380 --release 456 \
        --subject "Fwd: 380-456 parts ready for pickup"
"""
import argparse
import os
import sys
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def main():
    parser = argparse.ArgumentParser(description="Pick-up inbound-email->Trello(mock) e2e test.")
    parser.add_argument("--job", type=int, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--subject", help="Forwarded email subject (must contain the job-release).")
    parser.add_argument("--from", dest="sender", default="shipping@dencol.com")
    parser.add_argument("--db", default="pickup_e2e.sqlite", help="Local SQLite filename (isolated).")
    args = parser.parse_args()

    # Force an isolated local SQLite DB + mock Trello BEFORE importing app.
    # (python-dotenv loads .env with override=False, so these explicit values win.)
    os.environ["ENVIRONMENT"] = "local"
    os.environ["FLASK_ENV"] = "local"
    os.environ["LOCAL_DATABASE_URL"] = f"sqlite:///{os.path.join(ROOT_DIR, args.db)}"
    os.environ["TRELLO_MOCK"] = "1"

    from app import create_app
    from app.models import db, Releases, PickupOrder, TrelloOutbox
    from app.pickup_email.cloudmailin import parse_inbound
    from app.pickup_email.ingest import ingest_pickup_email
    from app.services.outbox_service import OutboxService

    subject = args.subject or f"Fwd: {args.job}-{args.release} parts ready for pickup"

    app = create_app()
    with app.app_context():
        db.create_all()

        if not Releases.query.filter_by(job=args.job, release=args.release).first():
            db.session.add(Releases(
                job=args.job, release=args.release, job_name="E2E Test Release",
                stage="Released", pm="DR",
            ))
            db.session.commit()
            print(f"seeded release {args.job}-{args.release}")
        else:
            print(f"release {args.job}-{args.release} already present")

        # Mimic exactly what CloudMailin POSTs to /brain/pickup/inbound-email.
        payload = {
            "envelope": {"from": args.sender, "to": "pickup@inbound.cloudmailin.net"},
            "headers": {
                "subject": subject,
                "from": args.sender,
                "to": "pickup@inbound.cloudmailin.net",
                "message_id": f"<e2e-{args.job}-{args.release}@dencol.com>",
                "date": "Tue, 26 May 2026 15:00:00 +0000",
            },
            "plain": "Your parts are ready for pick-up at the front desk.",
        }
        fields = parse_inbound(payload)
        print(f"\nparsed subject = {fields['subject']!r}")
        print("ingesting ...")
        res = ingest_pickup_email(**fields)
        print(f"ingest result: {res}")

        # Drive the outbox so the (mock) Trello card is created in this run.
        OutboxService.process_pending_items(limit=20)
        time.sleep(0.5)

        print("\n--- pickup_orders ---")
        for p in PickupOrder.query.order_by(PickupOrder.id).all():
            print(f"  #{p.id} {p.job}-{p.release} status={p.status} "
                  f"card={p.trello_card_id} subject={p.email_subject!r} from={p.email_from}")
        print("\n--- create_pickup_card outbox ---")
        for o in TrelloOutbox.query.filter_by(action="create_pickup_card").all():
            print(f"  outbox #{o.id} status={o.status} retries={o.retry_count} err={o.error_message}")


if __name__ == "__main__":
    main()
