"""Integration tests for the inbound-email webhook /brain/pickup/inbound-email.

Covers the shared-secret guard (fail-closed + the three accepted secret locations) and
the webhook status contract: every FINAL outcome returns 200 so the provider stops
re-POSTing, while the pipeline (PickupOrder + Trello outbox) still runs on a match.
"""
import base64

from app.models import Releases, PickupOrder, TrelloOutbox, db

SECRET = "inbound-secret-xyz"


def make_release(job, release, pm="DR"):
    db.session.add(Releases(job=job, release=release, job_name="T", stage="Released", pm=pm))
    db.session.commit()


def cloudmailin_payload(subject, sender="shipping@dencol.com", message_id="<m1@dencol.com>"):
    return {
        "envelope": {"from": sender, "to": "pickup@inbound.cloudmailin.net"},
        "headers": {
            "subject": subject,
            "from": sender,
            "to": "pickup@inbound.cloudmailin.net",
            "message_id": message_id,
            "date": "Tue, 26 May 2026 15:00:00 +0000",
        },
        "plain": "Your parts are ready for pick-up.",
    }


# --- auth -------------------------------------------------------------------

def test_fails_closed_when_secret_unconfigured(client, app):
    app.config["PICKUP_INBOUND_SECRET"] = None
    resp = client.post("/brain/pickup/inbound-email", json=cloudmailin_payload("380-456 ready"))
    assert resp.status_code == 503


def test_rejects_missing_or_wrong_secret(client, app):
    app.config["PICKUP_INBOUND_SECRET"] = SECRET
    assert client.post("/brain/pickup/inbound-email", json=cloudmailin_payload("380-456 ready")).status_code == 401
    bad = client.post("/brain/pickup/inbound-email?secret=nope", json=cloudmailin_payload("380-456 ready"))
    assert bad.status_code == 401


def test_accepts_secret_via_query_param(client, app):
    app.config["PICKUP_INBOUND_SECRET"] = SECRET
    with app.app_context():
        make_release(380, "456")
    resp = client.post(f"/brain/pickup/inbound-email?secret={SECRET}", json=cloudmailin_payload("380-456 ready"))
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "recorded"


def test_accepts_secret_via_header(client, app):
    app.config["PICKUP_INBOUND_SECRET"] = SECRET
    with app.app_context():
        make_release(381, "457")
    resp = client.post(
        "/brain/pickup/inbound-email",
        json=cloudmailin_payload("381-457 ready", message_id="<m-hdr@dencol.com>"),
        headers={"X-Pickup-Token": SECRET},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "recorded"


def test_accepts_secret_via_basic_auth_password(client, app):
    app.config["PICKUP_INBOUND_SECRET"] = SECRET
    with app.app_context():
        make_release(382, "458")
    creds = base64.b64encode(f"cloudmailin:{SECRET}".encode()).decode()
    resp = client.post(
        "/brain/pickup/inbound-email",
        json=cloudmailin_payload("382-458 ready", message_id="<m-basic@dencol.com>"),
        headers={"Authorization": f"Basic {creds}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "recorded"


# --- pipeline + status contract --------------------------------------------

def test_recorded_creates_pickup_and_queues_trello_card(client, app):
    app.config["PICKUP_INBOUND_SECRET"] = SECRET
    with app.app_context():
        make_release(380, "456")
    resp = client.post(f"/brain/pickup/inbound-email?secret={SECRET}",
                       json=cloudmailin_payload("Fwd: 380-456 parts ready", message_id="<real@dencol.com>"))
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "recorded"
    with app.app_context():
        assert PickupOrder.query.filter_by(job=380, release="456", email_message_id="<real@dencol.com>").count() == 1
        assert TrelloOutbox.query.filter_by(action="create_pickup_card").count() == 1


def test_duplicate_message_is_idempotent_200(client, app):
    app.config["PICKUP_INBOUND_SECRET"] = SECRET
    with app.app_context():
        make_release(380, "456")
    payload = cloudmailin_payload("380-456 ready", message_id="<dup@dencol.com>")
    first = client.post(f"/brain/pickup/inbound-email?secret={SECRET}", json=payload)
    second = client.post(f"/brain/pickup/inbound-email?secret={SECRET}", json=payload)
    assert first.get_json()["status"] == "recorded"
    assert second.status_code == 200
    assert second.get_json()["status"] == "duplicate"
    with app.app_context():
        assert PickupOrder.query.filter_by(email_message_id="<dup@dencol.com>").count() == 1


def test_unmatched_release_returns_200_not_422(client, app):
    # A webhook must NOT signal retry for a permanent miss, so unmatched is 200.
    # 999-888 is a well-formed job-release (so it parses) that no release row matches.
    app.config["PICKUP_INBOUND_SECRET"] = SECRET
    resp = client.post(f"/brain/pickup/inbound-email?secret={SECRET}",
                       json=cloudmailin_payload("999-888 ready"))
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "unmatched"
    with app.app_context():
        assert PickupOrder.query.count() == 0


def test_unparseable_subject_returns_200(client, app):
    app.config["PICKUP_INBOUND_SECRET"] = SECRET
    resp = client.post(f"/brain/pickup/inbound-email?secret={SECRET}",
                       json=cloudmailin_payload("no identifier here"))
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "unparseable"


def test_no_subject_returns_200_unparseable(client, app):
    app.config["PICKUP_INBOUND_SECRET"] = SECRET
    resp = client.post(f"/brain/pickup/inbound-email?secret={SECRET}",
                       json={"envelope": {"from": "x@y"}, "plain": "b"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "unparseable"
