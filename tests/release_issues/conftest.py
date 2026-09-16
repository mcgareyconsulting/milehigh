"""Fixtures for the Release Issue Register suite (roadmap T11).

Real User and Releases rows (mentions resolve against User.first_name), in-memory
DB from the shared `app` fixture, attachments written to a tmp storage root.
"""
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from tests.conftest import make_release, make_user


@pytest.fixture
def storage_root(app, tmp_path):
    app.config['RELEASE_ISSUE_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


@pytest.fixture
def release(app):
    from app.models import db
    r = make_release(job=290, release='153', job_name='Issue Test Job')
    db.session.commit()
    return r


@pytest.fixture
def other_release(app):
    from app.models import db
    r = make_release(job=410, release='108', job_name='Other Job')
    db.session.commit()
    return r


@pytest.fixture
def admin(app):
    return make_user('issueadmin', is_admin=True, first_name='Ada', last_name='Admin')


@pytest.fixture
def dave(app):
    return make_user('dave', first_name='Dave', last_name='Cruz')


@pytest.fixture
def plain_user(app):
    return make_user('plainuser', first_name='Pat', last_name='Plain')


def valid_issue_payload(**overrides):
    payload = {
        'title': 'Bent stair stringer',
        'description': 'Stringer arrived bent at the jobsite.',
        'department': 'fab',
        'category': 'damage',
        'priority': 'high',
        'estimated_cost': '1200',
    }
    payload.update(overrides)
    return payload


def _client_as(app, user):
    with ExitStack() as stack:
        for target in (
            'app.auth.utils.get_current_user',
            'app.brain.release_issues.routes.get_current_user',
        ):
            stack.enter_context(patch(target, return_value=user))
        yield app.test_client()


@pytest.fixture
def admin_client(app, admin):
    yield from _client_as(app, admin)


@pytest.fixture
def plain_client(app, plain_user):
    yield from _client_as(app, plain_user)


@pytest.fixture
def anon_client(app):
    yield from _client_as(app, None)
