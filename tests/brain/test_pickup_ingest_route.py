"""Integration tests for the agent-facing /brain/pickup/ingest endpoint (service token + explicit release)."""
from app.models import Releases, PickupOrder, TrelloOutbox, db

TOKEN = "test-service-token"


def make_release(job, release, pm="DR"):
    db.session.add(Releases(job=job, release=release, job_name="T", stage="Released", pm=pm))
    db.session.commit()


def test_ingest_with_service_token_and_explicit_release(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    with app.app_context():
        make_release(380, "456")

    resp = client.post(
        "/brain/pickup/ingest",
        json={"job": 380, "release": "456", "subject": "Dencol parts", "body": "trace",
              "message_id": "gmail-xyz"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "recorded"
    assert data["job"] == 380 and data["release"] == "456"
    with app.app_context():
        assert PickupOrder.query.filter_by(job=380, release="456", email_message_id="gmail-xyz").count() == 1
        assert TrelloOutbox.query.filter_by(action="create_pickup_card").count() == 1


def test_ingest_release_normalized_uppercase(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    with app.app_context():
        make_release(412, "V3")
    resp = client.post(
        "/brain/pickup/ingest",
        json={"job": 412, "release": "v3", "subject": "x"},
        headers={"X-Brain-Token": TOKEN},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "recorded"


def test_ingest_unmatched_release(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    resp = client.post(
        "/brain/pickup/ingest",
        json={"job": 999, "release": "999", "subject": "x"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["status"] == "unmatched"


def test_ingest_requires_job_release_or_subject(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    resp = client.post("/brain/pickup/ingest", json={"from": "x"},
                       headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 400


def test_ingest_bad_token_unauthorized(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    resp = client.post("/brain/pickup/ingest", json={"job": 1, "release": "1"},
                       headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_ingest_admin_session_allowed(admin_client, app):
    # No token configured → admin session is the fallback path.
    app.config["BRAIN_SERVICE_TOKEN"] = None
    with app.app_context():
        make_release(380, "456")
    resp = admin_client.post("/brain/pickup/ingest", json={"job": 380, "release": "456", "subject": "x"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "recorded"


def test_ingest_no_auth_rejected(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    resp = client.post("/brain/pickup/ingest", json={"job": 1, "release": "1"})
    assert resp.status_code == 401
