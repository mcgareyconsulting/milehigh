"""Integration tests for the monthly invoicing report endpoint.

Layer: integration (HTTP via test_client + in-memory DB). Auth is patched at
app.auth.utils.get_current_user — the decorator resolves the user there.

The report is Katie Hearn's billing view, so it applies several filters:
  * Submittals: DRR ("Drafting Release Review") type only.
  * Submittal events: create / open / close lifecycle only (no BIC/order changes).
  * Releases: no fab-order, start-install, or due-date events.
  * Submittal items never expose ball_in_court.
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

DRR_TYPE = "Drafting Release Review"

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
    """Seed projects exercising every invoicing filter, in May and April 2026."""
    with app.app_context():
        # Project 1234 — canonical name from Projects table.
        db.session.add(Projects(name="Downtown Mall", job_number="1234"))
        db.session.add(Releases(job=1234, release="V2", job_name="Downtown Mall (excel)",
                                description="Storefront frames", pm="JD", stage="Complete",
                                job_comp="X", invoiced="X"))
        # DRR submittal — appears, with ball_in_court that must NOT surface.
        db.session.add(Submittals(submittal_id="S-1", project_number="1234",
                                  project_name="Downtown Mall", title="Glazing schedule",
                                  type=DRR_TYPE, status="Closed", ball_in_court="Jane Smith",
                                  submittal_manager="Bob Jones"))
        # Non-DRR submittal — must be excluded entirely.
        db.session.add(Submittals(submittal_id="S-3", project_number="1234",
                                  project_name="Downtown Mall", title="GC approval pkg",
                                  type="Submittal for GC Approval", status="Open"))
        # Project 5678 — its only May event is an excluded fab-order change, so the
        # whole project must drop out of the report.
        db.session.add(Releases(job=5678, release="A", job_name="Airport Hangar",
                                description="Canopy"))

        # --- May 2026 release events for 1234/V2 ---
        db.session.add(ReleaseEvents(job=1234, release="V2", action="update_stage",
                                     payload={"from": "Released", "to": "Welded QC"},
                                     payload_hash="h-rel-stage", source="Brain",
                                     created_at=datetime(2026, 5, 15, 12, 0)))
        db.session.add(ReleaseEvents(job=1234, release="V2", action="updated",
                                     payload={"field": "job_comp", "old_value": None, "new_value": "X"},
                                     payload_hash="h-rel-jobcomp", source="Brain",
                                     created_at=datetime(2026, 5, 17, 12, 0)))
        # Excluded release events (fab order, start install, due date).
        db.session.add(ReleaseEvents(job=1234, release="V2", action="update_fab_order",
                                     payload={"from": 5.0, "to": 7.0},
                                     payload_hash="h-rel-fab", source="Brain",
                                     created_at=datetime(2026, 5, 16, 12, 0)))
        db.session.add(ReleaseEvents(job=1234, release="V2", action="updated",
                                     payload={"field": "start_install", "old_value": None, "new_value": "2026-06-01"},
                                     payload_hash="h-rel-si", source="Brain",
                                     created_at=datetime(2026, 5, 18, 12, 0)))
        db.session.add(ReleaseEvents(job=1234, release="V2", action="update_due_date",
                                     payload={"from": None, "to": "2026-06-10"},
                                     payload_hash="h-rel-due", source="Trello",
                                     created_at=datetime(2026, 5, 19, 12, 0)))

        # --- May 2026 submittal events for DRR S-1 ---
        db.session.add(SubmittalEvents(submittal_id="S-1", action="created",
                                       payload={"title": "Glazing schedule", "status": "Draft"},
                                       payload_hash="h-sub-create", source="Procore",
                                       created_at=datetime(2026, 5, 10, 12, 0)))
        db.session.add(SubmittalEvents(submittal_id="S-1", action="updated",
                                       payload={"status": {"old": "Draft", "new": "Open"}},
                                       payload_hash="h-sub-open", source="Procore",
                                       created_at=datetime(2026, 5, 12, 12, 0)))
        db.session.add(SubmittalEvents(submittal_id="S-1", action="updated",
                                       payload={"status": {"old": "Open", "new": "Closed"}},
                                       payload_hash="h-sub-close", source="Procore",
                                       created_at=datetime(2026, 5, 14, 12, 0)))
        # Ball-in-court-only update — must be excluded.
        db.session.add(SubmittalEvents(submittal_id="S-1", action="updated",
                                       payload={"ball_in_court": {"old": "Jane", "new": "Bob"}},
                                       payload_hash="h-sub-bic", source="Procore",
                                       created_at=datetime(2026, 5, 13, 12, 0)))
        # Status change to a non-open/close value — must be excluded.
        db.session.add(SubmittalEvents(submittal_id="S-1", action="updated",
                                       payload={"status": {"old": "Closed", "new": "Approved"}},
                                       payload_hash="h-sub-appr", source="Procore",
                                       created_at=datetime(2026, 5, 15, 12, 0)))
        # System-echo open event — excluded by the echo filter.
        db.session.add(SubmittalEvents(submittal_id="S-1", action="updated",
                                       payload={"status": {"old": "Draft", "new": "Open"}},
                                       payload_hash="h-sub-echo", source="Brain",
                                       is_system_echo=True,
                                       created_at=datetime(2026, 5, 11, 12, 0)))
        # Non-DRR submittal event — excluded because S-3 is not a DRR.
        db.session.add(SubmittalEvents(submittal_id="S-3", action="created",
                                       payload={"title": "GC approval pkg", "status": "Open"},
                                       payload_hash="h-sub-nondrr", source="Procore",
                                       created_at=datetime(2026, 5, 9, 12, 0)))

        # --- May 2026: project 5678's only event is excluded (fab order) ---
        db.session.add(ReleaseEvents(job=5678, release="A", action="update_fab_order",
                                     payload={"from": 5.0, "to": 7.0},
                                     payload_hash="h-5678-fab", source="Brain",
                                     created_at=datetime(2026, 5, 16, 12, 0)))

        # Project 9012 — DRR created + opened in April, closed in May. Viewing
        # May must still surface the April create/open dates (lifecycle backfill).
        db.session.add(Projects(name="Lakeside Tower", job_number="9012"))
        db.session.add(Submittals(submittal_id="S-4", project_number="9012",
                                  project_name="Lakeside Tower", title="Late close",
                                  type=DRR_TYPE, status="Closed", submittal_manager="Amy Lee"))
        db.session.add(SubmittalEvents(submittal_id="S-4", action="created",
                                       payload={"title": "Late close", "status": "Draft"},
                                       payload_hash="h-s4-create", source="Procore",
                                       created_at=datetime(2026, 4, 5, 12, 0)))
        db.session.add(SubmittalEvents(submittal_id="S-4", action="updated",
                                       payload={"status": {"old": "Draft", "new": "Open"}},
                                       payload_hash="h-s4-open", source="Procore",
                                       created_at=datetime(2026, 4, 10, 12, 0)))
        db.session.add(SubmittalEvents(submittal_id="S-4", action="updated",
                                       payload={"status": {"old": "Open", "new": "Closed"}},
                                       payload_hash="h-s4-close", source="Procore",
                                       created_at=datetime(2026, 5, 20, 12, 0)))

        # --- April 2026 (out of range) ---
        db.session.add(SubmittalEvents(submittal_id="S-1", action="created",
                                       payload={"title": "Glazing schedule"},
                                       payload_hash="h-sub-apr", source="Procore",
                                       created_at=datetime(2026, 4, 20, 12, 0)))
        db.session.commit()
    return app


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Filtering behavior
# --------------------------------------------------------------------------- #

def _get_report(seeded, url=REPORT_URL):
    with patch("app.auth.utils.get_current_user",
               return_value=_mock_user(is_admin=True)):
        resp = seeded.test_client().get(url)
    return resp


def test_month_metadata(seeded):
    data = _get_report(seeded).get_json()
    assert data["year"] == 2026
    assert data["month"] == 5
    assert data["month_label"] == "May 2026"


def test_project_pruned_when_all_events_excluded(seeded):
    """5678's only May event is a fab-order change, so the project drops out."""
    data = _get_report(seeded).get_json()
    projects = {p["project_number"] for p in data["projects"]}
    assert projects == {"1234", "9012"}
    assert "5678" not in projects


def test_submittal_lifecycle_backfills_prior_month_dates(seeded):
    """A DRR closed in May still reports its April create/open dates."""
    data = _get_report(seeded).get_json()
    p9012 = next(p for p in data["projects"] if p["project_number"] == "9012")
    assert [s["submittal_id"] for s in p9012["submittals"]] == ["S-4"]
    sub = p9012["submittals"][0]
    assert sub["total_changes"] == 3
    by_kind = {ev["kind"]: ev["created_at"] for ev in sub["events"]}
    assert set(by_kind) == {"create", "open", "close"}
    # Create and open happened in April; close in May — all three are present.
    assert by_kind["create"].startswith("April")
    assert by_kind["open"].startswith("April")
    assert by_kind["close"].startswith("May")


def test_releases_drop_fab_install_due_events(seeded):
    data = _get_report(seeded).get_json()
    p1234 = next(p for p in data["projects"] if p["project_number"] == "1234")
    assert len(p1234["releases"]) == 1
    rel = p1234["releases"][0]
    # Only the stage change and the job_comp update survive.
    assert rel["total_changes"] == 2
    new_values = [ev["new_value"] for ev in rel["events"]]
    assert "Welded QC" in new_values
    assert "job_comp → X" in new_values
    actions = {ev["action"] for ev in rel["events"]}
    assert "update_fab_order" not in actions
    assert "update_due_date" not in actions
    # The start_install field-level update is gone too.
    assert all("start_install" not in (ev["new_value"] or "") for ev in rel["events"])
    # Release summary fields still surface for the one-line row.
    assert rel["stage"] == "Complete"
    assert rel["install_prog"] == "X"
    assert rel["invoiced"] == "X"


def test_submittals_drr_only_with_lifecycle_events(seeded):
    data = _get_report(seeded).get_json()
    p1234 = next(p for p in data["projects"] if p["project_number"] == "1234")
    # Non-DRR S-3 is excluded; only DRR S-1 remains.
    assert [s["submittal_id"] for s in p1234["submittals"]] == ["S-1"]

    sub = p1234["submittals"][0]
    # create + open + close survive; BIC-only and Approved updates are dropped.
    assert sub["total_changes"] == 3
    kinds = [ev["kind"] for ev in sub["events"]]
    # Events are newest-first: close (May 14), open (May 12), create (May 10).
    assert kinds == ["close", "open", "create"]


def test_submittal_items_omit_ball_in_court(seeded):
    data = _get_report(seeded).get_json()
    p1234 = next(p for p in data["projects"] if p["project_number"] == "1234")
    sub = p1234["submittals"][0]
    assert "ball_in_court" not in sub
    # Other summary fields remain.
    assert sub["status"] == "Closed"
    assert sub["submittal_manager"] == "Bob Jones"


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #

def test_empty_month_returns_no_projects(seeded):
    data = _get_report(seeded, "/api/reports/monthly-invoicing?year=2026&month=1").get_json()
    assert data["projects"] == []
    assert data["total_projects"] == 0


def test_invalid_month_rejected(seeded):
    resp = _get_report(seeded, "/api/reports/monthly-invoicing?year=2026&month=13")
    assert resp.status_code == 400
