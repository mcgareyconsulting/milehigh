"""Microsoft Graph change-notification (webhook) lifecycle for BB mail.

The PUSH fast path that complements the poll in m365_mail.py. Instead of waiting
for the next poll, Graph POSTs our notification endpoint the instant mail lands
in the watched mailbox; we fetch that one message and land it via the SAME
`_land()` upsert the poll uses, so push and poll stay perfectly consistent
(re-landing an already-seen message is a harmless 'unchanged').

Three pieces live here:
  - lifecycle: create / renew / delete / ensure a subscription. `ensure()` is the
    idempotent reconcile (list → create-or-renew-or-skip) modeled on the Procore
    `ensure_webhooks` script; it doubles as both the bootstrap and the renewal job.
  - `fetch_and_land()`: pull one message by id and upsert it into the lake.
  - `handle_notification()`: validate + dedup + land, called by the HTTP route.

Graph caps mailbox message subscriptions at ~70h, so a subscription is not
create-once — the renewal job PATCHes its expiry well inside that window, and
re-creates it if it has lapsed. If push ever silently stops, the poll floor
(BB_MAIL_POLL_MINUTES) sweeps up whatever was missed.
"""
from datetime import datetime, timedelta

from flask import current_app

from app.lake.ingest.m365_mail import GRAPH_SELECT, SOURCE, _land, _mailbox
from app.logging_config import get_logger
from app.microsoft.graph_app_client import (
    graph_delete,
    graph_get,
    graph_patch,
    graph_post,
)
from app.models import GraphSubscription, WebhookReceipt, db

logger = get_logger(__name__)

# The route the subscription points Graph at (appended to GRAPH_NOTIFICATION_URL).
NOTIFICATION_PATH = "/lake/graph/notifications"

# Graph caps message subscriptions at 4230 min (~70.5h); request just under so a
# little clock skew on Graph's side never rejects the create. Renew when within
# RENEW_THRESHOLD of expiry so a run can slip without the subscription lapsing.
SUBSCRIPTION_LIFETIME = timedelta(minutes=4200)
RENEW_THRESHOLD = timedelta(minutes=1440)  # 24h

# We only care about new mail arriving.
CHANGE_TYPE = "created"


class SubscriptionConfigError(RuntimeError):
    """Raised when the pieces needed to create a subscription are missing."""


def _resource(mailbox):
    """Graph resource path for a mailbox's Inbox messages."""
    return f"/users/{mailbox}/mailFolders/Inbox/messages"


def _notification_url():
    base = current_app.config.get("GRAPH_NOTIFICATION_URL")
    if not base:
        raise SubscriptionConfigError(
            "GRAPH_NOTIFICATION_URL is not set (the public HTTPS base Graph POSTs to)."
        )
    return base.rstrip("/") + NOTIFICATION_PATH


def _client_state():
    secret = current_app.config.get("GRAPH_SUBSCRIPTION_CLIENT_STATE")
    if not secret:
        raise SubscriptionConfigError(
            "GRAPH_SUBSCRIPTION_CLIENT_STATE is not set (the notification shared secret)."
        )
    return secret


def _expiration_iso(now=None):
    """ISO-8601 UTC 'Z' timestamp Graph accepts for expirationDateTime."""
    now = now or datetime.utcnow()
    return (now + SUBSCRIPTION_LIFETIME).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_graph_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def list_remote():
    """All Graph subscriptions this app currently owns (across all resources)."""
    data = graph_get("/subscriptions")
    return data.get("value", []) or []


def create_subscription(mailbox=None):
    """Create a Graph subscription for the mailbox's Inbox and persist the row.

    Graph validates the notificationUrl synchronously (it POSTs a validationToken
    that our route must echo) before returning — so the endpoint must be live and
    publicly reachable when this runs. Returns the persisted GraphSubscription.
    """
    mailbox = mailbox or _mailbox()
    resource = _resource(mailbox)
    body = {
        "changeType": CHANGE_TYPE,
        "notificationUrl": _notification_url(),
        "resource": resource,
        "expirationDateTime": _expiration_iso(),
        "clientState": _client_state(),
    }
    created = graph_post("/subscriptions", body)
    sub_id = created.get("id")
    expires_at = _parse_graph_dt(created.get("expirationDateTime"))

    row = GraphSubscription.get(SOURCE, resource)
    if row is None:
        row = GraphSubscription(source=SOURCE, resource=resource)
        db.session.add(row)
    row.mailbox = mailbox
    row.subscription_id = sub_id
    row.client_state = body["clientState"]
    row.notification_url = body["notificationUrl"]
    row.expires_at = expires_at
    db.session.commit()

    logger.info(
        "graph_subscription_created",
        mailbox=mailbox,
        subscription_id=sub_id,
        expires_at=str(expires_at),
    )
    return row


def renew_subscription(row):
    """PATCH a subscription's expiry forward. Returns the updated row."""
    new_expiry = _expiration_iso()
    updated = graph_patch(
        f"/subscriptions/{row.subscription_id}",
        {"expirationDateTime": new_expiry},
    )
    row.expires_at = _parse_graph_dt(updated.get("expirationDateTime")) if updated else _parse_graph_dt(new_expiry)
    db.session.commit()
    logger.info(
        "graph_subscription_renewed",
        subscription_id=row.subscription_id,
        expires_at=str(row.expires_at),
    )
    return row


def delete_subscription(subscription_id):
    """Delete a Graph subscription and drop its local row (if any). Idempotent."""
    try:
        graph_delete(f"/subscriptions/{subscription_id}")
    except Exception as exc:  # noqa: BLE001 — a 404 (already gone) is success for our purposes
        logger.warning("graph_subscription_delete_remote_failed", subscription_id=subscription_id, error=str(exc))
    row = GraphSubscription.query.filter_by(subscription_id=subscription_id).first()
    if row is not None:
        db.session.delete(row)
        db.session.commit()
    logger.info("graph_subscription_deleted", subscription_id=subscription_id)


def _needs_renew(row, now=None):
    now = now or datetime.utcnow()
    return row.expires_at is None or row.expires_at <= now + RENEW_THRESHOLD


def ensure(mailbox=None):
    """Idempotently converge the mailbox's subscription to a live, non-expiring state.

    - No subscription (or ours is unknown to Graph) → create one.
    - Ours exists but is nearing expiry → renew it.
    - Ours exists and is healthy → skip.

    Safe to run repeatedly; this is both the bootstrap call and the renewal job.
    Returns a small action summary dict.
    """
    mailbox = mailbox or _mailbox()
    resource = _resource(mailbox)
    row = GraphSubscription.get(SOURCE, resource)

    # Reconcile against Graph's view: our stored id must actually still exist there
    # (a lapsed subscription is silently dropped by Graph, leaving a stale row).
    remote_ids = {s.get("id") for s in list_remote()}
    known_remotely = bool(row and row.subscription_id in remote_ids)

    if not known_remotely:
        row = create_subscription(mailbox)
        return {"action": "created", "subscription_id": row.subscription_id, "mailbox": mailbox}

    if _needs_renew(row):
        renew_subscription(row)
        return {"action": "renewed", "subscription_id": row.subscription_id, "mailbox": mailbox}

    return {"action": "skipped", "subscription_id": row.subscription_id, "mailbox": mailbox}


# --------------------------------------------------------------------------- #
# Notification handling
# --------------------------------------------------------------------------- #
def _mailbox_for_subscription(subscription_id):
    """Resolve which mailbox a subscription id watches (falls back to default)."""
    row = GraphSubscription.query.filter_by(subscription_id=subscription_id).first()
    if row and row.mailbox:
        return row.mailbox
    return _mailbox()


def _already_processed(subscription_id, message_id):
    """Dedup guard: record (subscription, message) once; a retry hits the unique key.

    Mirrors the Procore WebhookReceipt pattern so a duplicate notification (Graph
    can redeliver) is a no-op before any Graph fetch.
    """
    import hashlib

    from sqlalchemy.exc import IntegrityError

    receipt_hash = hashlib.sha256(
        f"graph:{subscription_id}:{message_id}".encode("utf-8")
    ).hexdigest()
    # receipt_hash (fixed 64 chars) is the real dedup key. resource_id is only an
    # informational back-reference and the shared WebhookReceipt column is VARCHAR(64),
    # but a Graph message id is ~150 chars — Postgres rejects the overflow (SQLite
    # silently allows it, which is why tests didn't catch it). Store a fitting prefix.
    receipt = WebhookReceipt(
        receipt_hash=receipt_hash, provider="graph", resource_id=(message_id or "")[:64]
    )
    db.session.add(receipt)
    try:
        db.session.commit()
        return False
    except IntegrityError:
        db.session.rollback()
        return True


def fetch_and_land(mailbox, message_id):
    """Fetch one message by id and upsert it into the lake. Returns the _land result."""
    message = graph_get(
        f"/users/{mailbox}/messages/{message_id}", params={"$select": GRAPH_SELECT}
    )
    result = _land(message, mailbox)
    db.session.commit()
    logger.info("graph_notification_landed", mailbox=mailbox, message_id=message_id, result=result)
    return result


def handle_notification(payload):
    """Process a Graph change-notification body ({"value": [ ... ]}).

    For each valid item (clientState verified, not already processed), fetches the
    message and lands it. Silently skips items whose clientState doesn't match, so
    a spoofed POST can't drive fetches. Returns a summary dict. Never raises for a
    single bad item — the route must still 202 fast.
    """
    expected_state = current_app.config.get("GRAPH_SUBSCRIPTION_CLIENT_STATE")
    items = (payload or {}).get("value", []) or []
    summary = {"received": len(items), "landed": 0, "duplicate": 0, "rejected": 0, "errors": 0}

    for item in items:
        if expected_state and item.get("clientState") != expected_state:
            summary["rejected"] += 1
            logger.warning("graph_notification_bad_client_state", subscription_id=item.get("subscriptionId"))
            continue

        subscription_id = item.get("subscriptionId")
        resource_data = item.get("resourceData") or {}
        message_id = resource_data.get("id")
        if not message_id:
            summary["errors"] += 1
            continue

        # Guard the whole item — dedup insert AND fetch — so one bad item (e.g. a
        # DB error) can never abort the rest of the batch and leave Graph un-acked.
        try:
            if _already_processed(subscription_id, message_id):
                summary["duplicate"] += 1
                continue
            mailbox = _mailbox_for_subscription(subscription_id)
            fetch_and_land(mailbox, message_id)
            summary["landed"] += 1
        except Exception:
            db.session.rollback()
            summary["errors"] += 1
            logger.error(
                "graph_notification_item_failed",
                subscription_id=subscription_id,
                message_id=message_id,
                exc_info=True,
            )

    # Consume anything newly landed into supplier material orders, same as the poll.
    if summary["landed"]:
        try:
            from app.brain.material_orders import service as material_orders_service

            material_orders_service.ingest_unprocessed()
        except Exception:
            logger.error("graph_notification_material_ingest_failed", exc_info=True)

    return summary
