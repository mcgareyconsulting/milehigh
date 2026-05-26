"""
@milehigh-header
schema_version: 1
purpose: Provider-agnostic core that matches a forwarded vendor pick-up email to a release and records it.
exports:
  ingest_pickup_email: Record one pick-up email; shared by the inbound webhook, the agent ingest endpoint, and the admin simulate endpoint.
imports_from: [app.config, app.models, app.brain.job_log.features.pickup]
imported_by: [app/brain/job_log/routes (inbound-email / ingest / simulate)]
invariants:
  - No Gmail/provider dependency: callers fetch/receive the email and pass its fields in.
    CloudMailin (inbound webhook) is normalized in app/pickup_email/cloudmailin.py.
  - The job-release is taken from explicit job+release when given (agent path), otherwise
    parsed from the subject (inbound-email / simulate paths).
  - Idempotency is the unique PickupOrder.email_message_id (set inside RecordPickupCommand).
"""
from app.config import Config as cfg
from app.logging_config import get_logger

logger = get_logger(__name__)


def ingest_pickup_email(*, subject=None, sender=None, to=None, body=None,
                        message_id=None, received_at=None, job=None, release=None) -> dict:
    """Record one pick-up email. Provider-agnostic; no Gmail dependency.

    Shared core used by the Gmail poller, the admin simulate endpoint, and the
    agent ingest endpoint. The job-release is taken from explicit `job`+`release`
    when provided (agent path — the user named the release), otherwise parsed from
    the subject (mailbox-poll path).

    Returns a status dict; only raises on unexpected (transient) errors:
      - {"status": "unparseable", ...}  no explicit release and none in subject
      - {"status": "unmatched", ...}    resolved, but no such release
      - {"status": "recorded" | "duplicate", "pickup_order_id", "event_id", ...}
    """
    from app.models import Releases
    from app.brain.job_log.features.pickup.parser import parse_subject, clean_subject
    from app.brain.job_log.features.pickup.command import RecordPickupCommand

    raw_subject = subject or ""
    if job is not None and release:
        try:
            job_number = int(job)
        except (TypeError, ValueError):
            return {"status": "unparseable", "subject": raw_subject, "reason": "invalid job"}
        release = str(release).strip().upper()
    else:
        parsed = parse_subject(raw_subject)
        if not parsed:
            return {"status": "unparseable", "subject": raw_subject}
        job_number, release = parsed

    if not Releases.query.filter_by(job=job_number, release=release).first():
        return {"status": "unmatched", "job": job_number, "release": release}

    result = RecordPickupCommand(
        job_id=job_number,
        release=release,
        vendor=cfg.PICKUP_VENDOR_LABEL,
        email_message_id=message_id,
        email_subject=clean_subject(raw_subject),
        email_from=sender,
        email_to=to,
        email_body=body,
        email_received_at=received_at,
    ).execute()

    return {
        "status": "duplicate" if result.deduplicated else "recorded",
        "job": job_number,
        "release": release,
        "pickup_order_id": result.pickup_order_id,
        "event_id": result.event_id,
    }
