"""BUG-19: an unnumbered submittal that comes back from a review group is invisible.

A numbered submittal that bounces back jumps to the top of the drafter's list in an
urgency slot. One that was worked WITHOUT a number returns into the unnumbered bucket at
the bottom of the list, which drafters don't read — Colton has missed real work this way
[bill-2026-09-02#L1590].

The rows arrive unnumbered because leaving 'Open' clears order_number on the way out
(check_and_update_submittal), so the return had nothing for the plain ladder bump to act
on and it silently no-oped.

Scope boundary, deliberate (Daniel, 2026-09-03): this covers the multiple-assignees ->
single return only. A single -> single ball-in-court move is a drafter reassignment the
engineering lead communicates directly, not a bounce-back, and must not jump the queue.
"""
from unittest.mock import patch

from app.models import Submittals, SubmittalEvents, db
from app.procore.procore import check_and_update_submittal


def _submittal(submittal_id="1001", ball_in_court="Colton, Bill", status="Open",
               order_number=None, was_multiple_assignees=True):
    record = Submittals(
        submittal_id=submittal_id,
        procore_project_id="99",
        project_number="600",
        project_name="Project Phoenix",
        title="Submittal 1001",
        status=status,
        ball_in_court=ball_in_court,
        submittal_drafting_status="",
        order_number=order_number,
        was_multiple_assignees=was_multiple_assignees,
    )
    db.session.add(record)
    db.session.commit()
    return record


def _parsed(ball_in_court, status="Open", title="Submittal 1001",
            approvers=None, manager=None):
    """The 6-tuple handle_submittal_update returns to check_and_update_submittal.

    approvers stays None so the submitter-pending trigger cannot fire and these tests
    isolate the group return.
    """
    return (None, ball_in_court, approvers, status, title, manager)


def test_unnumbered_group_return_is_promoted(app):
    """The regression. Group -> single drafter, no order number: must land in a slot."""
    _submittal(ball_in_court="Colton, Bill", order_number=None)

    with patch("app.procore.procore.handle_submittal_update",
               return_value=_parsed("Colton")):
        check_and_update_submittal(99, "1001")

    record = Submittals.query.filter_by(submittal_id="1001").first()
    assert record.order_number == 0.9
    assert record.was_multiple_assignees is False


def test_unnumbered_group_return_is_auditable(app):
    """The promotion has to show up in the event stream, not just in the row."""
    _submittal(ball_in_court="Colton, Bill", order_number=None)

    with patch("app.procore.procore.handle_submittal_update",
               return_value=_parsed("Colton")):
        check_and_update_submittal(99, "1001")

    event = SubmittalEvents.query.filter_by(submittal_id="1001").one()
    assert event.payload["order_bumped"] is True
    assert event.payload["order_number"] == 0.9


def test_unnumbered_group_return_takes_the_slot_above_the_incumbent(app):
    """It joins the ladder like any bounce-back: 0.9, and the incumbent slides down."""
    _submittal(submittal_id="1001", ball_in_court="Colton, Bill", order_number=None)
    _submittal(submittal_id="2002", ball_in_court="Colton",
               order_number=0.9, was_multiple_assignees=False)

    with patch("app.procore.procore.handle_submittal_update",
               return_value=_parsed("Colton")):
        check_and_update_submittal(99, "1001")

    assert Submittals.query.filter_by(submittal_id="1001").first().order_number == 0.9
    assert Submittals.query.filter_by(submittal_id="2002").first().order_number == 0.8


def test_numbered_group_return_is_unchanged(app):
    """The behaviour that already worked keeps working."""
    _submittal(ball_in_court="Colton, Bill", order_number=5)

    with patch("app.procore.procore.handle_submittal_update",
               return_value=_parsed("Colton")):
        check_and_update_submittal(99, "1001")

    assert Submittals.query.filter_by(submittal_id="1001").first().order_number == 0.9


def test_unnumbered_single_to_single_move_is_left_alone(app):
    """The boundary: a drafter reassignment is not a bounce-back and must not promote."""
    _submittal(ball_in_court="Colton", order_number=None, was_multiple_assignees=False)

    with patch("app.procore.procore.handle_submittal_update",
               return_value=_parsed("Dalton")):
        check_and_update_submittal(99, "1001")

    record = Submittals.query.filter_by(submittal_id="1001").first()
    assert record.ball_in_court == "Dalton"
    assert record.order_number is None
