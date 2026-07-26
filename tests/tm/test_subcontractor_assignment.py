"""Tests for admin subcontractor roster management (invite/resend/deactivate)
and T&M ticket assignment, plus the assignment-scoping security guarantees
from the subcontractor-facing side (a subcontractor never sees another
subcontractor's ticket).

send_mail is mocked app-wide for this directory (tests/tm/conftest.py) so
these never attempt a real Graph call.
"""
from app.models import Subcontractor, TMTicket, TMTicketSubcontractor, db
from tests.conftest import make_subcontractor
from tests.tm.conftest import subcontractor_authed_client


def _create_ticket(status="draft"):
    ticket = TMTicket(status=status, created_by="test_admin")
    db.session.add(ticket)
    db.session.commit()
    return ticket


# ---------------------------------------------------------------------------
# Admin: invite / roster CRUD
# ---------------------------------------------------------------------------


def test_invite_creates_pending_subcontractor_and_sends_mail(app, admin_client):
    resp = admin_client.post('/brain/subcontractors', json={
        'company_name': 'Acme Electrical', 'contact_name': 'Sam Sub', 'email': 'sam@acme.test',
    })
    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body['company_name'] == 'Acme Electrical'
    assert body['email'] == 'sam@acme.test'
    assert body['invite_accepted'] is False

    row = Subcontractor.query.filter_by(email='sam@acme.test').first()
    assert row is not None
    assert row.invite_token_hash is not None
    assert row.invite_token_expires_at is not None
    assert row.password_hash is None


def test_invite_lowercases_email(app, admin_client):
    resp = admin_client.post('/brain/subcontractors', json={
        'company_name': 'Acme', 'contact_name': 'Sam', 'email': 'SAM@ACME.TEST',
    })
    assert resp.status_code == 201
    assert resp.get_json()['email'] == 'sam@acme.test'


def test_invite_duplicate_email_returns_409(app, admin_client):
    make_subcontractor('sam@acme.test')
    resp = admin_client.post('/brain/subcontractors', json={
        'company_name': 'Acme', 'contact_name': 'Sam', 'email': 'sam@acme.test',
    })
    assert resp.status_code == 409


def test_invite_missing_fields_returns_400(app, admin_client):
    resp = admin_client.post('/brain/subcontractors', json={'company_name': 'Acme'})
    assert resp.status_code == 400


def test_invite_bad_email_returns_400(app, admin_client):
    resp = admin_client.post('/brain/subcontractors', json={
        'company_name': 'Acme', 'contact_name': 'Sam', 'email': 'not-an-email',
    })
    assert resp.status_code == 400


def test_list_and_get_roster(app, admin_client):
    sub = make_subcontractor('sam@acme.test')
    resp = admin_client.get('/brain/subcontractors')
    assert resp.status_code == 200
    assert any(s['id'] == sub.id for s in resp.get_json()['subcontractors'])

    resp = admin_client.get(f'/brain/subcontractors/{sub.id}')
    assert resp.status_code == 200
    assert resp.get_json()['email'] == 'sam@acme.test'


def test_resend_invite_regenerates_token(app, admin_client):
    sub = make_subcontractor('sam@acme.test')
    old_hash = sub.invite_token_hash

    resp = admin_client.post(f'/brain/subcontractors/{sub.id}/resend-invite')
    assert resp.status_code == 200
    db.session.refresh(sub)
    assert sub.invite_token_hash != old_hash


def test_resend_invite_after_acceptance_returns_400(app, admin_client):
    sub = make_subcontractor('sam@acme.test', accepted=True)
    resp = admin_client.post(f'/brain/subcontractors/{sub.id}/resend-invite')
    assert resp.status_code == 400


def test_deactivate_and_reactivate(app, admin_client):
    sub = make_subcontractor('sam@acme.test')
    resp = admin_client.post(f'/brain/subcontractors/{sub.id}/deactivate')
    assert resp.status_code == 200
    assert resp.get_json()['is_active'] is False

    resp = admin_client.post(f'/brain/subcontractors/{sub.id}/reactivate')
    assert resp.status_code == 200
    assert resp.get_json()['is_active'] is True


def test_non_admin_forbidden_on_roster_routes(app, non_admin_client):
    sub = make_subcontractor('sam@acme.test')
    assert non_admin_client.post('/brain/subcontractors', json={}).status_code == 403
    assert non_admin_client.get('/brain/subcontractors').status_code == 403
    assert non_admin_client.post(f'/brain/subcontractors/{sub.id}/deactivate').status_code == 403


# ---------------------------------------------------------------------------
# Admin: assignment
# ---------------------------------------------------------------------------


def test_assign_and_list_ticket_subcontractors(app, admin_client):
    ticket = _create_ticket()
    sub = make_subcontractor('sam@acme.test', accepted=True)

    resp = admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors',
                              json={'subcontractor_id': sub.id})
    assert resp.status_code == 201
    assert resp.get_json()['subcontractor_id'] == sub.id

    resp = admin_client.get(f'/brain/tm-tickets/{ticket.id}/subcontractors')
    assert resp.status_code == 200
    assert [a['subcontractor_id'] for a in resp.get_json()['subcontractors']] == [sub.id]


def test_assign_is_idempotent(app, admin_client):
    ticket = _create_ticket()
    sub = make_subcontractor('sam@acme.test', accepted=True)
    admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})
    admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})
    assert TMTicketSubcontractor.query.filter_by(tm_ticket_id=ticket.id, subcontractor_id=sub.id).count() == 1


def test_assign_sends_separate_sub_and_admin_emails(app, admin_client, mock_send_mail):
    ticket = _create_ticket()
    sub = make_subcontractor('sam@acme.test', accepted=True)

    resp = admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})
    assert resp.status_code == 201

    assert mock_send_mail.call_count == 2
    calls_by_to = {c.kwargs['to_address']: c.kwargs for c in mock_send_mail.call_args_list}

    sub_kwargs = calls_by_to['sam@acme.test']
    assert sub_kwargs.get('cc_address') is None
    assert f'/sub/tickets/{ticket.id}' in sub_kwargs['html_content']
    assert str(ticket.id) in sub_kwargs['subject']

    admin_kwargs = calls_by_to['test_admin']
    assert admin_kwargs.get('cc_address') is None
    assert str(ticket.id) in admin_kwargs['subject']
    assert 'Sam Sub' in admin_kwargs['html_content']


def test_reassign_idempotent_does_not_resend_notification(app, admin_client, mock_send_mail):
    ticket = _create_ticket()
    sub = make_subcontractor('sam@acme.test', accepted=True)
    admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})
    mock_send_mail.reset_mock()

    resp = admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})
    assert resp.status_code == 201
    mock_send_mail.assert_not_called()


def test_assign_notification_failure_does_not_fail_the_assignment(app, admin_client, mock_send_mail):
    ticket = _create_ticket()
    sub = make_subcontractor('sam@acme.test', accepted=True)
    mock_send_mail.side_effect = RuntimeError("graph down")

    resp = admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})
    assert resp.status_code == 201
    assert TMTicketSubcontractor.query.filter_by(tm_ticket_id=ticket.id, subcontractor_id=sub.id).count() == 1


def test_assign_inactive_subcontractor_returns_400(app, admin_client):
    ticket = _create_ticket()
    sub = make_subcontractor('sam@acme.test', accepted=True, is_active=False)
    resp = admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})
    assert resp.status_code == 400


def test_assign_missing_ticket_returns_404(app, admin_client):
    sub = make_subcontractor('sam@acme.test', accepted=True)
    resp = admin_client.post('/brain/tm-tickets/999999/subcontractors', json={'subcontractor_id': sub.id})
    assert resp.status_code == 404


def test_unassign_removes_row(app, admin_client):
    ticket = _create_ticket()
    sub = make_subcontractor('sam@acme.test', accepted=True)
    admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})

    resp = admin_client.delete(f'/brain/tm-tickets/{ticket.id}/subcontractors/{sub.id}')
    assert resp.status_code == 200
    assert TMTicketSubcontractor.query.filter_by(tm_ticket_id=ticket.id, subcontractor_id=sub.id).count() == 0


def test_unassign_missing_returns_404(app, admin_client):
    ticket = _create_ticket()
    sub = make_subcontractor('sam@acme.test', accepted=True)
    resp = admin_client.delete(f'/brain/tm-tickets/{ticket.id}/subcontractors/{sub.id}')
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Assignment scoping (subcontractor-facing) — the security-load-bearing tests
# ---------------------------------------------------------------------------


def test_subcontractor_list_only_shows_own_assigned_tickets(app, admin_client):
    ticket_a = _create_ticket()
    ticket_b = _create_ticket()
    sub_a = make_subcontractor('a@acme.test', accepted=True)
    sub_b = make_subcontractor('b@acme.test', accepted=True)
    admin_client.post(f'/brain/tm-tickets/{ticket_a.id}/subcontractors', json={'subcontractor_id': sub_a.id})
    admin_client.post(f'/brain/tm-tickets/{ticket_b.id}/subcontractors', json={'subcontractor_id': sub_b.id})

    stack, client = subcontractor_authed_client(app, sub_a)
    with stack:
        resp = client.get('/brain/subcontractor/tm-tickets')
        assert resp.status_code == 200
        ids = [t['id'] for t in resp.get_json()['tickets']]
        assert ids == [ticket_a.id]
        assert ticket_b.id not in ids


def test_subcontractor_cannot_get_unassigned_ticket_404_not_403(app, admin_client):
    ticket = _create_ticket()
    sub = make_subcontractor('a@acme.test', accepted=True)
    # Deliberately never assigned.

    stack, client = subcontractor_authed_client(app, sub)
    with stack:
        resp = client.get(f'/brain/subcontractor/tm-tickets/{ticket.id}')
        assert resp.status_code == 404


def test_unassign_revokes_visibility(app, admin_client):
    ticket = _create_ticket()
    sub = make_subcontractor('a@acme.test', accepted=True)
    admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})

    stack, client = subcontractor_authed_client(app, sub)
    with stack:
        assert client.get(f'/brain/subcontractor/tm-tickets/{ticket.id}').status_code == 200

    admin_client.delete(f'/brain/tm-tickets/{ticket.id}/subcontractors/{sub.id}')

    stack, client = subcontractor_authed_client(app, sub)
    with stack:
        assert client.get(f'/brain/subcontractor/tm-tickets/{ticket.id}').status_code == 404


def test_subcontractor_can_edit_and_submit_assigned_draft(app, admin_client):
    ticket = _create_ticket()
    sub = make_subcontractor('a@acme.test', accepted=True)
    admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})

    stack, client = subcontractor_authed_client(app, sub)
    with stack:
        resp = client.put(f'/brain/subcontractor/tm-tickets/{ticket.id}', json={
            'work_description': 'Ran conduit on level 3',
            'labor': [{'name': 'Sam Sub', 'hours_reg': 8}],
        })
        assert resp.status_code == 200
        assert resp.get_json()['ticket']['work_description'] == 'Ran conduit on level 3'

        resp = client.post(f'/brain/subcontractor/tm-tickets/{ticket.id}/submit')
        assert resp.status_code == 200
        assert resp.get_json()['ticket']['status'] == 'submitted'

    db.session.refresh(ticket)
    assert ticket.status == 'submitted'
    assert ticket.reviewed_by == f'subcontractor:{sub.id}:{sub.email}'


def test_subcontractor_cannot_edit_submitted_ticket(app, admin_client):
    ticket = _create_ticket(status="submitted")
    sub = make_subcontractor('a@acme.test', accepted=True)
    admin_client.post(f'/brain/tm-tickets/{ticket.id}/subcontractors', json={'subcontractor_id': sub.id})

    stack, client = subcontractor_authed_client(app, sub)
    with stack:
        resp = client.put(f'/brain/subcontractor/tm-tickets/{ticket.id}', json={'work_description': 'x'})
        assert resp.status_code == 400

        resp = client.post(f'/brain/subcontractor/tm-tickets/{ticket.id}/submit')
        assert resp.status_code == 400
