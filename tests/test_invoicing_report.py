"""Integration tests for the monthly invoicing report endpoint.

Layer: integration (HTTP via test_client + in-memory DB). Auth is patched at
app.auth.utils.get_current_user — the decorator resolves the user there.
"""
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from app.models import (
    db,
    Releases,
    Submittals,
    ReleaseEvents,
    SubmittalEvents,
    Projects,
)


REPORT_URL = "/api/reports/monthly-invoicing?year=2026&month=5"


def _mock_user(*, username="someone@mhmw.com", is_admin=False):
    user = Mock()
    user.id = 99
    user.username = username
    user.is_admin = is_admin
    user.is_active = True
    user.is_drafter = False
    return user


@pytest.fixture
def seeded(app):
    """Seed two projects with releases/submittals and events in May and April 2026."""
    with app.app_context():
        # Project 1234 — canonical name from Projects table.
        db.session.add(Projects(name="Downtown Mall", job_number="1234"))
        db.session.add(Releases(job=1234, release="V2", job_name="Downtown Mall (excel)",
                                description="Storefront frames", pm="JD", stage="Complete",
                                job_comp="X", invoiced="X"))
        db.session.add(Submittals(submittal_id="S-1", project_number="1234",
                                  project_name="Downtown Mall", title="Glazing schedule",
                                  status="Approved", ball_in_court="Jane Smith",
                                  submittal_manager="Bob Jones"))
        # Project 5678 — no Projects row; name falls back to release/submittal values.
        db.session.add(Releases(job=5678, release="A", job_name="Airport Hangar",
                                description="Canopy"))
        db.session.add(Submittals(submittal_id="S-2", project_number="5678",
                                  project_name="Airport Hangar", title="Anchor bolts",
                                  status="Open"))

        # May 2026 events (in range).
        db.session.add(ReleaseEvents(job=1234, release="V2", action="update_stage",
                                     payload={"from": "Released", "to": "Welded QC"},
                                     payload_hash="h-rel-may-1", source="Brain",
                                     created_at=datetime(2026, 5, 15, 12, 0)))
        # A field-level 'updated' event: new_value should surface the field name.
        db.session.add(ReleaseEvents(job=1234, release="V2", action="updated",
                                     payload={"field": "job_comp", "old_value": None, "new_value": "X"},
                                     payload_hash="h-rel-may-field", source="Brain",
                                     created_at=datetime(2026, 5, 17, 12, 0)))
        db.session.add(ReleaseEvents(job=5678, release="A", action="update_fab_order",
                                     payload={"from": 5.0, "to": 7.0},
                                     payload_hash="h-rel-may-2", source="Brain",
                                     created_at=datetime(2026, 5, 16, 12, 0)))
        db.session.add(SubmittalEvents(submittal_id="S-1", action="updated",
                                       payload={"status": {"old": "Open", "new": "Approved"}},
                                       payload_hash="h-sub-may-1", source="Procore",
                                       created_at=datetime(2026, 5, 10, 12, 0)))
        # A system-echo event in May — must be excluded.
        db.session.add(SubmittalEvents(submittal_id="S-1", action="updated",
                                       payload={"status": {"old": "Approved", "new": "Open"}},
                                       payload_hash="h-sub-may-echo", source="Brain",
                                       is_system_echo=True,
                                       created_at=datetime(2026, 5, 11, 12, 0)))

        # April 2026 event (out of range) — its project should not appear.
        db.session.add(SubmittalEvents(submittal_id="S-2", action="created",
                                       payload={"title": "Anchor bolts"},
                                       payload_hash="h-sub-apr-1", source="Procore",
                                       created_at=datetime(2026, 4, 20, 12, 0)))
        db.session.commit()
    return app


def test_requires_auth(client):
    resp = client.get(REPORT_URL)
    assert resp.status_code == 401


def test_forbidden_for_other_user(seeded):
    with patch("app.auth.utils.get_current_user", return_value=_mock_user()):
        resp = seeded.test_client().get(REPORT_URL)
    assert resp.status_code == 403


def test_allowed_for_admin(seeded):
    with patch("app.auth.utils.get_current_user",
               return_value=_mock_user(is_admin=True)):
        resp = seeded.test_client().get(REPORT_URL)
    assert resp.status_code == 200


def test_allowed_for_khearn(seeded):
    with patch("app.auth.utils.get_current_user",
               return_value=_mock_user(username="KHearn@MHMW.com")):
        resp = seeded.test_client().get(REPORT_URL)
    assert resp.status_code == 200


def test_report_groups_and_filters_by_month(seeded):
    with patch("app.auth.utils.get_current_user",
               return_value=_mock_user(is_admin=True)):
        resp = seeded.test_client().get(REPORT_URL)
    data = resp.get_json()

    assert data["year"] == 2026
    assert data["month"] == 5
    assert data["month_label"] == "May 2026"

    projects = {p["project_number"]: p for p in data["projects"]}
    # Project 5678 only had an April submittal event + a May release event;
    # it appears because of the release event, but its submittal must be absent.
    assert set(projects) == {"1234", "5678"}

    # Canonical name preferred from Projects table.
    assert projects["1234"]["project_name"] == "Downtown Mall"
    # Fallback name when no Projects row.
    assert projects["5678"]["project_name"] == "Airport Hangar"

    # Project 1234: one release with two changes, one submittal with one change
    # (system-echo excluded).
    p1234 = projects["1234"]
    assert len(p1234["releases"]) == 1
    rel = p1234["releases"][0]
    assert rel["release"] == "V2"
    assert rel["total_changes"] == 2
    # Release summary fields surfaced for the one-line row.
    assert rel["pm"] == "JD"
    assert rel["stage"] == "Complete"
    assert rel["install_prog"] == "X"
    assert rel["invoiced"] == "X"
    # Field-level 'updated' event names the changed field.
    new_values = [ev["new_value"] for ev in rel["events"]]
    assert "Welded QC" in new_values
    assert "job_comp → X" in new_values
    # Most recent change first: job_comp (May 17) precedes the stage change (May 15).
    assert rel["events"][0]["new_value"] == "job_comp → X"
    assert rel["events"][-1]["new_value"] == "Welded QC"

    assert len(p1234["submittals"]) == 1
    sub = p1234["submittals"][0]
    assert sub["submittal_id"] == "S-1"
    assert sub["total_changes"] == 1
    # Submittal summary fields surfaced for the one-line row.
    assert sub["status"] == "Approved"
    assert sub["ball_in_court"] == "Jane Smith"
    assert sub["submittal_manager"] == "Bob Jones"

    # Project 5678: release event present, submittal S-2 (April) excluded.
    p5678 = projects["5678"]
    assert len(p5678["releases"]) == 1
    assert p5678["submittals"] == []


def test_empty_month_returns_no_projects(seeded):
    with patch("app.auth.utils.get_current_user",
               return_value=_mock_user(is_admin=True)):
        resp = seeded.test_client().get("/api/reports/monthly-invoicing?year=2026&month=1")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["projects"] == []
    assert data["total_projects"] == 0


def test_invalid_month_rejected(seeded):
    with patch("app.auth.utils.get_current_user",
               return_value=_mock_user(is_admin=True)):
        resp = seeded.test_client().get("/api/reports/monthly-invoicing?year=2026&month=13")
    assert resp.status_code == 400
