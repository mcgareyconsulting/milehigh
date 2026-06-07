"""Tests for the meeting → checklist → to-do/notify MVP.

Extraction is stubbed/patched so tests are hermetic (no live Anthropic call).
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.models import db, Meeting, ChecklistItem, Notification
from app.brain.meetings import service, extract
from tests.conftest import make_user, make_release


REVIEWER = "boneill@mhmw.com"  # matches Config.CHECKLIST_REVIEWER_USERNAME default


def _items(**over):
    base = dict(title="t", detail=None, item_type="action", owner_name=None,
                due_date=None, gc_facing=False, release_ref=None,
                submittal_ref=None, confidence=None)
    base.update(over)
    return base


def _extract_ret(items):
    """Mimic extract(): items + zeroed (stub) usage, for patching service.extract."""
    return {"items": items,
            "usage": {"input_tokens": 0, "output_tokens": 0, "model": "stub", "cost_usd": 0.0}}


# --------------------------------------------------------------------------- #
# Extractor (deterministic stub path)
# --------------------------------------------------------------------------- #
def test_stub_extractor_picks_action_lines_skips_chitchat(app):
    transcript = (
        "Shop touch-base\n"
        "- 480-146 redo needed, did not fit, need to redo today\n"
        "- Luis to order galvanized lintels by Thursday\n"
        "- talked about the weekend\n"
    )
    with patch.object(extract.cfg, "ANTHROPIC_API_KEY", None):  # force stub
        items = extract.extract_items(transcript)
    titles = [i["title"] for i in items]
    assert any("480-146" in t for t in titles)
    assert any("lintels" in t for t in titles)
    assert not any("weekend" in t for t in titles)  # chit-chat excluded
    ref = next(i for i in items if "480-146" in i["title"])
    assert ref["release_ref"] == "480-146"


# --------------------------------------------------------------------------- #
# Service: ingest + extract + notify reviewer
# --------------------------------------------------------------------------- #
def test_create_meeting_extracts_links_and_notifies_reviewer(app):
    bill = make_user(REVIEWER, first_name="Bill", last_name="O'Neill", is_admin=True)
    make_user("lsolano@mhmw.com", first_name="Luis", last_name="Solano", is_admin=True)
    make_release(480, "146", job_name="Wood Partners - Alta Flatirons", stage="Fitup Start")
    db.session.commit()

    proposed = [
        _items(title="480-146 redo, did not fit", release_ref="480-146", owner_name="Luis"),
        _items(title="Order galvanized lintels", item_type="action"),
    ]
    with patch("app.brain.meetings.service.extract", return_value=_extract_ret(proposed)):
        meeting = service.create_meeting_with_extraction(
            title="Shop touch-base", meeting_type="internal_shop",
            transcript="(stubbed)", created_by_id=bill.id,
        )

    items = meeting.items.order_by(ChecklistItem.id).all()
    assert len(items) == 2
    assert meeting.project_number == "480"          # auto-set from 480-146
    assert items[0].release_id is not None          # auto-linked to the release
    assert items[0].proposed_owner_user_id is not None  # "Luis" resolved
    assert items[0].status == "proposed"
    # reviewer (Bill) got exactly one "checklist ready" notification
    assert Notification.query.filter_by(user_id=bill.id, type="checklist_ready").count() == 1


def test_unresolved_reviewer_does_not_crash(app):
    # No user matches the configured reviewer username → ingestion still succeeds.
    with patch("app.brain.meetings.service.extract", return_value=_extract_ret([_items(title="x")])):
        meeting = service.create_meeting_with_extraction(
            title="m", meeting_type="other", transcript="x",
        )
    assert meeting.items.count() == 1


# --------------------------------------------------------------------------- #
# Service: review (yes / no / edit owner+date)
# --------------------------------------------------------------------------- #
def test_review_accept_defaults_then_overrides_owner_and_due(app):
    bill = make_user(REVIEWER, first_name="Bill", is_admin=True)
    luis = make_user("lsolano@mhmw.com", first_name="Luis", is_admin=True)
    m = Meeting(title="m", meeting_type="internal_shop")
    db.session.add(m); db.session.flush()
    item = ChecklistItem(meeting_id=m.id, title="do thing",
                         proposed_owner_user_id=luis.id, proposed_due_date=date(2026, 6, 10))
    db.session.add(item); db.session.commit()

    # accept with no overrides -> inherits the agent's proposal
    service.review_item(item.id, action="accept", reviewer=bill)
    item = db.session.get(ChecklistItem, item.id)
    assert item.status == "accepted"
    assert item.owner_user_id == luis.id and item.due_date == date(2026, 6, 10)
    assert item.reviewed_by == bill.id and item.reviewed_at is not None

    # edit overrides owner + date (reviewer has final say)
    service.review_item(item.id, fields={"owner_user_id": bill.id, "due_date": "2026-07-01"},
                        reviewer=bill)
    item = db.session.get(ChecklistItem, item.id)
    assert item.owner_user_id == bill.id and item.due_date == date(2026, 7, 1)


def test_review_reject(app):
    m = Meeting(title="m", meeting_type="other")
    db.session.add(m); db.session.flush()
    item = ChecklistItem(meeting_id=m.id, title="nope")
    db.session.add(item); db.session.commit()
    service.review_item(item.id, action="reject")
    assert db.session.get(ChecklistItem, item.id).status == "rejected"


# --------------------------------------------------------------------------- #
# Service: deadline notifications + dedup
# --------------------------------------------------------------------------- #
def test_notify_due_items_pings_owner_once(app):
    owner = make_user("lsolano@mhmw.com", first_name="Luis", is_admin=True)
    m = Meeting(title="m", meeting_type="other")
    db.session.add(m); db.session.flush()
    item = ChecklistItem(meeting_id=m.id, title="due soon", status="accepted",
                         owner_user_id=owner.id, due_date=date(2026, 6, 2))
    db.session.add(item); db.session.commit()

    sent = service.notify_due_items(today=date(2026, 6, 2))
    assert sent == 1
    note = Notification.query.filter_by(user_id=owner.id, type="checklist_due").first()
    assert note is not None and note.checklist_item_id == item.id
    # dedup: a second scan in the same window sends nothing
    assert service.notify_due_items(today=date(2026, 6, 2)) == 0


def test_notify_skips_unaccepted_and_far_future(app):
    owner = make_user("lsolano@mhmw.com", first_name="Luis", is_admin=True)
    m = Meeting(title="m", meeting_type="other")
    db.session.add(m); db.session.flush()
    db.session.add_all([
        ChecklistItem(meeting_id=m.id, title="proposed", status="proposed",
                      owner_user_id=owner.id, due_date=date(2026, 6, 2)),
        ChecklistItem(meeting_id=m.id, title="far off", status="accepted",
                      owner_user_id=owner.id, due_date=date(2026, 12, 31)),
    ])
    db.session.commit()
    assert service.notify_due_items(today=date(2026, 6, 2)) == 0


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #
def test_create_meeting_endpoint_rejects_non_admin(client, mock_non_admin_user):
    with patch("app.auth.utils.get_current_user", return_value=mock_non_admin_user):
        resp = client.post("/brain/meetings", json={"transcript": "x"})
    assert resp.status_code == 403


def test_create_and_review_endpoints_happy_path(app, client):
    admin = make_user(REVIEWER, first_name="Bill", is_admin=True)
    proposed = [_items(title="do the thing")]
    with patch("app.auth.utils.get_current_user", return_value=admin), \
         patch("app.brain.meetings.routes.get_current_user", return_value=admin), \
         patch("app.brain.meetings.service.extract", return_value=_extract_ret(proposed)):
        resp = client.post("/brain/meetings", json={
            "title": "Shop", "meeting_type": "internal_shop", "transcript": "(stub)",
        })
        assert resp.status_code == 201
        item_id = resp.get_json()["items"][0]["id"]

        resp = client.patch(f"/brain/checklist-items/{item_id}", json={
            "action": "accept", "fields": {"due_date": "2026-06-15"},
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "accepted" and body["due_date"] == "2026-06-15"


def test_create_meeting_endpoint_requires_transcript(app, client):
    admin = make_user(REVIEWER, first_name="Bill", is_admin=True)
    with patch("app.auth.utils.get_current_user", return_value=admin):
        resp = client.post("/brain/meetings", json={"title": "x"})
    assert resp.status_code == 400
