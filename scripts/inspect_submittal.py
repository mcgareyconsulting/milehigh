"""
One-off diagnostic: pull all operational logs + events around a single submittal.

Usage:
    ENVIRONMENT=production python scripts/inspect_submittal.py 69723920
"""
import os
import sys
import json
from datetime import datetime

# Ensure prod unless overridden
os.environ.setdefault("ENVIRONMENT", "production")

from app import create_app
from app.models import (
    Submittals,
    SubmittalEvents,
    ProcoreOutbox,
    WebhookReceipt,
    SystemLogs,
    SyncOperation,
)


def jdump(obj):
    try:
        return json.dumps(obj, indent=2, default=str)
    except Exception:
        return repr(obj)


def main():
    submittal_id = sys.argv[1] if len(sys.argv) > 1 else "69723920"
    sid = str(submittal_id)

    app = create_app()
    with app.app_context():
        print(f"DB: {app.config.get('SQLALCHEMY_DATABASE_URI', '').split('@')[-1]}")
        print("=" * 100)

        # 1. Current submittal record
        sub = Submittals.query.filter_by(submittal_id=sid).first()
        print(f"\n### SUBMITTAL RECORD (submittal_id={sid})")
        if not sub:
            print("  NOT FOUND in submittals table")
        else:
            print(jdump(sub.to_dict()))
            print(f"  raw status        : {sub.status!r}")
            print(f"  last_updated      : {sub.last_updated}")
            print(f"  last_bic_update   : {sub.last_bic_update}")
            print(f"  procore_project_id: {sub.procore_project_id}")

        # 2. Full event stream (chronological)
        events = (
            SubmittalEvents.query.filter(SubmittalEvents.submittal_id == sid)
            .order_by(SubmittalEvents.created_at.asc(), SubmittalEvents.id.asc())
            .all()
        )
        print(f"\n### SUBMITTAL_EVENTS ({len(events)} rows, chronological)")
        for e in events:
            payload = e.payload if isinstance(e.payload, dict) else e.payload
            print(
                f"\n  [{e.id}] {e.created_at}  action={e.action}  source={e.source}  "
                f"echo={e.is_system_echo}  ext_user={e.external_user_id}  int_user={e.internal_user_id}  applied_at={e.applied_at}"
            )
            print(f"       hash={e.payload_hash}")
            print("       payload=" + jdump(payload).replace("\n", "\n       "))

        # 3. Procore outbox (outbound attempts)
        ob = (
            ProcoreOutbox.query.filter(ProcoreOutbox.submittal_id == sid)
            .order_by(ProcoreOutbox.created_at.asc())
            .all()
        )
        print(f"\n### PROCORE_OUTBOX ({len(ob)} rows)")
        for o in ob:
            print(
                f"  [{o.id}] {o.created_at}  action={o.action}  status={o.status}  "
                f"retries={o.retry_count}/{o.max_retries}  next_retry={o.next_retry_at}  completed={o.completed_at}"
            )
            print(f"       src_app_id={o.source_application_id}  payload={jdump(o.request_payload)}")
            if o.error_message:
                print(f"       error={o.error_message}")

        # 4. Webhook receipts (incoming dedup, keyed by resource_id)
        wr = (
            WebhookReceipt.query.filter(WebhookReceipt.resource_id == sid)
            .order_by(WebhookReceipt.received_at.asc())
            .all()
        )
        print(f"\n### WEBHOOK_RECEIPTS (resource_id={sid}, {len(wr)} rows)")
        for w in wr:
            print(f"  [{w.id}] {w.received_at}  provider={w.provider}  hash={w.receipt_hash}")

        # 5. System logs mentioning the submittal id
        logs = (
            SystemLogs.query.filter(SystemLogs.message.like(f"%{sid}%"))
            .order_by(SystemLogs.timestamp.asc())
            .all()
        )
        print(f"\n### SYSTEM_LOGS mentioning {sid} ({len(logs)} rows)")
        for l in logs:
            print(f"  [{l.id}] {l.timestamp}  {l.level}  {l.category}/{l.operation}  {l.message}")
            if l.context:
                print(f"       context={jdump(l.context)}")

        # 6. Sync operations referencing the submittal as source_id
        ops = (
            SyncOperation.query.filter(SyncOperation.source_id == sid)
            .order_by(SyncOperation.started_at.asc())
            .all()
        )
        print(f"\n### SYNC_OPERATIONS source_id={sid} ({len(ops)} rows)")
        for op in ops:
            print(
                f"  [{op.id}] {op.started_at}  type={op.operation_type}  status={op.status}  "
                f"created={op.records_created} updated={op.records_updated} failed={op.records_failed}  err={op.error_message}"
            )


if __name__ == "__main__":
    main()
