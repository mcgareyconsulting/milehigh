"""Tests for pre/post-meeting Brain snapshots + agreed-update reconciliation.

The premise: a meeting agrees a release/submittal field should change; the post-meeting
reconciliation flags the to-do brain_update_pending when that change never landed on the
Brain. All LLM calls are patched/forced off so tests stay hermetic.
"""
from datetime import date, datetime, timedelta
from unittest.mock import patch

from app.models import db, Meeting, ChecklistItem, Submittals
from app.brain.meetings import snapshot, service
from tests.conftest import make_user, make_release


REVIEWER = "boneill@mhmw.com"


# --------------------------------------------------------------------------- #
# sanitize_expected_update — only well-formed, allowlisted field changes survive
# --------------------------------------------------------------------------- #
def test_sanitize_accepts_valid_release_and_submittal_updates():
    assert snapshot.sanitize_expected_update(
        {"target": "release", "field": "stage", "new_value": "Ship Complete"}
    ) == {"target": "release", "field": "stage", "new_value": "Ship Complete"}
    assert snapshot.sanitize_expected_update(
        {"target": "submittal", "field": "ball_in_court", "new_value": "GC"}
    ) == {"target": "submittal", "field": "ball_in_court", "new_value": "GC"}


def test_sanitize_rejects_bad_target_field_or_empty():
    # field not in the release allowlist
    assert snapshot.sanitize_expected_update(
        {"target": "release", "field": "job_name", "new_value": "x"}) is None
    # release field used under submittal target
    assert snapshot.sanitize_expected_update(
        {"target": "submittal", "field": "stage", "new_value": "x"}) is None
    # missing value / not a dict
    assert snapshot.sanitize_expected_update(
        {"target": "release", "field": "stage"}) is None
    assert snapshot.sanitize_expected_update("nope") is None


# --------------------------------------------------------------------------- #
# capture_snapshot — records the discussed entities' current field values
# --------------------------------------------------------------------------- #
def test_capture_snapshot_records_release_fields(app):
    make_release(480, "146", job_name="Alta Flatirons", stage="Fabrication",
                 start_install=date(2026, 7, 1))
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", project_number="480")
    db.session.add(m); db.session.commit()

    snap = snapshot.capture_snapshot(m)
    assert "480-146" in snap["releases"]
    cell = snap["releases"]["480-146"]
    assert cell["stage"] == "Fabrication"
    assert cell["start_install"] == "2026-07-01"   # date -> ISO string (JSON-safe)


# --------------------------------------------------------------------------- #
# reconcile — pending when the Brain still shows the old value
# --------------------------------------------------------------------------- #
def _item(meeting, release_id, expected_update):
    it = ChecklistItem(meeting_id=meeting.id, title="x", item_type="action",
                       release_id=release_id, expected_update=expected_update)
    db.session.add(it); db.session.commit()
    return it


def test_reconcile_flags_update_that_never_landed(app):
    r = make_release(480, "146", job_name="Alta", stage="Fabrication")
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", project_number="480")
    db.session.add(m); db.session.commit()
    # Room agreed to mark it shipped, but the Brain still shows Fabrication.
    it = _item(m, r.id, {"target": "release", "field": "stage", "new_value": "Ship Complete"})

    flagged = snapshot.reconcile(m)
    db.session.commit()
    assert flagged == 1
    assert db.session.get(ChecklistItem, it.id).brain_update_pending is True


def test_reconcile_clears_when_brain_already_matches(app):
    r = make_release(480, "146", job_name="Alta", stage="Ship Complete")
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", project_number="480")
    db.session.add(m); db.session.commit()
    it = _item(m, r.id, {"target": "release", "field": "stage", "new_value": "Ship Complete"})

    flagged = snapshot.reconcile(m)
    db.session.commit()
    assert flagged == 0   # Brain already shows the agreed value → nothing pending
    assert db.session.get(ChecklistItem, it.id).brain_update_pending is False


def test_reconcile_matches_dates_across_representations(app):
    r = make_release(480, "146", job_name="Alta", start_install=date(2026, 7, 10))
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", project_number="480")
    db.session.add(m); db.session.commit()
    it = _item(m, r.id,
               {"target": "release", "field": "start_install", "new_value": "2026-07-10"})

    snapshot.reconcile(m)
    db.session.commit()
    assert db.session.get(ChecklistItem, it.id).brain_update_pending is False


def test_reconcile_skips_unanchored_items(app):
    make_release(480, "146", job_name="Alta", stage="Fabrication")
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", project_number="480")
    db.session.add(m); db.session.commit()
    # No release_id → can't verify → never flagged.
    it = _item(m, None, {"target": "release", "field": "stage", "new_value": "Ship Complete"})

    flagged = snapshot.reconcile(m)
    db.session.commit()
    assert flagged == 0
    assert db.session.get(ChecklistItem, it.id).brain_update_pending is False


# --------------------------------------------------------------------------- #
# End-to-end: extract_into_meeting persists expected_update + reconciles + snapshots
# --------------------------------------------------------------------------- #
def test_extract_into_meeting_reconciles_brain_update(app):
    make_user(REVIEWER, first_name="Bill", is_admin=True)
    make_release(480, "146", job_name="Alta Flatirons", stage="Fabrication", pm="WO")
    db.session.commit()
    m = Meeting(title="Shop", meeting_type="internal_shop", project_number="480",
                agenda_text="Cover 480-146", transcript="(stub)",
                occurred_at=datetime(2026, 6, 9))
    db.session.add(m); db.session.commit()

    def fake_extract(transcript, today=None, people=None, context=None):
        return {"items": [{
            "title": "Mark 480-146 shipped", "item_type": "action",
            "release_ref": "480-146", "owner_name": None, "due_date": None,
            "gc_facing": False, "confidence": 0.9,
            "brain_update": {"target": "release", "field": "stage",
                             "new_value": "Ship Complete"},
        }], "usage": {"input_tokens": 0, "output_tokens": 0,
                      "model": "stub", "cost_usd": 0.0}}

    with patch("app.brain.meetings.service.extract", side_effect=fake_extract):
        service.extract_into_meeting(m, notify=False)

    item = ChecklistItem.query.filter_by(meeting_id=m.id).first()
    assert item.expected_update["field"] == "stage"
    assert item.brain_update_pending is True          # Brain still shows Fabrication
    assert m.post_snapshot and "480-146" in m.post_snapshot["releases"]
