"""
Tests for the per-event Undo feature on the Events tab (#68).

Covers:
- Each whitelisted action (update_stage, update_notes, update_fab_order,
  update_start_install) — undo reverts the release and writes a new event
  (action unchanged, source stays 'Brain') whose `payload.undone_event_id`
  links back to the source event. That field is the marker for "this is an
  undo".
- Staleness — a target event whose `payload.to` no longer matches the
  current Releases value returns 409.
- Undo events are not themselves undoable — clicking Undo on a row whose
  payload has `undone_event_id` returns 400. (Users edit the value in Job Log
  directly to reverse an undo.)
- Auth — non-admin gets 403.
- Ineligible actions — `email_received`, no-op (from==to), unknown action
  all return 400.
- Events feed enrichment — /brain/events includes `current_value` for
  whitelist rows.
- Cross-group stage rollback — undoing a stage change that crosses stage
  groups (e.g. FABRICATION → READY_TO_SHIP) restores both `stage` and
  `stage_group` correctly.
- Linked-event bundling — when a stage change forces a fab_order side-effect
  (e.g. moving to a fixed-tier stage like 'Shipping planning' which auto-
  assigns fab_order=2), undoing the parent stage event also reverts the
  linked fab_order event in a single atomic operation.
- Stale child — bundle fails 409 if any child has been independently edited.
- DWL (SubmittalEvents) undo — order_number, notes, submittal_drafting_status
  revert via POST /brain/submittal-events/<id>/undo. The Procore-bound `status`
  field is rejected. No Procore API call is triggered.
"""
from unittest.mock import patch
from datetime import date

import pytest

from app.models import Releases, ReleaseEvents, Submittals, SubmittalEvents, db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Shared fixtures (app, client, mock_admin_user, mock_non_admin_user) live in
# tests/conftest.py. admin_client / non_admin_client live in tests/brain/conftest.py.


def _make_release(**overrides):
    defaults = dict(
        job=1234, release='A', job_name='Test Job',
        stage='Welded QC', stage_group='FABRICATION',
        fab_order=10.0, notes=None, start_install=None,
        start_install_formulaTF=True,
    )
    defaults.update(overrides)
    r = Releases(**defaults)
    db.session.add(r)
    db.session.flush()
    return r


def _seed_event(*, job=1234, release='A', action, payload, source='Brain'):
    """Create a ReleaseEvents row directly. Bypasses JobEventService so test
    setup doesn't trigger dedup and we can hand-craft any payload shape."""
    import json, hashlib, time
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


def _make_submittal(submittal_id='SUB-1', **overrides):
    defaults = dict(
        submittal_id=submittal_id,
        order_number=5.0,
        notes=None,
        submittal_drafting_status='',
        status='Open',
    )
    defaults.update(overrides)
    s = Submittals(**defaults)
    db.session.add(s)
    db.session.flush()
    return s


def _seed_submittal_event(*, submittal_id='SUB-1', payload, source='Brain', action='updated'):
    """Mirror create_submittal_event's hash logic but build the row directly so
    tests can hand-craft payloads without going through DWL routes."""
    import json, hashlib
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    payload_hash = hashlib.sha256(
        f"{action}:{submittal_id}:{payload_json}".encode('utf-8')
    ).hexdigest()
    ev = SubmittalEvents(
        submittal_id=str(submittal_id), action=action, payload=payload,
        payload_hash=payload_hash, source=source, internal_user_id=1,
    )
    db.session.add(ev)
    db.session.flush()
    return ev


def _patch_side_effects():
    """Common side-effect patches for the update commands so tests don't
    actually hit Trello or run the scheduling cascade."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch('app.services.outbox_service.OutboxService.add'))
    stack.enter_context(patch(
        'app.brain.job_log.scheduling.service.recalculate_all_jobs_scheduling'
    ))
    stack.enter_context(patch('app.brain.job_log.routes.update_trello_card'))
    return stack


# ---------------------------------------------------------------------------
# Each whitelist action: undo round-trip
# ---------------------------------------------------------------------------

def test_undo_update_stage_reverts_release(admin_client, app):
    with app.app_context():
        rel = _make_release(stage='Paint')
        # Original event: Welded QC -> Paint. Release currently shows 'Paint'.
        ev = _seed_event(action='update_stage', payload={'from': 'Welded QC', 'to': 'Paint'})
        db.session.commit()

        with _patch_side_effects():
            resp = admin_client.post(f'/brain/events/{ev.id}/undo')

        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body['status'] == 'success'
        new_event_id = body['event_id']

        # Release reverted.
        db.session.expire_all()
        rel = Releases.query.filter_by(job=1234, release='A').first()
        assert rel.stage == 'Welded QC'
        # Releases.source_of_update is String(16) — Postgres enforces the cap
        # (SQLite doesn't), so guard against any future change that pipes a
        # longer undo-flavored source into this column.
        assert rel.source_of_update == 'Brain'

        # New event has plain 'Brain' source and undone_event_id link to the original.
        new_ev = db.session.get(ReleaseEvents, new_event_id)
        assert new_ev.source == 'Brain'
        assert new_ev.payload['from'] == 'Paint'
        assert new_ev.payload['to'] == 'Welded QC'
        assert new_ev.payload['undone_event_id'] == ev.id


def test_undo_update_notes_reverts_release(admin_client, app):
    with app.app_context():
        rel = _make_release(notes='New notes')
        ev = _seed_event(
            action='update_notes',
            payload={'from': 'Original notes', 'to': 'New notes'},
        )
        db.session.commit()

        with _patch_side_effects():
            resp = admin_client.post(f'/brain/events/{ev.id}/undo')

        assert resp.status_code == 200, resp.get_json()
        db.session.expire_all()
        rel = Releases.query.filter_by(job=1234, release='A').first()
        assert rel.notes == 'Original notes'

        new_ev = db.session.get(ReleaseEvents, resp.get_json()['event_id'])
        assert new_ev.source == 'Brain'
        assert new_ev.payload['undone_event_id'] == ev.id


def test_undo_update_fab_order_reverts_release(admin_client, app):
    with app.app_context():
        # Stage must be in the FAB queue range (not Complete or fixed-tier)
        # so the command doesn't override the requested fab_order.
        rel = _make_release(stage='Welded QC', fab_order=42.0)
        ev = _seed_event(
            action='update_fab_order',
            payload={'from': 10.0, 'to': 42.0},
        )
        db.session.commit()

        with _patch_side_effects():
            resp = admin_client.post(f'/brain/events/{ev.id}/undo')

        assert resp.status_code == 200, resp.get_json()
        db.session.expire_all()
        rel = Releases.query.filter_by(job=1234, release='A').first()
        assert rel.fab_order == 10.0

        new_ev = db.session.get(ReleaseEvents, resp.get_json()['event_id'])
        assert new_ev.source == 'Brain'
        assert new_ev.payload['undone_event_id'] == ev.id


def test_undo_update_start_install_reverts_release(admin_client, app):
    with app.app_context():
        rel = _make_release(start_install=date(2026, 6, 1), start_install_formulaTF=False)
        ev = _seed_event(
            action='update_start_install',
            payload={
                'from': '2026-05-15',
                'to': '2026-06-01',
                'is_hard_date': True,
            },
        )
        db.session.commit()

        with _patch_side_effects():
            resp = admin_client.post(f'/brain/events/{ev.id}/undo')

        assert resp.status_code == 200, resp.get_json()
        db.session.expire_all()
        rel = Releases.query.filter_by(job=1234, release='A').first()
        assert rel.start_install == date(2026, 5, 15)

        new_ev = db.session.get(ReleaseEvents, resp.get_json()['event_id'])
        assert new_ev.source == 'Brain'
        assert new_ev.payload['undone_event_id'] == ev.id


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------

def test_undo_stale_event_returns_409(admin_client, app):
    with app.app_context():
        # Release stage is 'Complete', but the target event was a transition
        # to 'Paint'. A later edit superseded it — undo would silently
        # overwrite that later change.
        rel = _make_release(stage='Complete')
        ev = _seed_event(action='update_stage', payload={'from': 'Welded QC', 'to': 'Paint'})
        db.session.commit()

        with _patch_side_effects():
            resp = admin_client.post(f'/brain/events/{ev.id}/undo')

        assert resp.status_code == 409
        body = resp.get_json()
        assert body['error'] == 'stale'
        assert body['current'] == 'Complete'
        assert body['expected'] == 'Paint'


# ---------------------------------------------------------------------------
# Undo-the-undo is rejected
# ---------------------------------------------------------------------------

def test_cannot_undo_an_undo_event(admin_client, app):
    """Undo events themselves are not undoable. To reverse an undo, the user
    edits the value directly in Job Log — undo-the-undo via this endpoint
    would muddle the audit trail and complicates the bundling logic.

    Note: `undone_event_id` is still stamped on every undo event's payload.
    Beyond marking the event for the badge, it perturbs the dedup hash —
    a defense-in-depth property even though the path that would have
    triggered the collision (undo-the-undo within 30s) is now blocked at
    the endpoint."""
    with app.app_context():
        _make_release(stage='Paint')
        ev = _seed_event(action='update_stage', payload={'from': 'Welded QC', 'to': 'Paint'})
        db.session.commit()

        with _patch_side_effects():
            r1 = admin_client.post(f'/brain/events/{ev.id}/undo')
            assert r1.status_code == 200, r1.get_json()
            undo_event_id = r1.get_json()['event_id']

            # Trying to undo the undo — rejected.
            r2 = admin_client.post(f'/brain/events/{undo_event_id}/undo')
            assert r2.status_code == 400
            assert 'undoable' in r2.get_json()['error'].lower()

        # The undo event's payload still carries undone_event_id (used by the
        # frontend badge and as dedup-hash defense).
        undo_event = db.session.get(ReleaseEvents, undo_event_id)
        assert undo_event.payload['undone_event_id'] == ev.id


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_undo_non_admin_forbidden(non_admin_client, app):
    with app.app_context():
        _make_release(stage='Paint')
        ev = _seed_event(action='update_stage', payload={'from': 'Welded QC', 'to': 'Paint'})
        db.session.commit()

        resp = non_admin_client.post(f'/brain/events/{ev.id}/undo')
        assert resp.status_code == 403


def test_undo_unauthenticated_returns_401(client, app):
    with app.app_context():
        _make_release(stage='Paint')
        ev = _seed_event(action='update_stage', payload={'from': 'Welded QC', 'to': 'Paint'})
        db.session.commit()
        event_id = ev.id

    resp = client.post(f'/brain/events/{event_id}/undo')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Ineligible inputs
# ---------------------------------------------------------------------------

def test_undo_email_received_action_rejected(admin_client, app):
    with app.app_context():
        _make_release()
        ev = _seed_event(action='email_received', payload={'subject': 'hi'})
        db.session.commit()

        resp = admin_client.post(f'/brain/events/{ev.id}/undo')
        assert resp.status_code == 400
        assert 'not undoable' in resp.get_json()['error'].lower()


def test_undo_noop_event_rejected(admin_client, app):
    with app.app_context():
        _make_release(stage='Paint')
        ev = _seed_event(action='update_stage', payload={'from': 'Paint', 'to': 'Paint'})
        db.session.commit()

        resp = admin_client.post(f'/brain/events/{ev.id}/undo')
        assert resp.status_code == 400


def test_undo_missing_event_returns_404(admin_client, app):
    with app.app_context():
        resp = admin_client.post('/brain/events/99999/undo')
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Events feed enrichment
# ---------------------------------------------------------------------------

def test_events_feed_includes_current_value_for_whitelist(admin_client, app):
    with app.app_context():
        _make_release(stage='Paint', notes='hello', fab_order=42.0)
        _seed_event(action='update_stage', payload={'from': 'Welded QC', 'to': 'Paint'})
        _seed_event(action='update_notes', payload={'from': None, 'to': 'hello'})
        _seed_event(action='update_fab_order', payload={'from': 10.0, 'to': 42.0})
        _seed_event(action='email_received', payload={'subject': 'hi'})
        db.session.commit()

        resp = admin_client.get('/brain/events?limit=50')
        assert resp.status_code == 200
        events = resp.get_json()['events']
        by_action = {e['action']: e for e in events}

        assert by_action['update_stage']['current_value'] == 'Paint'
        assert by_action['update_notes']['current_value'] == 'hello'
        assert by_action['update_fab_order']['current_value'] == 42.0
        # Non-whitelist action gets None.
        assert by_action['email_received']['current_value'] is None


# ---------------------------------------------------------------------------
# Undo marker
# ---------------------------------------------------------------------------
# Undo events are NOT distinguished by source (which stays 'Brain'). The
# `payload.undone_event_id` field is the canonical marker — set by the undo
# endpoint, used by the frontend to render the ↶ undo badge, and available to
# any backend analytics that wants to count undos. The per-action tests above
# already assert `payload.undone_event_id == ev.id`; this section is a stub
# kept so future changes to the marker (if ever) land near the asserts.


# ---------------------------------------------------------------------------
# Cross-stage-group rollback
# ---------------------------------------------------------------------------

def test_undo_cross_group_stage_change_restores_stage_group(admin_client, app):
    """Moving a release into 'Shipping planning' (READY_TO_SHIP) and then
    undoing it must restore stage_group=FABRICATION, not just the stage."""
    with app.app_context():
        rel = _make_release(
            stage='Shipping planning',
            stage_group='READY_TO_SHIP',
            fab_order=2.0,
        )
        ev = _seed_event(
            action='update_stage',
            payload={'from': 'Weld Complete', 'to': 'Shipping planning'},
        )
        db.session.commit()

        with _patch_side_effects():
            resp = admin_client.post(f'/brain/events/{ev.id}/undo')

        assert resp.status_code == 200, resp.get_json()
        db.session.expire_all()
        rel = Releases.query.filter_by(job=1234, release='A').first()
        assert rel.stage == 'Weld Complete'
        # The whole point of this test:
        assert rel.stage_group == 'FABRICATION'


# ---------------------------------------------------------------------------
# Linked-event bundling (parent_event_id)
# ---------------------------------------------------------------------------

def test_undo_bundles_linked_fab_order_child(admin_client, app):
    """Reproduces the 390-428 case from the screenshot: stage transition to a
    fixed-tier stage forces fab_order=2 alongside the stage event. Undoing the
    parent stage event must also revert the child fab_order event."""
    with app.app_context():
        # Live state mirrors what UpdateStageCommand would have produced for a
        # 'Weld Complete' (fab_order=17) → 'Shipping planning' (fab_order=2)
        # transition.
        rel = _make_release(
            stage='Shipping planning',
            stage_group='READY_TO_SHIP',
            fab_order=2.0,
        )
        parent = _seed_event(
            action='update_stage',
            payload={'from': 'Weld Complete', 'to': 'Shipping planning'},
        )
        child = _seed_event(
            action='update_fab_order',
            payload={
                'from': 17.0,
                'to': 2.0,
                'reason': 'stage_change_unified',
                'parent_event_id': parent.id,
            },
        )
        db.session.commit()

        with _patch_side_effects():
            resp = admin_client.post(f'/brain/events/{parent.id}/undo')

        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body['status'] == 'success'
        assert len(body['linked_event_ids']) == 1

        db.session.expire_all()
        rel = Releases.query.filter_by(job=1234, release='A').first()
        assert rel.stage == 'Weld Complete'
        assert rel.stage_group == 'FABRICATION'
        # The fab_order was reverted as a linked side-effect — this is the
        # bug the screenshot revealed.
        assert rel.fab_order == 17.0

        # New parent undo event references the original parent.
        new_parent = db.session.get(ReleaseEvents, body['event_id'])
        assert new_parent.action == 'update_stage'
        assert new_parent.payload['undone_event_id'] == parent.id
        # New child undo event references the original child.
        new_child = db.session.get(ReleaseEvents, body['linked_event_ids'][0])
        assert new_child.action == 'update_fab_order'
        assert new_child.payload['undone_event_id'] == child.id


def test_undo_bundle_fails_when_child_is_stale(admin_client, app):
    """If the child fab_order has been independently edited since the parent
    event, the bundle must fail 409 — partial revert would corrupt state."""
    with app.app_context():
        # Parent event matches live stage. Child says fab_order should be 2,
        # but live fab_order is 5 (someone edited it independently).
        rel = _make_release(
            stage='Shipping planning',
            stage_group='READY_TO_SHIP',
            fab_order=5.0,
        )
        parent = _seed_event(
            action='update_stage',
            payload={'from': 'Weld Complete', 'to': 'Shipping planning'},
        )
        _seed_event(
            action='update_fab_order',
            payload={
                'from': 17.0, 'to': 2.0,
                'reason': 'stage_change_unified',
                'parent_event_id': parent.id,
            },
        )
        db.session.commit()

        with _patch_side_effects():
            resp = admin_client.post(f'/brain/events/{parent.id}/undo')

        assert resp.status_code == 409
        body = resp.get_json()
        assert body['error'] == 'stale'
        assert body['stale_children']
        assert body['stale_children'][0]['action'] == 'update_fab_order'

        # Live state untouched — no partial revert.
        db.session.expire_all()
        rel = Releases.query.filter_by(job=1234, release='A').first()
        assert rel.stage == 'Shipping planning'
        assert rel.fab_order == 5.0


def test_events_feed_includes_linked_children(admin_client, app):
    """The events feed surfaces linked children so the confirm dialog can
    enumerate what will be reverted."""
    with app.app_context():
        _make_release(stage='Shipping planning', fab_order=2.0)
        parent = _seed_event(
            action='update_stage',
            payload={'from': 'Weld Complete', 'to': 'Shipping planning'},
        )
        child = _seed_event(
            action='update_fab_order',
            payload={
                'from': 17.0, 'to': 2.0,
                'reason': 'stage_change_unified',
                'parent_event_id': parent.id,
            },
        )
        db.session.commit()

        resp = admin_client.get('/brain/events?limit=50')
        assert resp.status_code == 200
        events = resp.get_json()['events']
        parent_row = next(e for e in events if e['id'] == parent.id)
        assert len(parent_row['linked_children']) == 1
        linked = parent_row['linked_children'][0]
        assert linked['id'] == child.id
        assert linked['action'] == 'update_fab_order'
        assert linked['from'] == 17.0
        assert linked['to'] == 2.0


# ---------------------------------------------------------------------------
# DWL (SubmittalEvents) undo
# ---------------------------------------------------------------------------

def test_dwl_undo_order_number_reverts(admin_client, app):
    with app.app_context():
        sub = _make_submittal(submittal_id='SUB-1', order_number=8.0)
        ev = _seed_submittal_event(
            submittal_id='SUB-1',
            payload={'order_number': {'old': 5.0, 'new': 8.0}},
        )
        db.session.commit()

        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 200, resp.get_json()

        db.session.expire_all()
        sub = Submittals.query.filter_by(submittal_id='SUB-1').first()
        assert sub.order_number == 5.0

        new_event_id = resp.get_json()['event_id']
        new_ev = db.session.get(SubmittalEvents, new_event_id)
        assert new_ev.action == 'updated'
        assert new_ev.source == 'Brain'
        assert new_ev.payload['order_number'] == {'old': 8.0, 'new': 5.0}
        assert new_ev.payload['undone_event_id'] == ev.id


def test_dwl_undo_notes_reverts(admin_client, app):
    with app.app_context():
        sub = _make_submittal(submittal_id='SUB-2', notes='New notes')
        ev = _seed_submittal_event(
            submittal_id='SUB-2',
            payload={'notes': {'old': 'Original', 'new': 'New notes'}},
        )
        db.session.commit()

        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 200, resp.get_json()

        db.session.expire_all()
        sub = Submittals.query.filter_by(submittal_id='SUB-2').first()
        assert sub.notes == 'Original'


def test_dwl_undo_drafting_status_reverts(admin_client, app):
    with app.app_context():
        sub = _make_submittal(submittal_id='SUB-3', submittal_drafting_status='STARTED')
        ev = _seed_submittal_event(
            submittal_id='SUB-3',
            payload={'submittal_drafting_status': {'old': '', 'new': 'STARTED'}},
        )
        db.session.commit()

        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 200, resp.get_json()

        db.session.expire_all()
        sub = Submittals.query.filter_by(submittal_id='SUB-3').first()
        assert sub.submittal_drafting_status == ''


def test_dwl_undo_stale_returns_409(admin_client, app):
    """Submittal was independently edited after the event — undo would
    overwrite that later change."""
    with app.app_context():
        # Live order_number = 12 (someone bumped it again after the original
        # 5 → 8 change). Trying to undo back to 5 would silently lose the 12.
        _make_submittal(submittal_id='SUB-4', order_number=12.0)
        ev = _seed_submittal_event(
            submittal_id='SUB-4',
            payload={'order_number': {'old': 5.0, 'new': 8.0}},
        )
        db.session.commit()

        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 409
        body = resp.get_json()
        assert body['error'] == 'stale'
        assert body['current'] == 12.0
        assert body['expected'] == 8.0


def test_dwl_undo_rejects_procore_status_event(admin_client, app):
    """The Procore-bound `status` field is intentionally NOT in the DWL
    whitelist — undo on those events returns 400. Defense against someone
    crafting a payload that targets the wrong column."""
    with app.app_context():
        _make_submittal(submittal_id='SUB-5', status='Closed')
        ev = _seed_submittal_event(
            submittal_id='SUB-5',
            payload={'status': {'old': 'Open', 'new': 'Closed'}},
        )
        db.session.commit()

        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 400
        assert 'undoable field' in resp.get_json()['error'].lower()


def test_dwl_undo_does_not_create_procore_outbox(admin_client, app):
    """The whole point of the feature: undo writes the DB column directly
    and emits a SubmittalEvents row — no ProcoreOutbox entry is created.
    Asserts no rows in the outbox after a successful undo."""
    with app.app_context():
        from app.models import ProcoreOutbox
        _make_submittal(submittal_id='SUB-6', notes='New')
        ev = _seed_submittal_event(
            submittal_id='SUB-6',
            payload={'notes': {'old': 'Old', 'new': 'New'}},
        )
        db.session.commit()
        outbox_before = ProcoreOutbox.query.count()

        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 200, resp.get_json()

        outbox_after = ProcoreOutbox.query.count()
        assert outbox_after == outbox_before, (
            "Undo must not enqueue a Procore outbox entry"
        )


def test_dwl_undo_event_is_not_undoable(admin_client, app):
    with app.app_context():
        _make_submittal(submittal_id='SUB-7', order_number=8.0)
        ev = _seed_submittal_event(
            submittal_id='SUB-7',
            payload={'order_number': {'old': 5.0, 'new': 8.0}},
        )
        db.session.commit()

        r1 = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert r1.status_code == 200
        undo_event_id = r1.get_json()['event_id']

        r2 = admin_client.post(f'/brain/submittal-events/{undo_event_id}/undo')
        assert r2.status_code == 400
        assert 'undoable' in r2.get_json()['error'].lower()


def test_dwl_undo_non_admin_forbidden(non_admin_client, app):
    with app.app_context():
        _make_submittal(submittal_id='SUB-8', order_number=8.0)
        ev = _seed_submittal_event(
            submittal_id='SUB-8',
            payload={'order_number': {'old': 5.0, 'new': 8.0}},
        )
        db.session.commit()

        resp = non_admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 403


def test_dwl_notes_route_records_persisted_value(admin_client, app):
    """Regression: the DWL notes route used to log the raw request value into
    the event payload while persisting the stripped value. That mismatch made
    the resulting event un-undoable (current_value !== payload.new) until you
    edited the submittal again. Lock in that the payload's `new` reflects what
    actually got stored."""
    with app.app_context():
        sub = _make_submittal(submittal_id='SUB-NOTES', notes='before',
                              ball_in_court='Drafter A')
        db.session.commit()
        sub_pk = sub.id

        resp = admin_client.put(
            '/brain/drafting-work-load/notes',
            json={'submittal_id': 'SUB-NOTES', 'notes': 'Test undo note   '},
        )
        assert resp.status_code == 200, resp.get_json()

        db.session.expire_all()
        sub = db.session.get(Submittals, sub_pk)
        # Service strips whitespace before persisting.
        assert sub.notes == 'Test undo note'

        # Event payload's `new` must match the persisted value, not the raw
        # request — otherwise the undo eligibility check fails the staleness
        # comparison.
        ev = (SubmittalEvents.query
              .filter_by(submittal_id='SUB-NOTES')
              .order_by(SubmittalEvents.id.desc())
              .first())
        assert ev is not None
        assert ev.payload['notes']['new'] == 'Test undo note'

        # End-to-end check: the event we just created should be undoable.
        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 200, resp.get_json()
        db.session.expire_all()
        assert db.session.get(Submittals, sub_pk).notes == 'before'


def test_dwl_undo_step_reverts_swap_partner(admin_client, app):
    """A DWL step operation emits ONE event with the neighbor's change embedded
    in `payload.swapped_with`. Undoing the parent event must also revert the
    neighbor's order_number — otherwise both submittals end up at the same
    order (the bug from the screenshot)."""
    with app.app_context():
        # State after a step "up" operation: 69261242 went 0.8 → 0.9, and the
        # neighbor 69363161 went 0.9 → 0.8 to swap with it.
        primary = _make_submittal(submittal_id='69261242', order_number=0.9,
                                  ball_in_court='Drafter A')
        partner = _make_submittal(submittal_id='69363161', order_number=0.8,
                                  ball_in_court='Drafter A')
        ev = _seed_submittal_event(
            submittal_id='69261242',
            payload={
                'order_number': {'old': 0.8, 'new': 0.9},
                'order_step': 'up',
                'swapped_with': {
                    'submittal_id': '69363161',
                    'order_number': {'old': 0.9, 'new': 0.8},
                },
            },
        )
        db.session.commit()

        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert len(body['linked_event_ids']) == 1

        db.session.expire_all()
        primary = Submittals.query.filter_by(submittal_id='69261242').first()
        partner = Submittals.query.filter_by(submittal_id='69363161').first()
        assert primary.order_number == 0.8
        assert partner.order_number == 0.9  # swapped back

        # The partner event links back to the primary undo event for audit trail.
        partner_event = db.session.get(SubmittalEvents, body['linked_event_ids'][0])
        assert partner_event.submittal_id == '69363161'
        assert partner_event.payload['order_number'] == {'old': 0.8, 'new': 0.9}
        assert partner_event.payload['undone_event_id'] == ev.id
        assert partner_event.payload['parent_event_id'] == body['event_id']


def test_dwl_undo_step_fails_when_partner_is_stale(admin_client, app):
    """If the neighbor's order_number was independently edited after the step,
    the bundle returns 409 — partial revert would leave both at the same order."""
    with app.app_context():
        _make_submittal(submittal_id='69261242', order_number=0.9,
                        ball_in_court='Drafter A')
        # Partner was independently set to 1.5 after the step.
        _make_submittal(submittal_id='69363161', order_number=1.5,
                        ball_in_court='Drafter A')
        ev = _seed_submittal_event(
            submittal_id='69261242',
            payload={
                'order_number': {'old': 0.8, 'new': 0.9},
                'order_step': 'up',
                'swapped_with': {
                    'submittal_id': '69363161',
                    'order_number': {'old': 0.9, 'new': 0.8},
                },
            },
        )
        db.session.commit()

        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 409
        body = resp.get_json()
        assert body['error'] == 'stale'
        assert body['partner_submittal_id'] == '69363161'

        # No partial revert.
        db.session.expire_all()
        assert Submittals.query.filter_by(submittal_id='69261242').first().order_number == 0.9
        assert Submittals.query.filter_by(submittal_id='69363161').first().order_number == 1.5


def test_dwl_undo_step_fails_when_partner_missing(admin_client, app):
    """If the swap partner submittal was deleted, fail loudly rather than
    silently leaving the order in a collision state."""
    with app.app_context():
        _make_submittal(submittal_id='69261242', order_number=0.9)
        # Note: no submittal with id '69363161'.
        ev = _seed_submittal_event(
            submittal_id='69261242',
            payload={
                'order_number': {'old': 0.8, 'new': 0.9},
                'order_step': 'up',
                'swapped_with': {
                    'submittal_id': '69363161',
                    'order_number': {'old': 0.9, 'new': 0.8},
                },
            },
        )
        db.session.commit()

        resp = admin_client.post(f'/brain/submittal-events/{ev.id}/undo')
        assert resp.status_code == 400
        assert 'swap partner' in resp.get_json()['error'].lower()


def test_events_feed_includes_current_value_for_dwl_events(admin_client, app):
    with app.app_context():
        _make_submittal(submittal_id='SUB-9', order_number=8.0, notes='hello',
                        submittal_drafting_status='HOLD')
        _seed_submittal_event(
            submittal_id='SUB-9',
            payload={'order_number': {'old': 5.0, 'new': 8.0}},
        )
        _seed_submittal_event(
            submittal_id='SUB-9',
            payload={'notes': {'old': None, 'new': 'hello'}},
        )
        _seed_submittal_event(
            submittal_id='SUB-9',
            payload={'submittal_drafting_status': {'old': '', 'new': 'HOLD'}},
        )
        # A Procore-status event — should NOT get a current_value (not whitelisted).
        _seed_submittal_event(
            submittal_id='SUB-9',
            payload={'status': {'old': 'Open', 'new': 'Closed'}},
        )
        db.session.commit()

        resp = admin_client.get('/brain/events?limit=50')
        assert resp.status_code == 200
        events = resp.get_json()['events']
        by_field = {}
        procore_status_event = None
        for e in events:
            if e['type'] != 'submittal':
                continue
            payload = e.get('payload') or {}
            for k in ('order_number', 'notes', 'submittal_drafting_status'):
                if k in payload:
                    by_field[k] = e
            if 'status' in payload:
                procore_status_event = e

        assert by_field['order_number']['current_value'] == 8.0
        assert by_field['notes']['current_value'] == 'hello'
        assert by_field['submittal_drafting_status']['current_value'] == 'HOLD'
        # Procore status — not undoable, no current_value populated.
        assert procore_status_event is not None
        assert procore_status_event['current_value'] is None
