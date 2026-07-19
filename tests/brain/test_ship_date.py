"""
Tests for the ship_date feature on Releases:
  - PATCH /brain/update-ship-date/<job>/<release> — set, clear, invalid date, 404
  - UpdateShipDateCommand — writes the row + emits an event, no Trello/scheduling
  - undo of update_ship_date via POST /brain/events/<id>/undo
  - neutralize_install_date_cascade also strips ship_date color on completion

ship_date is a plain hard date: no Trello push, no comp_eta/scheduling recompute.
Uses the real in-memory SQLite DB. admin_client (tests/brain/conftest.py) auths as admin.
"""
import json
from datetime import date
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from app.models import Releases, ReleaseEvents, db
from tests.conftest import make_release


def _seed_event(*, job, release, action, payload, source='Brain'):
    """Create a ReleaseEvents row directly (bypasses JobEventService dedup)."""
    import hashlib, time
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    bucket = int(time.time() // 30)
    hash_string = f"{action}:{job}:{release}:{payload_json}:{bucket}"
    payload_hash = hashlib.sha256(hash_string.encode('utf-8')).hexdigest()
    ev = ReleaseEvents(
        job=job, release=release, action=action, payload=payload,
        payload_hash=payload_hash, source=source, internal_user_id=1,
    )
    db.session.add(ev)
    db.session.flush()
    return ev


def _patch_undo_side_effects():
    """The bundled-undo path runs a scheduling recalc at the end; patch it out."""
    stack = ExitStack()
    stack.enter_context(patch(
        'app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling'
    ))
    return stack


# --- PATCH /brain/update-ship-date/<job>/<release> --------------------------------

class TestUpdateShipDateRoute:
    def test_set_ship_date(self, admin_client, app):
        with app.app_context():
            make_release(500, 'A', ship_date=None)
            db.session.commit()

            resp = admin_client.patch(
                '/brain/update-ship-date/500/A',
                json={'ship_date': '2026-09-15'},
            )

            assert resp.status_code == 200, resp.get_json()
            db.session.expire_all()
            rel = Releases.query.filter_by(job=500, release='A').first()
            assert rel.ship_date == date(2026, 9, 15)
            assert rel.ship_date_no_color is False
            ev = ReleaseEvents.query.filter_by(job=500, release='A', action='update_ship_date').first()
            assert ev is not None
            assert ev.payload['to'] == '2026-09-15'

    def test_clear_ship_date(self, admin_client, app):
        with app.app_context():
            make_release(501, 'A', ship_date=date(2026, 9, 15))
            db.session.commit()

            resp = admin_client.patch(
                '/brain/update-ship-date/501/A',
                json={'ship_date': None},
            )

            assert resp.status_code == 200, resp.get_json()
            db.session.expire_all()
            rel = Releases.query.filter_by(job=501, release='A').first()
            assert rel.ship_date is None

    def test_invalid_date_returns_400(self, admin_client, app):
        with app.app_context():
            make_release(502, 'A')
            db.session.commit()

            resp = admin_client.patch(
                '/brain/update-ship-date/502/A',
                json={'ship_date': 'not-a-date'},
            )

            assert resp.status_code == 400

    def test_missing_release_returns_404(self, admin_client, app):
        with app.app_context():
            resp = admin_client.patch(
                '/brain/update-ship-date/999/Z',
                json={'ship_date': '2026-09-15'},
            )
            assert resp.status_code == 404

    def test_clear_hard_date_also_drops_ship_date(self, admin_client, app):
        """Clearing the hard start_install (revert to formula) drops the tied ship date."""
        with app.app_context():
            make_release(
                504, 'A',
                start_install=date(2026, 9, 16), start_install_formulaTF=False,
                ship_date=date(2026, 9, 15),
            )
            db.session.commit()

            with patch('app.brain.job_log.routes.update_trello_card'), \
                 patch('app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling'):
                resp = admin_client.patch(
                    '/brain/update-start-install/504/A',
                    json={'clear_hard_date': True},
                )

            assert resp.status_code == 200, resp.get_json()
            db.session.expire_all()
            rel = Releases.query.filter_by(job=504, release='A').first()
            assert rel.start_install_formulaTF is True
            assert rel.ship_date is None
            assert rel.ship_date_no_color is False

    def test_does_not_push_trello_or_recalc(self, admin_client, app):
        """Setting a ship date must not touch Trello or the scheduling cascade."""
        with app.app_context():
            make_release(503, 'A', trello_card_id='card-503')
            db.session.commit()

            with patch('app.brain.job_log.routes.update_trello_card') as m_trello, \
                 patch('app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling') as m_recalc:
                resp = admin_client.patch(
                    '/brain/update-ship-date/503/A',
                    json={'ship_date': '2026-09-15'},
                )

            assert resp.status_code == 200, resp.get_json()
            m_trello.assert_not_called()
            m_recalc.assert_not_called()


# --- undo of update_ship_date -----------------------------------------------------

def test_undo_update_ship_date_reverts_release(admin_client, app):
    with app.app_context():
        make_release(510, 'A', ship_date=date(2026, 6, 1))
        ev = _seed_event(
            job=510, release='A',
            action='update_ship_date',
            payload={'from': '2026-05-15', 'to': '2026-06-01'},
        )
        db.session.commit()

        with _patch_undo_side_effects():
            resp = admin_client.post(f'/brain/events/{ev.id}/undo')

        assert resp.status_code == 200, resp.get_json()
        db.session.expire_all()
        rel = Releases.query.filter_by(job=510, release='A').first()
        assert rel.ship_date == date(2026, 5, 15)

        new_ev = db.session.get(ReleaseEvents, resp.get_json()['event_id'])
        assert new_ev.payload['undone_event_id'] == ev.id


# --- completion cascade neutralizes ship color ------------------------------------

def test_neutralize_cascade_strips_ship_color(app):
    from app.brain.job_log.features.start_install.neutralize_install_date_cascade import (
        neutralize_install_date_cascade,
    )
    with app.app_context():
        # Formula-driven install (no install neutralization) but a concrete ship date.
        rel = make_release(
            520, 'A',
            start_install=None, start_install_formulaTF=True,
            ship_date=date(2026, 9, 15), ship_date_no_color=False,
        )
        parent = _seed_event(job=520, release='A', action='update_stage',
                             payload={'from': 'x', 'to': 'Complete'})
        db.session.commit()

        changed = neutralize_install_date_cascade(
            rel, parent_event_id=parent.id, reason='stage_set_to_complete',
        )
        db.session.commit()

        assert changed is True
        db.session.expire_all()
        rel = Releases.query.filter_by(job=520, release='A').first()
        assert rel.ship_date == date(2026, 9, 15)  # date preserved
        assert rel.ship_date_no_color is True       # color stripped
        # A linked child event records the ship-date neutralization.
        child = ReleaseEvents.query.filter_by(job=520, release='A', action='updated').all()
        assert any(
            (c.payload or {}).get('field') == 'ship_date_no_color'
            and (c.payload or {}).get('parent_event_id') == parent.id
            for c in child
        )
