"""Integration tests for the admin /brain/pickup/simulate endpoint."""
from app.models import Releases, PickupOrder, TrelloOutbox, db


def make_release(job, release, pm="GA"):
    db.session.add(Releases(job=job, release=release, job_name="T", stage="Released", pm=pm))
    db.session.commit()


def test_simulate_records_pickup(admin_client, app):
    with app.app_context():
        make_release(123, "V4")

    resp = admin_client.post("/brain/pickup/simulate", json={
        "subject": "Fwd: 123-V4 parts ready",
        "from": "vendor@dencol.com",
        "body": "full traceback",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "recorded"
    assert data["job"] == 123 and data["release"] == "V4"

    with app.app_context():
        assert PickupOrder.query.filter_by(job=123, release="V4").count() == 1
        assert TrelloOutbox.query.filter_by(action="create_pickup_card").count() == 1


def test_simulate_unmatched_release(admin_client, app):
    # Parses to a valid job-release, but no such release exists → unmatched.
    resp = admin_client.post("/brain/pickup/simulate", json={"subject": "999-V9 ready"})
    assert resp.status_code == 422
    assert resp.get_json()["status"] == "unmatched"


def test_simulate_unparseable_subject(admin_client, app):
    resp = admin_client.post("/brain/pickup/simulate", json={"subject": "no identifier"})
    assert resp.status_code == 422
    assert resp.get_json()["status"] == "unparseable"


def test_simulate_requires_subject(admin_client, app):
    resp = admin_client.post("/brain/pickup/simulate", json={})
    assert resp.status_code == 400


def test_simulate_duplicate_message_id(admin_client, app):
    with app.app_context():
        make_release(123, "V4")
    body = {"subject": "123-V4 ready", "message_id": "fixed-id"}
    first = admin_client.post("/brain/pickup/simulate", json=body)
    second = admin_client.post("/brain/pickup/simulate", json=body)
    assert first.get_json()["status"] == "recorded"
    assert second.get_json()["status"] == "duplicate"
    with app.app_context():
        assert PickupOrder.query.filter_by(email_message_id="fixed-id").count() == 1


def test_simulate_requires_admin(non_admin_client, app):
    resp = non_admin_client.post("/brain/pickup/simulate", json={"subject": "123-V4"})
    assert resp.status_code == 403
