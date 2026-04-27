"""Auth-patching test clients for brain blueprint tests.

Brain blueprints import get_current_user directly, so admin_required's
get_current_user lookup goes through app.auth.utils while routes call the
name bound in their own module. Both sites must be patched.
"""
from contextlib import ExitStack

import pytest
from unittest.mock import patch


_BRAIN_PATCH_TARGETS = (
    'app.auth.utils.get_current_user',
    'app.brain.job_log.routes.get_current_user',
    'app.brain.board.routes.get_current_user',
)


def _authed_client(app, user):
    with ExitStack() as stack:
        for target in _BRAIN_PATCH_TARGETS:
            stack.enter_context(patch(target, return_value=user))
        yield app.test_client()


@pytest.fixture
def admin_client(app, mock_admin_user):
    mock_admin_user.is_drafter = True
    yield from _authed_client(app, mock_admin_user)


@pytest.fixture
def non_admin_client(app, mock_non_admin_user):
    yield from _authed_client(app, mock_non_admin_user)
