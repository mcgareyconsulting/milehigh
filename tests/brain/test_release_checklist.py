"""Tests for GET /brain/releases/<id>/checklist — the read-only enrichment endpoint
that backs the timeline detail modal (active to-dos + meeting notes for one release)."""
from datetime import date, datetime

from app.models import db, Meeting, ChecklistItem
from tests.conftest import make_user, make_release


def _item(meeting_id, release_id, **over):
    base = dict(
        meeting_id=meeting_id, release_id=release_id, title="t",
        item_type="action", status="accepted",
    )
    base.update(over)
    it = ChecklistItem(**base)
    db.session.add(it)
    return it


def _seed(owner_id):
    """One release with a meeting and a spread of checklist items across statuses."""
    rel = make_release(900, "1", job_name="Test Release")
    meeting = Meeting(
        title="Shop touch-base", meeting_type="internal_shop",
        occurred_at=datetime(2026, 6, 1, 9, 0), summary="Discussed the redo.",
    )
    db.session.add(meeting)
    db.session.flush()

    _item(meeting.id, rel.id, title="Order lintels", status="accepted",
          owner_user_id=owner_id, due_date=date(2026, 6, 10))
    _item(meeting.id, rel.id, title="Closed task", status="done", owner_user_id=owner_id)
    _item(meeting.id, rel.id, title="Still proposed", status="proposed", owner_user_id=owner_id)
    _item(meeting.id, rel.id, title="Rejected task", status="rejected", owner_user_id=owner_id)
    _item(meeting.id, rel.id, title="Accepted but no owner", status="accepted", owner_user_id=None)
    db.session.commit()
    return rel, meeting


def test_returns_active_todos_and_meeting_notes(non_admin_client, mock_non_admin_user):
    rel, meeting = _seed(mock_non_admin_user.id)

    resp = non_admin_client.get(f"/brain/releases/{rel.id}/checklist")
    assert resp.status_code == 200
    data = resp.get_json()

    titles = {t["title"] for t in data["todos"]}
    # accepted + done with an owner only
    assert titles == {"Order lintels", "Closed task"}
    # proposed / rejected / owner-less are excluded
    assert "Still proposed" not in titles
    assert "Rejected task" not in titles
    assert "Accepted but no owner" not in titles

    # each todo carries its source meeting title
    assert all(t["meeting_title"] == "Shop touch-base" for t in data["todos"])

    # lean meeting projection — title/summary present, transcript absent
    assert len(data["meetings"]) == 1
    m = data["meetings"][0]
    assert m["id"] == meeting.id
    assert m["title"] == "Shop touch-base"
    assert m["summary"] == "Discussed the redo."
    assert "transcript" not in m


def test_empty_release_returns_empty_arrays(non_admin_client):
    rel = make_release(901, "1")
    db.session.commit()
    resp = non_admin_client.get(f"/brain/releases/{rel.id}/checklist")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"release_id": rel.id, "todos": [], "meetings": []}


def test_unknown_release_404(non_admin_client):
    resp = non_admin_client.get("/brain/releases/999999/checklist")
    assert resp.status_code == 404


def test_requires_login(app):
    rel = make_release(902, "1")
    db.session.commit()
    resp = app.test_client().get(f"/brain/releases/{rel.id}/checklist")
    assert resp.status_code == 401
