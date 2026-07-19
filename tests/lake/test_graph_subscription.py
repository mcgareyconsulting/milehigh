"""Tests for the Graph change-notification (push webhook) lifecycle + route.

Graph is always mocked; the DB is the real in-memory SQLite from tests/conftest.py.
Covers: the validation handshake, clientState rejection, fetch+land on a real
notification, notification dedup, and ensure() create/renew/skip reconciliation.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

from app.lake.ingest import graph_subscription as gs
from app.lake.ingest import m365_mail
from app.models import GraphSubscription, RawSourceRecord, WebhookReceipt, db


def _msg(mid="AAA", subject="RFI 042", received="2026-06-06T18:30:00Z", body="Hello"):
    return {
        "id": mid,
        "subject": subject,
        "from": {"emailAddress": {"name": "GC", "address": "gc@build.com"}},
        "toRecipients": [{"emailAddress": {"name": "BB", "address": "bb@mhmw.com"}}],
        "ccRecipients": [],
        "receivedDateTime": received,
        "sentDateTime": received,
        "bodyPreview": body[:50],
        "body": {"contentType": "text", "content": body},
        "conversationId": "conv1",
        "internetMessageId": "<msg@x>",
        "hasAttachments": False,
        "webLink": "https://outlook.example/x",
    }


def _configure(app):
    app.config["GRAPH_NOTIFICATION_URL"] = "https://abc123.ngrok-free.app"
    app.config["GRAPH_SUBSCRIPTION_CLIENT_STATE"] = "s3cr3t"
    app.config["BB_MAILBOX"] = "bb@mhmw.com"


# --------------------------------------------------------------------------- #
# Route: validation handshake + notification
# --------------------------------------------------------------------------- #
def test_validation_handshake_echoes_token(client):
    resp = client.post("/lake/graph/notifications?validationToken=abc%20123")
    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    assert resp.get_data(as_text=True) == "abc 123"


def test_notification_lands_message(client, app):
    _configure(app)
    body = {"value": [{
        "subscriptionId": "sub-1",
        "clientState": "s3cr3t",
        "resourceData": {"id": "AAA"},
    }]}
    with patch.object(gs, "graph_get", return_value=_msg("AAA")):
        resp = client.post("/lake/graph/notifications", json=body)
    assert resp.status_code == 202
    assert RawSourceRecord.query.filter_by(external_id="AAA").count() == 1


def test_notification_rejects_bad_client_state(client, app):
    _configure(app)
    body = {"value": [{
        "subscriptionId": "sub-1",
        "clientState": "WRONG",
        "resourceData": {"id": "AAA"},
    }]}
    with patch.object(gs, "graph_get", return_value=_msg("AAA")) as gg:
        resp = client.post("/lake/graph/notifications", json=body)
    assert resp.status_code == 202
    gg.assert_not_called()  # never fetched
    assert RawSourceRecord.query.count() == 0


# --------------------------------------------------------------------------- #
# handle_notification: land, dedup
# --------------------------------------------------------------------------- #
def test_handle_notification_dedup(app):
    _configure(app)
    item = {"subscriptionId": "sub-1", "clientState": "s3cr3t", "resourceData": {"id": "AAA"}}
    with patch.object(gs, "graph_get", return_value=_msg("AAA")):
        s1 = gs.handle_notification({"value": [item]})
        s2 = gs.handle_notification({"value": [item]})  # same message again
    assert s1["landed"] == 1
    assert s2["duplicate"] == 1 and s2["landed"] == 0
    assert RawSourceRecord.query.filter_by(external_id="AAA").count() == 1
    assert WebhookReceipt.query.filter_by(provider="graph").count() == 1


# A real Graph message id is ~150 chars; WebhookReceipt.resource_id is VARCHAR(64).
# In-memory SQLite ignores the cap, so we assert the stored length directly rather
# than relying on the DB to reject it (Postgres does — that's the prod bug this guards).
_LONG_ID = (
    "AAMkADkwNzY2Mjk3LWExZDgtNDg5Yi04MmI4LTAxNTdlYTg1MGVhYgBGAAAAAACBApl30w"
    "CuTrDw5TNVSqTwBwBk73yzyUFwRacXM4z5K2LPAAAAAAEMAABk73yzyUFwRacXM4z5K2LPAAAaUh1pAAA="
)


def test_receipt_resource_id_fits_column_for_long_graph_id(app):
    _configure(app)
    assert len(_LONG_ID) > 64  # sanity: this id would overflow VARCHAR(64) unmasked
    item = {"subscriptionId": "sub-1", "clientState": "s3cr3t", "resourceData": {"id": _LONG_ID}}
    with patch.object(gs, "graph_get", return_value=_msg(_LONG_ID)):
        summary = gs.handle_notification({"value": [item]})
    assert summary["landed"] == 1
    receipt = WebhookReceipt.query.filter_by(provider="graph").one()
    assert len(receipt.resource_id) <= 64  # truncated to fit the shared column
    # Dedup still keyed on the full id via the hash, not the truncated resource_id.
    with patch.object(gs, "graph_get", return_value=_msg(_LONG_ID)):
        again = gs.handle_notification({"value": [item]})
    assert again["duplicate"] == 1


def test_handle_notification_skips_item_without_id(app):
    _configure(app)
    body = {"value": [{"subscriptionId": "sub-1", "clientState": "s3cr3t", "resourceData": {}}]}
    summary = gs.handle_notification(body)
    assert summary["errors"] == 1 and summary["landed"] == 0


# --------------------------------------------------------------------------- #
# ensure(): create / renew / skip
# --------------------------------------------------------------------------- #
def test_ensure_creates_when_absent(app):
    _configure(app)
    created = {"id": "sub-new", "expirationDateTime": "2026-06-09T00:00:00Z"}
    with patch.object(gs, "list_remote", return_value=[]), \
         patch.object(gs, "graph_post", return_value=created) as gp:
        result = gs.ensure()
    assert result["action"] == "created"
    gp.assert_called_once()
    row = GraphSubscription.get("m365_mail", "/users/bb@mhmw.com/mailFolders/Inbox/messages")
    assert row.subscription_id == "sub-new"


def test_ensure_renews_when_expiring(app):
    _configure(app)
    resource = "/users/bb@mhmw.com/mailFolders/Inbox/messages"
    row = GraphSubscription(
        source="m365_mail", resource=resource, mailbox="bb@mhmw.com",
        subscription_id="sub-old", client_state="s3cr3t",
        expires_at=datetime.utcnow() + timedelta(minutes=60),  # inside RENEW_THRESHOLD
    )
    db.session.add(row)
    db.session.commit()

    renewed = {"id": "sub-old", "expirationDateTime": "2026-06-12T00:00:00Z"}
    with patch.object(gs, "list_remote", return_value=[{"id": "sub-old"}]), \
         patch.object(gs, "graph_patch", return_value=renewed) as gpatch, \
         patch.object(gs, "graph_post") as gpost:
        result = gs.ensure()
    assert result["action"] == "renewed"
    gpatch.assert_called_once()
    gpost.assert_not_called()


def test_ensure_skips_when_healthy(app):
    _configure(app)
    resource = "/users/bb@mhmw.com/mailFolders/Inbox/messages"
    row = GraphSubscription(
        source="m365_mail", resource=resource, mailbox="bb@mhmw.com",
        subscription_id="sub-ok", client_state="s3cr3t",
        expires_at=datetime.utcnow() + timedelta(days=2),  # well outside threshold
    )
    db.session.add(row)
    db.session.commit()

    with patch.object(gs, "list_remote", return_value=[{"id": "sub-ok"}]), \
         patch.object(gs, "graph_post") as gpost, \
         patch.object(gs, "graph_patch") as gpatch:
        result = gs.ensure()
    assert result["action"] == "skipped"
    gpost.assert_not_called()
    gpatch.assert_not_called()


def test_ensure_recreates_when_stale_row_unknown_to_graph(app):
    """Stored row exists but Graph no longer knows the id (lapsed) → recreate."""
    _configure(app)
    resource = "/users/bb@mhmw.com/mailFolders/Inbox/messages"
    row = GraphSubscription(
        source="m365_mail", resource=resource, mailbox="bb@mhmw.com",
        subscription_id="sub-gone", client_state="s3cr3t",
        expires_at=datetime.utcnow() + timedelta(days=2),
    )
    db.session.add(row)
    db.session.commit()

    created = {"id": "sub-fresh", "expirationDateTime": "2026-06-09T00:00:00Z"}
    with patch.object(gs, "list_remote", return_value=[]), \
         patch.object(gs, "graph_post", return_value=created) as gpost:
        result = gs.ensure()
    assert result["action"] == "created"
    gpost.assert_called_once()
    assert GraphSubscription.get("m365_mail", resource).subscription_id == "sub-fresh"


def test_create_missing_config_raises(app):
    app.config["GRAPH_NOTIFICATION_URL"] = None
    with patch.object(gs, "list_remote", return_value=[]):
        try:
            gs.ensure()
            assert False, "expected SubscriptionConfigError"
        except gs.SubscriptionConfigError:
            pass
