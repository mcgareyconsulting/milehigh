"""Integration tests for GET /brain/release/<job>/<release>/rundown."""
from datetime import datetime

from app.models import Releases, PickupOrder, ReleaseEvents, db

TOKEN = "test-service-token"


def seed():
    rel = Releases(job=280, release="235", job_name="Acme", stage="Released", pm="RL")
    db.session.add(rel)
    db.session.flush()
    db.session.add(ReleaseEvents(
        job=280, release="235", action="update_stage", payload={"from": "Released", "to": "Cut Start"},
        payload_hash="h1", source="Brain", is_system_echo=False, created_at=datetime(2026, 5, 1)))
    db.session.add(ReleaseEvents(
        job=280, release="235", action="echo", payload={}, payload_hash="h2",
        source="Trello", is_system_echo=True, created_at=datetime(2026, 5, 2)))
    db.session.add(PickupOrder(
        release_id=rel.id, job=280, release="235", vendor="Dencol",
        email_message_id="m1", email_subject="280-235 ready", email_from="vendor@dencol.com",
        email_body="parts", status="received", created_at=datetime(2026, 5, 3)))
    db.session.commit()


def test_rundown_zips_release_events_pickups(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    with app.app_context():
        seed()

    resp = client.get("/brain/release/280/235/rundown", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["release"]["job"] == 280 and data["release"]["release"] == "235"
    # system echo hidden by default → only the update_stage event
    assert data["counts"]["events"] == 1
    assert data["events"][0]["action"] == "update_stage"
    assert data["counts"]["pickups"] == 1
    assert data["pickups"][0]["email_subject"] == "280-235 ready"
    assert data["pickups"][0]["vendor"] == "Dencol"


def test_rundown_include_echoes(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    with app.app_context():
        seed()
    resp = client.get("/brain/release/280/235/rundown?include_echoes=true",
                      headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    assert resp.get_json()["counts"]["events"] == 2


def test_rundown_missing_release_404(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    resp = client.get("/brain/release/999/Z/rundown", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 404


def test_rundown_requires_auth(client, app):
    app.config["BRAIN_SERVICE_TOKEN"] = TOKEN
    resp = client.get("/brain/release/280/235/rundown")
    assert resp.status_code == 401
