"""Tests for ASAP Mode on Start Install.

ASAP is a visual flag on a release. While set, when the release transitions
into stage 'Paint Complete', UpdateStageCommand intercepts and rips it
straight to 'Ship Planning' — one event in DB (action='update_stage',
payload includes asap_intercepted/via), one Trello move (to Shipping
planning list).
"""
from unittest.mock import patch

import pytest

from app.models import Releases, ReleaseEvents, db


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user):
        yield


def _make_release(job, release, **kwargs):
    defaults = dict(
        job=job,
        release=release,
        job_name="Test Job",
        stage="Paint Start",
        stage_group="FABRICATION",
        fab_order=12.5,
        start_install_formulaTF=True,
        start_install_asap=False,
    )
    defaults.update(kwargs)
    r = Releases(**defaults)
    db.session.add(r)
    db.session.flush()
    return r


def _stage_command_patches():
    return [
        patch("app.services.outbox_service.OutboxService.add"),
        patch("app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling"),
        patch("app.brain.job_log.routes.get_list_id_by_stage", return_value="list-1"),
    ]


# ---------------------------------------------------------------------------
# Route: set / clear ASAP
# ---------------------------------------------------------------------------

class TestSetClearAsapRoute:
    def test_set_asap_flips_flag_and_emits_event(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"asap": True},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body.get("start_install_asap") is True

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install_asap is True

            evs = ReleaseEvents.query.filter_by(action="set_asap").all()
            assert len(evs) == 1
            assert evs[0].payload == {"from": False, "to": True}

    def test_clear_asap_flips_flag_and_emits_event(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A", start_install_asap=True)
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"asap": False},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install_asap is False

            evs = ReleaseEvents.query.filter_by(action="clear_asap").all()
            assert len(evs) == 1
            assert evs[0].payload == {"from": True, "to": False}

    def test_set_asap_does_not_touch_start_install_fields(self, app, admin_client):
        """ASAP is a flag only — formula-driven scheduling stays untouched."""
        from datetime import date

        with app.app_context():
            _make_release(
                1, "A",
                start_install=date(2026, 6, 1),
                start_install_formula="=released+30d",
                start_install_formulaTF=True,
            )
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"asap": True},
            )
            assert resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install == date(2026, 6, 1)
            assert r2.start_install_formula == "=released+30d"
            assert r2.start_install_formulaTF is True


# ---------------------------------------------------------------------------
# UpdateStageCommand: Paint Complete + ASAP → Ship Planning
# ---------------------------------------------------------------------------

class TestAsapAutoAdvance:
    def test_paint_complete_with_asap_advances_to_ship_planning(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Paint Start",
                fab_order=12.5,
                start_install_asap=True,
                trello_card_id="card-123",
                trello_list_name="Paint start",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            from app.services.outbox_service import OutboxService

            patches = _stage_command_patches()
            with patches[0] as outbox_add, patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Paint Complete").execute()

            db.session.refresh(r)
            assert r.stage == "Ship Planning"
            assert r.stage_group == "READY_TO_SHIP"
            # Ship Planning is fixed tier 2
            assert r.fab_order == 2
            # ASAP flag stays set — admin manually clears
            assert r.start_install_asap is True

            stage_event = ReleaseEvents.query.filter_by(action="update_stage").one()
            assert stage_event.payload["from"] == "Paint Start"
            assert stage_event.payload["to"] == "Ship Planning"
            assert stage_event.payload.get("asap_intercepted") is True
            assert stage_event.payload.get("via") == "Paint Complete"

            # Exactly one Trello outbox enqueue, tied to the stage event
            assert outbox_add.call_count == 1
            kwargs = outbox_add.call_args.kwargs
            assert kwargs["destination"] == "trello"
            assert kwargs["action"] == "move_card"
            assert kwargs["event_id"] == stage_event.id

    def test_paint_complete_without_asap_behaves_normally(self, app):
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Paint Start",
                fab_order=12.5,
                start_install_asap=False,
                trello_card_id="card-123",
                trello_list_name="Paint start",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Paint Complete").execute()

            db.session.refresh(r)
            assert r.stage == "Paint Complete"
            stage_event = ReleaseEvents.query.filter_by(action="update_stage").one()
            assert stage_event.payload["to"] == "Paint Complete"
            assert stage_event.payload.get("asap_intercepted") is None

    def test_re_apply_paint_complete_when_already_ship_planning_is_noop(self, app):
        """Idempotency guard: if release is already at Ship Planning when stage=Paint
        Complete is dispatched (e.g. a stale UI click), don't re-cascade."""
        with app.app_context():
            r = _make_release(
                1, "A",
                stage="Ship Planning",
                fab_order=2,
                start_install_asap=True,
                trello_card_id="card-123",
            )
            db.session.commit()

            from app.brain.job_log.features.stage.command import UpdateStageCommand
            patches = _stage_command_patches()
            with patches[0], patches[1], patches[2]:
                UpdateStageCommand(job_id=1, release="A", stage="Paint Complete").execute()

            db.session.refresh(r)
            # Not intercepted — old_stage was already 'Ship Planning' so the guard
            # bypasses the override. Normal Paint Complete transition occurs.
            assert r.stage == "Paint Complete"
            ev = ReleaseEvents.query.filter_by(action="update_stage").one()
            assert ev.payload["to"] == "Paint Complete"
            assert ev.payload.get("asap_intercepted") is None


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

class TestAsapUndo:
    def test_undo_set_asap_clears_flag(self, app, admin_client):
        with app.app_context():
            _make_release(1, "A")
            db.session.commit()

            resp = admin_client.patch(
                "/brain/update-start-install/1/A",
                json={"asap": True},
            )
            assert resp.status_code == 200
            set_event_id = resp.get_json()["event_id"]

            undo_resp = admin_client.post(f"/brain/events/{set_event_id}/undo")
            assert undo_resp.status_code == 200

            db.session.expire_all()
            r2 = Releases.query.filter_by(job=1, release="A").first()
            assert r2.start_install_asap is False

            # A new clear_asap event was emitted, linked to the original
            undo_events = [
                e for e in ReleaseEvents.query.all()
                if isinstance(e.payload, dict) and e.payload.get("undone_event_id") == set_event_id
            ]
            assert len(undo_events) == 1
            assert undo_events[0].action == "clear_asap"
