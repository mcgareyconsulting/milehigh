"""
Tests for the StashSession feature — server-side "stash" flow used during
Thursday review meetings.

Covers:
- Service: start/stash/preview/apply/discard
- Idempotency on re-apply and deduplicated events
- Conflict detection (DB drifted vs baseline and new)
- Field apply order and single scheduling cascade at the end
- HTTP endpoints: admin gate, 409 on double-start, preview/apply/discard
"""
from unittest.mock import Mock, patch
from datetime import datetime, date

import pytest

from app.models import (
    Releases, User, StashSession, StashedJobChange, db,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Shared fixtures (app, client, mock_admin_user, mock_non_admin_user) live in
# tests/conftest.py. Auth-patching clients (admin_client, non_admin_client)
# live in tests/brain/conftest.py.


def _make_admin(username="admin_user"):
    u = User(
        username=username,
        password_hash="x",
        is_active=True,
        is_admin=True,
    )
    db.session.add(u)
    db.session.commit()
    return u


def _make_non_admin(username="normal_user"):
    u = User(
        username=username,
        password_hash="x",
        is_active=True,
        is_admin=False,
    )
    db.session.add(u)
    db.session.commit()
    return u


def make_release(job, release, stage="Weld Complete", stage_group="FABRICATION",
                 fab_order=10, job_name="Test", notes=None, job_comp=None,
                 invoiced=None, start_install=None, formulaTF=True):
    r = Releases(
        job=job, release=release, job_name=job_name,
        stage=stage, stage_group=stage_group, fab_order=fab_order,
        notes=notes, job_comp=job_comp, invoiced=invoiced,
        start_install=start_install, start_install_formulaTF=formulaTF,
    )
    db.session.add(r)
    db.session.flush()
    return r


# ---------------------------------------------------------------------------
# Service-level tests (no HTTP layer)
# ---------------------------------------------------------------------------

def test_service_start_creates_active_session(app):
    with app.app_context():
        user = _make_admin()
        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        assert session.id is not None
        assert session.status == 'active'
        assert session.started_by_id == user.id


def test_service_start_fails_when_active_session_exists(app):
    with app.app_context():
        user = _make_admin()
        from app.brain.job_log.features.stash.service import (
            StashSessionService, SessionAlreadyActiveError,
        )
        StashSessionService.start(user)

        with pytest.raises(SessionAlreadyActiveError):
            StashSessionService.start(user)


def test_service_stash_captures_baseline_on_first_insert(app):
    with app.app_context():
        user = _make_admin()
        make_release(1, "A", stage="Weld Complete", fab_order=10)
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        change = StashSessionService.stash_change(
            session_id=session.id, job=1, release="A",
            field='stage', new_value='Paint Start',
        )

        assert change.baseline_value == 'Weld Complete'
        assert change.new_value == 'Paint Start'
        assert change.status == 'pending'


def test_service_stash_upsert_preserves_baseline(app):
    with app.app_context():
        user = _make_admin()
        make_release(1, "A", stage="Weld Complete")
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        StashSessionService.stash_change(session.id, 1, "A", 'stage', 'Paint Start')
        # Second edit on the same cell: baseline must not change.
        c2 = StashSessionService.stash_change(session.id, 1, "A", 'stage', 'Paint complete')

        assert c2.baseline_value == 'Weld Complete'  # original baseline preserved
        assert c2.new_value == 'Paint complete'


def test_service_remove_change(app):
    with app.app_context():
        user = _make_admin()
        make_release(1, "A", stage="Weld Complete")
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        change = StashSessionService.stash_change(session.id, 1, "A", 'stage', 'Paint Start')
        StashSessionService.remove_change(session.id, change.id)

        remaining = StashedJobChange.query.filter_by(session_id=session.id).count()
        assert remaining == 0


def test_service_preview_flags_conflict(app):
    """If the DB drifts to a third value after stashing, preview marks conflict."""
    with app.app_context():
        user = _make_admin()
        r = make_release(1, "A", stage="Weld Complete")
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        StashSessionService.stash_change(session.id, 1, "A", 'stage', 'Paint Start')

        # Simulate a Trello webhook applying a DIFFERENT value directly to DB.
        r.stage = 'Fit Up Complete.'
        db.session.commit()

        preview = StashSessionService.preview(session.id)
        row = preview['changes'][0]
        assert row['current_value'] == 'Fit Up Complete.'
        assert row['baseline_value'] == 'Weld Complete'
        assert row['new_value'] == 'Paint Start'
        assert row['conflict'] is True


def test_service_preview_no_conflict_when_matches_new(app):
    """If the DB already matches the stashed new value, it is not a conflict."""
    with app.app_context():
        user = _make_admin()
        r = make_release(1, "A", stage="Weld Complete")
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        StashSessionService.stash_change(session.id, 1, "A", 'stage', 'Paint Start')

        r.stage = 'Paint Start'
        db.session.commit()

        preview = StashSessionService.preview(session.id)
        row = preview['changes'][0]
        assert row['conflict'] is False


def test_service_apply_marks_session_applied_and_updates_releases(app):
    with app.app_context():
        user = _make_admin()
        make_release(1, "A", stage="Weld Complete", fab_order=10)
        make_release(2, "B", stage="Cut start", fab_order=20)
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        StashSessionService.stash_change(session.id, 1, "A", 'fab_order', 55)
        StashSessionService.stash_change(session.id, 2, "B", 'notes', 'reviewed')

        with patch('app.services.outbox_service.OutboxService.add'), \
             patch('app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling') \
                 as mock_cascade:
            result = StashSessionService.apply(session.id, source="Brain:admin_user")

        assert result['summary']['applied'] == 2
        assert result['summary']['conflicts'] == 0
        assert result['summary']['failed'] == 0
        assert mock_cascade.call_count == 1  # exactly one cascade run

        r1 = Releases.query.filter_by(job=1, release="A").first()
        r2 = Releases.query.filter_by(job=2, release="B").first()
        assert r1.fab_order == 55
        assert r2.notes == 'reviewed'

        session = StashSession.query.get(session.id)
        assert session.status == 'applied'
        assert session.ended_at is not None


def test_service_apply_skips_conflict_rows(app):
    with app.app_context():
        user = _make_admin()
        r1 = make_release(1, "A", stage="Weld Complete", fab_order=10)
        make_release(2, "B", stage="Cut start", fab_order=20)
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        StashSessionService.stash_change(session.id, 1, "A", 'fab_order', 55)
        StashSessionService.stash_change(session.id, 2, "B", 'notes', 'reviewed')

        # Drift release 1 to a third value (not baseline, not new)
        r1.fab_order = 77
        db.session.commit()

        with patch('app.services.outbox_service.OutboxService.add'), \
             patch('app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling'):
            result = StashSessionService.apply(session.id, source="Brain:admin_user")

        assert result['summary']['conflicts'] == 1
        assert result['summary']['applied'] == 1
        assert result['summary']['failed'] == 0

        # Conflict row not touched
        r1_after = Releases.query.filter_by(job=1, release="A").first()
        assert r1_after.fab_order == 77

        # Non-conflict row was applied
        r2_after = Releases.query.filter_by(job=2, release="B").first()
        assert r2_after.notes == 'reviewed'

        session_after = StashSession.query.get(session.id)
        assert session_after.status == 'partial'


def test_service_apply_idempotent_on_already_applied_change(app):
    """Reapplying a session with already-applied rows is a no-op per row."""
    with app.app_context():
        user = _make_admin()
        make_release(1, "A", stage="Weld Complete", fab_order=10)
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        change = StashSessionService.stash_change(session.id, 1, "A", 'fab_order', 55)

        # Pretend this change was already applied in a prior run.
        change.applied_at = datetime.utcnow()
        change.status = 'applied'
        db.session.commit()

        with patch('app.services.outbox_service.OutboxService.add'), \
             patch('app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling'):
            result = StashSessionService.apply(session.id, source="Brain:admin_user")

        # Nothing newly applied; already count > 0 reported via summary
        assert result['summary']['applied'] == 0
        # fab_order was NOT forced back to 55 because the row was already_applied and skipped
        r = Releases.query.filter_by(job=1, release="A").first()
        assert r.fab_order == 10  # untouched


def test_service_apply_no_op_when_db_already_matches(app):
    """If the DB already matches the new value, the change is marked 'no_op'."""
    with app.app_context():
        user = _make_admin()
        make_release(1, "A", stage="Weld Complete", fab_order=10)
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        StashSessionService.stash_change(session.id, 1, "A", 'fab_order', 10)  # same as current

        with patch('app.services.outbox_service.OutboxService.add'), \
             patch('app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling'):
            result = StashSessionService.apply(session.id, source="Brain:admin_user")

        assert result['summary']['no_op'] == 1
        assert result['summary']['applied'] == 0


def test_service_discard_does_not_apply(app):
    with app.app_context():
        user = _make_admin()
        make_release(1, "A", stage="Weld Complete", fab_order=10)
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        StashSessionService.stash_change(session.id, 1, "A", 'fab_order', 55)

        StashSessionService.discard(session.id)

        r = Releases.query.filter_by(job=1, release="A").first()
        assert r.fab_order == 10  # DB untouched

        s = StashSession.query.get(session.id)
        assert s.status == 'discarded'
        assert s.ended_at is not None


def test_service_discard_preserves_change_rows_for_audit(app):
    with app.app_context():
        user = _make_admin()
        make_release(1, "A", stage="Weld Complete")
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        StashSessionService.stash_change(session.id, 1, "A", 'stage', 'Paint Start')

        StashSessionService.discard(session.id)

        # Changes still exist (audit trail)
        count = StashedJobChange.query.filter_by(session_id=session.id).count()
        assert count == 1


def test_service_apply_orders_fields_start_install_before_stage(app):
    """Within a (job, release), start_install applies before stage."""
    with app.app_context():
        user = _make_admin()
        make_release(1, "A", stage="Weld Complete", fab_order=10)
        db.session.commit()

        from app.brain.job_log.features.stash.service import StashSessionService

        session = StashSessionService.start(user)
        # Insert stage change FIRST so natural ordering would be stage-first
        StashSessionService.stash_change(session.id, 1, "A", 'stage', 'Paint Start')
        StashSessionService.stash_change(
            session.id, 1, "A", 'start_install',
            {'action': 'set', 'date': '2026-07-15', 'is_hard_date': True},
        )

        call_log = []
        orig_apply = None

        def _spy_apply(change, source="Brain"):
            call_log.append(change.field)
            # Mark applied so the caller doesn't treat as failed
            change.status = 'applied'
            change.applied_at = datetime.utcnow()

        with patch('app.brain.job_log.features.stash.service.apply_change', side_effect=_spy_apply), \
             patch('app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling'):
            StashSessionService.apply(session.id)

        # start_install must apply before stage
        assert call_log.index('start_install') < call_log.index('stage')


# ---------------------------------------------------------------------------
# HTTP endpoint tests (via Flask test client)
# ---------------------------------------------------------------------------

def test_endpoint_start_session_returns_201_for_admin(admin_client, app):
    resp = admin_client.post('/brain/stash-sessions')
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['session']['status'] == 'active'


def test_endpoint_start_session_409_when_active_exists(admin_client, app):
    with app.app_context():
        admin = _make_admin()
        s = StashSession(started_by_id=admin.id, status='active')
        db.session.add(s)
        db.session.commit()

    resp = admin_client.post('/brain/stash-sessions')
    assert resp.status_code == 409


def test_endpoint_admin_gate_rejects_non_admin(non_admin_client):
    """All stash routes require admin — non-admin receives 403."""
    r1 = non_admin_client.get('/brain/stash-sessions/active')
    assert r1.status_code == 403
    r2 = non_admin_client.post('/brain/stash-sessions')
    assert r2.status_code == 403


def test_endpoint_active_returns_null_when_no_session(admin_client):
    resp = admin_client.get('/brain/stash-sessions/active')
    assert resp.status_code == 200
    assert resp.get_json() == {'session': None}


def test_endpoint_stash_change_upserts(admin_client, app):
    with app.app_context():
        make_release(1, "A", stage="Weld Complete", fab_order=10)
        db.session.commit()

    start = admin_client.post('/brain/stash-sessions').get_json()
    session_id = start['session']['id']

    r1 = admin_client.post(
        f'/brain/stash-sessions/{session_id}/changes',
        json={'job': 1, 'release': 'A', 'field': 'fab_order', 'new_value': 55},
    )
    assert r1.status_code == 200

    # Upsert same cell — should not create a second row
    r2 = admin_client.post(
        f'/brain/stash-sessions/{session_id}/changes',
        json={'job': 1, 'release': 'A', 'field': 'fab_order', 'new_value': 77},
    )
    assert r2.status_code == 200

    with app.app_context():
        rows = StashedJobChange.query.filter_by(session_id=session_id).all()
        assert len(rows) == 1
        assert rows[0].new_value == 77
        assert rows[0].baseline_value == 10  # original baseline preserved


def test_endpoint_stash_change_rejects_unknown_field(admin_client, app):
    with app.app_context():
        make_release(1, "A", stage="Weld Complete")
        db.session.commit()

    session_id = admin_client.post('/brain/stash-sessions').get_json()['session']['id']

    resp = admin_client.post(
        f'/brain/stash-sessions/{session_id}/changes',
        json={'job': 1, 'release': 'A', 'field': 'evil_field', 'new_value': 'x'},
    )
    assert resp.status_code == 400


def test_endpoint_preview_and_apply(admin_client, app):
    with app.app_context():
        make_release(1, "A", stage="Weld Complete", fab_order=10)
        db.session.commit()

    session_id = admin_client.post('/brain/stash-sessions').get_json()['session']['id']
    admin_client.post(
        f'/brain/stash-sessions/{session_id}/changes',
        json={'job': 1, 'release': 'A', 'field': 'fab_order', 'new_value': 55},
    )

    pv = admin_client.get(f'/brain/stash-sessions/{session_id}/preview')
    assert pv.status_code == 200
    preview = pv.get_json()
    assert len(preview['changes']) == 1
    assert preview['changes'][0]['baseline_value'] == 10
    assert preview['changes'][0]['new_value'] == 55

    with patch('app.services.outbox_service.OutboxService.add'), \
         patch('app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling'):
        apply_resp = admin_client.post(f'/brain/stash-sessions/{session_id}/apply')

    assert apply_resp.status_code == 200
    summary = apply_resp.get_json()['summary']
    assert summary['applied'] == 1

    with app.app_context():
        r = Releases.query.filter_by(job=1, release="A").first()
        assert r.fab_order == 55


def test_endpoint_discard(admin_client, app):
    with app.app_context():
        make_release(1, "A", stage="Weld Complete", fab_order=10)
        db.session.commit()

    session_id = admin_client.post('/brain/stash-sessions').get_json()['session']['id']
    admin_client.post(
        f'/brain/stash-sessions/{session_id}/changes',
        json={'job': 1, 'release': 'A', 'field': 'fab_order', 'new_value': 55},
    )

    resp = admin_client.post(f'/brain/stash-sessions/{session_id}/discard')
    assert resp.status_code == 200
    assert resp.get_json()['session']['status'] == 'discarded'

    with app.app_context():
        r = Releases.query.filter_by(job=1, release="A").first()
        assert r.fab_order == 10  # DB untouched
