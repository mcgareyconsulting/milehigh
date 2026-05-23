"""
Unit tests for app/procore/reconcile.py — the delayed reconcile safety net.

Covers: coalescing schedule(), process_due() happy/no-op path, the rescue path
(a reconcile that applies a change the live webhook missed → SystemLogs WARNING),
and that future-dated rows are not picked up.
"""
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app import create_app
from app.models import db, SubmittalReconcile, SystemLogs


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _record_mock():
    record = MagicMock()
    record.title = "Trash Enclosure Bollards"
    record.project_name = "Flats at Sand Creek"
    return record


# ---- schedule() ----

class TestSchedule:
    def test_creates_pending_row(self, app):
        from app.procore.reconcile import ProcoreReconcileService

        ProcoreReconcileService.schedule("69723920", 3462738, delay_seconds=60)

        rows = SubmittalReconcile.query.all()
        assert len(rows) == 1
        assert rows[0].submittal_id == "69723920"
        assert rows[0].project_id == 3462738
        assert rows[0].status == "pending"
        assert rows[0].scheduled_for > datetime.utcnow()

    def test_coalesces_duplicate_pending(self, app):
        """A burst of deliveries must produce a single pending reconcile."""
        from app.procore.reconcile import ProcoreReconcileService

        ProcoreReconcileService.schedule("42", 99)
        ProcoreReconcileService.schedule("42", 99)
        ProcoreReconcileService.schedule("42", 99)

        pending = SubmittalReconcile.query.filter_by(submittal_id="42", status="pending").all()
        assert len(pending) == 1

    def test_completed_row_does_not_block_new_schedule(self, app):
        """Once a reconcile is done, a later webhook can schedule a fresh one."""
        from app.procore.reconcile import ProcoreReconcileService

        first = ProcoreReconcileService.schedule("42", 99)
        first.status = "completed"
        db.session.commit()

        ProcoreReconcileService.schedule("42", 99)
        assert SubmittalReconcile.query.filter_by(submittal_id="42").count() == 2

    def test_uses_config_default_delay(self, app):
        from app.procore.reconcile import ProcoreReconcileService

        app.config["PROCORE_RECONCILE_DELAY_SECONDS"] = 60
        before = datetime.utcnow()
        ProcoreReconcileService.schedule("42", 99)
        row = SubmittalReconcile.query.first()
        # Default is 60s (Config.PROCORE_RECONCILE_DELAY_SECONDS); allow scheduling slack.
        assert row.scheduled_for >= before + timedelta(seconds=55)


# ---- process_due() ----

class TestProcessDue:
    def _due_row(self, submittal_id="42", project_id=99):
        row = SubmittalReconcile(
            submittal_id=submittal_id,
            project_id=project_id,
            scheduled_for=datetime.utcnow() - timedelta(seconds=1),
            status="pending",
        )
        db.session.add(row)
        db.session.commit()
        return row

    def test_skips_future_rows(self, app):
        from app.procore.reconcile import ProcoreReconcileService

        db.session.add(SubmittalReconcile(
            submittal_id="42", project_id=99,
            scheduled_for=datetime.utcnow() + timedelta(minutes=5), status="pending",
        ))
        db.session.commit()

        with patch("app.procore.procore.check_and_update_submittal") as mock_cau:
            processed = ProcoreReconcileService.process_due()

        assert processed == 0
        mock_cau.assert_not_called()

    def test_noop_reconcile_completes_without_systemlog(self, app):
        from app.procore.reconcile import ProcoreReconcileService

        row = self._due_row()
        # No fields changed → tuple of all-False.
        with patch(
            "app.procore.procore.check_and_update_submittal",
            return_value=(False, False, False, False, _record_mock(), "x", "Open"),
        ):
            processed = ProcoreReconcileService.process_due()

        assert processed == 1
        db.session.refresh(row)
        assert row.status == "completed"
        assert row.completed_at is not None
        assert SystemLogs.query.filter_by(operation="reconcile_rescue").count() == 0

    def test_rescue_writes_systemlog_warning(self, app):
        """A reconcile that catches a missed status change must surface a WARNING."""
        from app.procore.reconcile import ProcoreReconcileService

        row = self._due_row(submittal_id="69723920", project_id=3462738)
        # status_updated=True → the live webhook missed the status flip (the real bug).
        with patch(
            "app.procore.procore.check_and_update_submittal",
            return_value=(False, True, False, False, _record_mock(), "x", "Closed"),
        ):
            ProcoreReconcileService.process_due()

        db.session.refresh(row)
        assert row.status == "completed"

        logs = SystemLogs.query.filter_by(operation="reconcile_rescue").all()
        assert len(logs) == 1
        assert logs[0].level == "WARNING"
        assert logs[0].category == "procore"
        assert "status" in logs[0].context["rescued_fields"]
        assert logs[0].context["submittal_id"] == "69723920"

    def test_failure_reschedules_then_fails_after_cap(self, app):
        from app.procore.reconcile import ProcoreReconcileService
        from app.procore import reconcile as reconcile_mod

        row = self._due_row()
        with patch(
            "app.procore.procore.check_and_update_submittal",
            side_effect=RuntimeError("procore api down"),
        ):
            # First attempts re-arm as pending; the cap flips it to failed.
            for _ in range(reconcile_mod.MAX_RECONCILE_ATTEMPTS):
                # Make the row due again before each pass.
                row.scheduled_for = datetime.utcnow() - timedelta(seconds=1)
                db.session.commit()
                ProcoreReconcileService.process_due()

        db.session.refresh(row)
        assert row.status == "failed"
        assert row.attempts == reconcile_mod.MAX_RECONCILE_ATTEMPTS
        assert "procore api down" in (row.last_error or "")
