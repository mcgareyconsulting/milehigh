"""Fixtures for BB chat tests.

Uses real User rows (so the conversation FK and the is_carmen_chat gate behave like prod) and
patches get_current_user at both sites the routes touch — app.auth.utils (the decorator) and
app.brain.carmen_chat.routes (the route body), mirroring tests/brain/conftest.py.
"""
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from tests.conftest import make_user


_PATCH_TARGETS = (
    "app.auth.utils.get_current_user",
    "app.brain.carmen_chat.routes.get_current_user",
)


def _mk(username, *, is_admin=False, is_carmen_chat=False):
    from app.models import db
    u = make_user(username, is_admin=is_admin)
    u.is_carmen_chat = is_carmen_chat
    db.session.commit()
    return u


@pytest.fixture
def bb_user(app):
    """A non-admin user granted BB-chat access. (The `app` fixture keeps an app context active.)"""
    return _mk("pilot@mhmw.com", is_carmen_chat=True)


@pytest.fixture
def no_access_user(app):
    """A non-admin user WITHOUT BB-chat access."""
    return _mk("nobody@mhmw.com", is_carmen_chat=False)


@pytest.fixture
def bb_admin_user(app):
    return _mk("admin@mhmw.com", is_admin=True)


def _authed_client(app, user):
    with ExitStack() as stack:
        for target in _PATCH_TARGETS:
            stack.enter_context(patch(target, return_value=user))
        yield app.test_client()


@pytest.fixture
def bb_client(app, bb_user):
    yield from _authed_client(app, bb_user)


@pytest.fixture
def no_access_client(app, no_access_user):
    yield from _authed_client(app, no_access_user)


@pytest.fixture
def bb_admin_client(app, bb_admin_user):
    yield from _authed_client(app, bb_admin_user)
