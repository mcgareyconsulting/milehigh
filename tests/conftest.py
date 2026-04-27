"""
Pytest configuration for the test suite.

Ensures TESTING=1 is set before any test runs so create_app() and db_config
always use in-memory SQLite and never connect to sandbox or production.
This prevents tests (e.g. db.drop_all()) from touching real databases.

Shared fixtures here are used across all suites. Subdirectory conftests add
domain-specific fixtures (e.g. tests/dwl/conftest.py for DWL-only fixtures,
tests/brain/conftest.py for brain auth-patching clients).
"""
import os

# Must run before any test module imports create_app
os.environ.setdefault("TESTING", "1")

from unittest.mock import Mock

import pytest


@pytest.fixture
def app():
    """Flask app with in-memory SQLite. Schema is created and dropped per test."""
    from app import create_app
    from app.models import db

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret-key"

    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    assert "sandbox" not in uri.lower() and "render.com" not in uri, (
        "Tests must not use sandbox/production DB. "
        "Set TESTING=1 before create_app (see tests/conftest.py)."
    )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mock_admin_user():
    user = Mock()
    user.id = 1
    user.username = "test_admin"
    user.first_name = "Admin"
    user.last_name = "User"
    user.is_admin = True
    user.is_active = True
    user.is_drafter = False
    return user


@pytest.fixture
def mock_non_admin_user():
    user = Mock()
    user.id = 2
    user.username = "normal_user"
    user.first_name = "Normal"
    user.last_name = "User"
    user.is_admin = False
    user.is_active = True
    user.is_drafter = False
    return user


# ---------------------------------------------------------------------------
# DB row factories
#
# Tests that need real User or Releases rows can use these. They commit so
# the row is queryable from request handlers; callers that do not want to
# commit should add rows directly with db.session.add(...).
# ---------------------------------------------------------------------------


def make_user(username, *, password_hash="x", password_set=True,
              is_active=True, is_admin=False, is_drafter=False,
              first_name=None, last_name=None):
    from app.models import User, db
    user = User(
        username=username.lower(),
        password_hash=password_hash,
        password_set=password_set,
        is_active=is_active,
        is_admin=is_admin,
        is_drafter=is_drafter,
        first_name=first_name,
        last_name=last_name,
    )
    db.session.add(user)
    db.session.commit()
    return user


def make_release(job, release, *, stage="Cut start", stage_group="FABRICATION",
                 fab_order=10, job_name="Test Job", **extra):
    from app.models import Releases, db
    r = Releases(
        job=job, release=release, job_name=job_name,
        stage=stage, stage_group=stage_group, fab_order=fab_order,
        **extra,
    )
    db.session.add(r)
    db.session.flush()
    return r
