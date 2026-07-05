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
)


@pytest.fixture(autouse=True)
def tm_storage_root(app, tmp_path):
    """Point TM_TICKET_STORAGE_ROOT at a tmp dir so uploads never write into the repo."""
    app.config["TM_TICKET_STORAGE_ROOT"] = str(tmp_path / "tm_tickets")
    yield


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
