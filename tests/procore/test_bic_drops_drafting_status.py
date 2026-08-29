"""BUG-16: a DWL drafting status must not survive a ball-in-court change.

HOLD / STARTED / NEED VIF are set against whoever holds the ball. Once the
submittal moves to someone else the status describes work that is nobody's, so
the Drafting Work Load shows held work that isn't held.

Every path that writes `ball_in_court` has to drop it, not just the webhook —
the roadmap's failure mode is the audit sweep re-syncing BIC and resurrecting
the stale status on the next run. Covered here:
  * app/procore/helpers.drop_drafting_status_for_bic_change (the shared rule)
  * app/procore/procore.check_and_update_submittal          (webhook)
  * POST /procore/health-scan/update                        (audit)
"""
from unittest.mock import patch

import pytest

from app.models import Submittals, SubmittalEvents, db
from app.procore.helpers import drop_drafting_status_for_bic_change
from app.procore.procore import check_and_update_submittal


def _submittal(submittal_id="1001", ball_in_court="Colton",
               drafting_status="HOLD", status="Open", order_number=None):
    record = Submittals(
        submittal_id=submittal_id,
        procore_project_id="99",
        project_number="600",
        project_name="Project Phoenix",
        title="Submittal 1001",
        status=status,
        ball_in_court=ball_in_court,
        submittal_drafting_status=drafting_status,
        order_number=order_number,
    )
    db.session.add(record)
    db.session.commit()
    return record


def _parsed(ball_in_court, status="Open", title="Submittal 1001",
            approvers=None, manager=None):
    """The 6-tuple handle_submittal_update returns to check_and_update_submittal."""
    return (None, ball_in_court, approvers, status, title, manager)


# --- the shared rule ------------------------------------------------------

@pytest.mark.parametrize("held", ["HOLD", "STARTED", "NEED VIF"])
def test_helper_drops_any_drafter_scoped_status(app, held):
    record = _submittal(drafting_status=held)
    assert drop_drafting_status_for_bic_change(record) == held
    assert record.submittal_drafting_status == ""


def test_helper_reports_nothing_to_drop_when_status_blank(app):
    record = _submittal(drafting_status="")
    assert drop_drafting_status_for_bic_change(record) is None
    assert record.submittal_drafting_status == ""


# --- webhook path ---------------------------------------------------------

def test_webhook_bic_change_drops_hold(app):
    _submittal(ball_in_court="Colton", drafting_status="HOLD")

    with patch("app.procore.procore.handle_submittal_update",
               return_value=_parsed("Daniel")):
        ball_updated, *_ = check_and_update_submittal(99, "1001")

    assert ball_updated is True
    record = Submittals.query.filter_by(submittal_id="1001").first()
    assert record.ball_in_court == "Daniel"
    assert record.submittal_drafting_status == ""


def test_webhook_bic_change_records_the_drop_as_an_event(app):
    _submittal(ball_in_court="Colton", drafting_status="HOLD")

    with patch("app.procore.procore.handle_submittal_update",
               return_value=_parsed("Daniel")):
        check_and_update_submittal(99, "1001")

    event = SubmittalEvents.query.filter_by(submittal_id="1001").one()
    assert event.payload["submittal_drafting_status"] == {"old": "HOLD", "new": ""}
    assert event.payload["ball_in_court"] == {"old": "Colton", "new": "Daniel"}


def test_webhook_leaves_status_alone_when_bic_did_not_change(app):
    """A title-only edit is not a hand-off; the drafter still holds the work."""
    _submittal(ball_in_court="Colton", drafting_status="HOLD")

    with patch("app.procore.procore.handle_submittal_update",
               return_value=_parsed("Colton", title="Renamed")):
        ball_updated, *_ = check_and_update_submittal(99, "1001")

    assert ball_updated is False
    record = Submittals.query.filter_by(submittal_id="1001").first()
    assert record.submittal_drafting_status == "HOLD"
    assert record.title == "Renamed"


def test_webhook_event_is_attributed_to_the_submittal_that_moved(app):
    """Regression: the order-compression loop rebound the `submittal_id`
    parameter, so the event landed on the last compressed sibling instead of
    the submittal whose ball actually moved."""
    _submittal(submittal_id="1001", ball_in_court="Colton",
               drafting_status="HOLD", order_number=1)
    # Siblings still in Colton's court, in urgency slots — compress_orders only
    # renumbers the 0 < order < 1 subset, so regular orders would no-op the loop
    # this test exists to cover.
    _submittal(submittal_id="2002", ball_in_court="Colton",
               drafting_status="", order_number=0.1)
    _submittal(submittal_id="3003", ball_in_court="Colton",
               drafting_status="", order_number=0.3)

    with patch("app.procore.procore.handle_submittal_update",
               return_value=_parsed("Daniel")):
        check_and_update_submittal(99, "1001")

    # Compression must actually have run, or this asserts nothing.
    assert Submittals.query.filter_by(submittal_id="3003").first().order_number == 0.9

    events = SubmittalEvents.query.all()
    assert [e.submittal_id for e in events] == ["1001"]


# --- audit path (POST /procore/health-scan/update) -------------------------

def _sync_issue(submittal_id="1001", api_bic="Daniel", db_bic="Colton"):
    return {
        "submittal_id": submittal_id,
        "project_id": "99",
        "title": "Submittal 1001",
        "ball_in_court": {"mismatch": True, "api": api_bic, "db": db_bic},
        "status": {"mismatch": False, "api": "Open", "db": "Open"},
    }


def test_health_scan_update_drops_hold_and_records_it(client, app):
    _submittal(ball_in_court="Colton", drafting_status="HOLD")

    with patch("app.procore.comprehensive_health_scan",
               return_value={"differences": {"sync_issues": [_sync_issue()]}}):
        resp = client.post("/procore/health-scan/update", json={})

    assert resp.status_code == 200
    record = Submittals.query.filter_by(submittal_id="1001").first()
    assert record.ball_in_court == "Daniel"
    assert record.submittal_drafting_status == ""

    event = SubmittalEvents.query.filter_by(submittal_id="1001").one()
    assert event.payload["submittal_drafting_status"] == {"old": "HOLD", "new": ""}


def test_health_scan_update_leaves_blank_status_out_of_the_payload(app, client):
    _submittal(ball_in_court="Colton", drafting_status="")

    with patch("app.procore.comprehensive_health_scan",
               return_value={"differences": {"sync_issues": [_sync_issue()]}}):
        resp = client.post("/procore/health-scan/update", json={})

    assert resp.status_code == 200
    event = SubmittalEvents.query.filter_by(submittal_id="1001").one()
    assert "submittal_drafting_status" not in event.payload
