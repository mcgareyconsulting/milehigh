"""
Verify the retry-on-mismatch behavior in check_and_update_submittal.

Procore commits multi-field updates non-atomically: a single webhook poll-back
can return BIC updated but status stale, or vice versa. When the first read
disagrees with the DB, the handler sleeps briefly and re-reads; if the second
read differs, it prefers the later read. See docs/procore-webhook-plan.md
Phase 1.3.
"""
from unittest.mock import patch

import pytest

from app import create_app
from app.models import Submittals, db


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["PROCORE_WEBHOOK_RETRY_ENABLED"] = True
    app.config["PROCORE_WEBHOOK_RETRY_DELAY_SECONDS"] = 0.0
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _seed_submittal(**overrides):
    defaults = dict(
        submittal_id="999",
        procore_project_id=1,
        project_name="Test Project",
        title="Test Submittal",
        status="Open",
        ball_in_court="Alice",
        submittal_manager="Manager A",
    )
    defaults.update(overrides)
    record = Submittals(**defaults)
    db.session.add(record)
    db.session.commit()
    return record


def _result(ball=None, status=None, title=None, manager=None, approvers=None):
    """Match handle_submittal_update's tuple shape."""
    return (None, ball, approvers or [], status, title, manager)


class TestRetryOnMismatch:
    def test_stale_then_fresh_prefers_fresh(self, app):
        """First Procore read shows stale BIC; retry returns fresh BIC; handler applies fresh."""
        from app.procore import procore as procore_mod

        _seed_submittal(ball_in_court="Alice", status="Open", title="T", submittal_manager="M")

        # First read: BIC unchanged from DB but status changed (forces no mismatch detected
        # against DB? Actually we want a mismatch to trigger the retry). Use ball changed
        # to "Bob" stale, then "Carol" fresh — both differ from DB Alice, so retry triggers.
        stale = _result(ball="Bob", status="Open", title="T", manager="M")
        fresh = _result(ball="Carol", status="Open", title="T", manager="M")

        # patch sleep to ensure we don't actually wait
        with patch.object(procore_mod, "handle_submittal_update", side_effect=[stale, fresh]) as h, \
             patch.object(procore_mod.time, "sleep") as mock_sleep:
            ball_updated, _, _, _, record, ball_in_court, _ = procore_mod.check_and_update_submittal(
                project_id=1, submittal_id="999"
            )

        assert h.call_count == 2
        mock_sleep.assert_called_once()
        assert ball_updated is True
        assert ball_in_court == "Carol"
        assert record.ball_in_court == "Carol"

    def test_identical_reads_apply_once_no_double_apply(self, app):
        """First read matches second read: apply once, no double-apply."""
        from app.procore import procore as procore_mod

        _seed_submittal(ball_in_court="Alice", status="Open")

        same = _result(ball="Bob", status="Open", title="Test Submittal", manager="Manager A")

        with patch.object(procore_mod, "handle_submittal_update", side_effect=[same, same]) as h, \
             patch.object(procore_mod.time, "sleep"):
            ball_updated, _, _, _, record, ball_in_court, _ = procore_mod.check_and_update_submittal(
                project_id=1, submittal_id="999"
            )

        # Retry fires (DB had Alice, first read had Bob → mismatch)
        assert h.call_count == 2
        assert ball_updated is True
        assert ball_in_court == "Bob"
        # Single applied state, not duplicated
        assert record.ball_in_court == "Bob"

    def test_no_mismatch_skips_retry(self, app):
        """When the first Procore read matches the DB on every tracked field, no retry."""
        from app.procore import procore as procore_mod

        _seed_submittal(
            ball_in_court="Alice", status="Open", title="Test Submittal", submittal_manager="Manager A"
        )

        in_sync = _result(ball="Alice", status="Open", title="Test Submittal", manager="Manager A")

        with patch.object(procore_mod, "handle_submittal_update", side_effect=[in_sync]) as h, \
             patch.object(procore_mod.time, "sleep") as mock_sleep:
            ball_updated, status_updated, title_updated, manager_updated, *_ = (
                procore_mod.check_and_update_submittal(project_id=1, submittal_id="999")
            )

        assert h.call_count == 1
        mock_sleep.assert_not_called()
        assert (ball_updated, status_updated, title_updated, manager_updated) == (False, False, False, False)

    def test_retry_disabled_does_not_retry(self, app):
        """When the config flag is off, retry is skipped even on mismatch."""
        from app.procore import procore as procore_mod

        _seed_submittal(ball_in_court="Alice", status="Open")

        stale = _result(ball="Bob", status="Open", title="Test Submittal", manager="Manager A")

        with patch.object(procore_mod.cfg, "PROCORE_WEBHOOK_RETRY_ENABLED", False), \
             patch.object(procore_mod, "handle_submittal_update", side_effect=[stale]) as h, \
             patch.object(procore_mod.time, "sleep") as mock_sleep:
            procore_mod.check_and_update_submittal(project_id=1, submittal_id="999")

        assert h.call_count == 1
        mock_sleep.assert_not_called()

    def test_retry_returns_none_falls_back_to_first_read(self, app):
        """If the retry call fails (returns None), keep the first read's values."""
        from app.procore import procore as procore_mod

        _seed_submittal(ball_in_court="Alice", status="Open")

        stale = _result(ball="Bob", status="Open", title="Test Submittal", manager="Manager A")

        with patch.object(procore_mod, "handle_submittal_update", side_effect=[stale, None]) as h, \
             patch.object(procore_mod.time, "sleep"):
            ball_updated, _, _, _, record, ball_in_court, _ = procore_mod.check_and_update_submittal(
                project_id=1, submittal_id="999"
            )

        assert h.call_count == 2
        assert ball_updated is True
        assert ball_in_court == "Bob"
        assert record.ball_in_court == "Bob"
