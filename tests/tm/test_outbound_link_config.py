"""BUG-10: an unset APP_BASE_URL must never reach a recipient's inbox.

The invite link is built as `{APP_BASE_URL}/sub/accept-invite/{token}` and
APP_BASE_URL falls back to the local Vite dev server. On a deployed
environment that fallback produced a real email carrying a localhost link,
with no error anywhere — the only symptom was the client reporting "the link
doesn't work". These tests pin the two halves of the fix: the fallback is
still fine locally, and it is fatal (before any state is written) once the
environment is anything else.
"""
from unittest.mock import patch

import pytest

from app.brain.tm.subcontractors import command
from app.config import LOCAL_APP_BASE_URL
from app.models import Subcontractor, TMTicket, db
from tests.conftest import make_subcontractor


@pytest.fixture
def deployed_env():
    """Run the body as if we were on Render, with APP_BASE_URL unset."""
    with patch.dict('os.environ', {'ENVIRONMENT': 'production'}, clear=False), \
            patch.object(command.cfg, 'APP_BASE_URL', LOCAL_APP_BASE_URL):
        yield


@pytest.fixture
def local_env():
    with patch.dict('os.environ', {'ENVIRONMENT': 'local'}, clear=False), \
            patch.object(command.cfg, 'APP_BASE_URL', LOCAL_APP_BASE_URL):
        yield


def _invite(email='newsub@acme.test'):
    return command.InviteSubcontractorCommand(
        company_name='Acme Electrical',
        contact_name='Sam Sub',
        email=email,
        invited_by_user_id=None,
        invited_by_email='admin@mhmw.test',
        invited_by_name='Admin',
    )


def test_localhost_base_is_allowed_locally(app, local_env, mock_send_mail):
    sub = _invite().execute()

    assert sub.id is not None
    html = mock_send_mail.call_args_list[0].kwargs['html_content']
    assert f'{LOCAL_APP_BASE_URL}/sub/accept-invite/' in html


def test_invite_refuses_localhost_link_when_deployed(app, deployed_env, mock_send_mail):
    with pytest.raises(command.OutboundLinkNotConfiguredError):
        _invite().execute()

    mock_send_mail.assert_not_called()
    # Refused before the row was written, so there is no dead subcontractor to clean up.
    assert Subcontractor.query.filter_by(email='newsub@acme.test').first() is None


def test_resend_refuses_before_rotating_the_token(app, deployed_env, mock_send_mail):
    sub = make_subcontractor('sam@acme.test')
    command._generate_and_store_invite_token(sub)
    db.session.commit()
    original_hash = sub.invite_token_hash

    with pytest.raises(command.OutboundLinkNotConfiguredError):
        command.resend_invite(sub, resent_by_email='admin@mhmw.test', resent_by_name='Admin')

    mock_send_mail.assert_not_called()
    db.session.refresh(sub)
    assert sub.invite_token_hash == original_hash  # still the working token


def test_ticket_assignment_link_is_covered_by_the_same_guard(app, deployed_env):
    # Same variable, second link — broken identically, just never hit yet.
    ticket = TMTicket(job='500-998', location='Bay 3')
    db.session.add(ticket)
    sub = make_subcontractor('sam@acme.test', accepted=True)
    db.session.commit()

    with pytest.raises(command.OutboundLinkNotConfiguredError):
        command._assignment_email_html(ticket, sub, 'Admin')


def test_a_real_domain_passes_and_does_not_double_slash(app):
    with patch.dict('os.environ', {'ENVIRONMENT': 'production'}, clear=False), \
            patch.object(command.cfg, 'APP_BASE_URL', 'https://brain.mhmw.test/'):
        assert command._external_link('/sub/tickets/7') == 'https://brain.mhmw.test/sub/tickets/7'
