"""Auth-patching test clients for T&M ticket blueprint tests.

app/brain/tm/routes.py imports get_current_user directly, so admin_required's
lookup goes through app.auth.utils while the route itself calls the name
bound in its own module. Both sites must be patched (see tests/brain/conftest.py
for the pattern this clones).
"""
from contextlib import ExitStack

import pytest
from unittest.mock import patch


_TM_PATCH_TARGETS = (
    'app.auth.utils.get_current_user',
    'app.brain.tm.routes.get_current_user',
    'app.brain.tm.subcontractors.routes.get_current_user',
)


@pytest.fixture(autouse=True)
def tm_storage_root(app, tmp_path):
    """Point TM_TICKET_STORAGE_ROOT at a tmp dir so uploads never write into the repo."""
    app.config["TM_TICKET_STORAGE_ROOT"] = str(tmp_path / "tm_tickets")
    yield


@pytest.fixture(autouse=True)
def mock_send_mail():
    """Every test in this directory gets outbound email mocked, no exceptions —
    subcontractor invite/resend routes call the real send_mail() otherwise,
    which would attempt a genuine Graph API call in CI."""
    with patch('app.brain.tm.subcontractors.command.send_mail') as mocked:
        yield mocked


def _authed_client(app, user):
    with ExitStack() as stack:
        for target in _TM_PATCH_TARGETS:
            stack.enter_context(patch(target, return_value=user))
        yield app.test_client()


@pytest.fixture
def admin_client(app, mock_admin_user):
    yield from _authed_client(app, mock_admin_user)


@pytest.fixture
def non_admin_client(app, mock_non_admin_user):
    yield from _authed_client(app, mock_non_admin_user)


_SUBCONTRACTOR_PATCH_TARGETS = (
    'app.subcontractor_auth.utils.get_current_subcontractor',
    'app.brain.tm.subcontractor_view.routes.get_current_subcontractor',
)


def subcontractor_authed_client(app, subcontractor):
    """Context manager yielding a test client authed as the given Subcontractor
    row. A plain function (not a fixture) since assignment-scoping tests need
    two DIFFERENT subcontractor identities in the same test — call it once per
    identity rather than trying to parametrize a fixture."""
    stack = ExitStack()
    for target in _SUBCONTRACTOR_PATCH_TARGETS:
        stack.enter_context(patch(target, return_value=subcontractor))
    return stack, app.test_client()
