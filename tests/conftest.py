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
import socket

# Must run before any test module imports create_app
os.environ.setdefault("TESTING", "1")

# Neutralize behavior flags a local .env may set (dotenv does not override
# existing env vars, so these hard sets win). Tests assume the defaults;
# without this, suites pass in CI (no .env) but fail on dev machines —
# e.g. TRELLO_MOCK=1 short-circuits the outbox move_card path.
os.environ["TRELLO_MOCK"] = "0"
os.environ["RECALL_CALENDAR_ENABLED"] = "0"

from unittest.mock import Mock, patch

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_outbound_network(request):
    """Fail fast on any real network connection from a test.

    External services (Trello, Procore, Graph, Anthropic) must always be
    mocked (tests/README.md); the DB is in-memory SQLite, so no test has a
    legitimate reason to open a TCP socket. Before this guard, a locally
    loaded .env let some tests silently hit live APIs (real Anthropic calls
    from the material-orders ingest path, real outbox deliveries).

    `pytest -m live` runs stand down: live-marked tests exist to make a real
    LLM call on purpose (see pytest.ini), and the default addopts exclude
    them from every normal run.
    """
    markexpr = request.config.getoption("-m", default="") or ""
    if "live" in markexpr and "not live" not in markexpr:
        yield
        return

    real_connect = socket.socket.connect

    def blocked_connect(self, address, *args, **kwargs):
        if self.family == getattr(socket, "AF_UNIX", None):
            return real_connect(self, address, *args, **kwargs)
        raise RuntimeError(
            f"Test attempted outbound network connection to {address!r}. "
            "Mock the external call (see tests/README.md)."
        )

    socket.socket.connect = blocked_connect
    try:
        yield
    finally:
        socket.socket.connect = real_connect


@pytest.fixture(autouse=True)
def _no_retry_backoff(monkeypatch):
    """Zero out Graph-client retry backoff so exhaust-retries tests don't
    sleep for real (1+2+4s per exercise). Patches the module-local delay
    helper, not time.sleep, so tests that rely on real timing (sync lock
    threads) are unaffected."""
    monkeypatch.setattr(
        "app.microsoft.graph_app_client._retry_delay_seconds",
        lambda resp, attempt: 0,
    )


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


@pytest.fixture
def admin_session(mock_admin_user):
    """Patch get_current_user at the shared auth.utils site to an admin.

    The single patch target used by non-HTTP command/service tests. Files that
    want every test authenticated as admin add a tiny autouse wrapper:

        @pytest.fixture(autouse=True)
        def setup_auth(admin_session):
            yield

    Brain HTTP-route tests that also import get_current_user at a blueprint
    site keep their own multi-target patch (see tests/brain/conftest.py).
    """
    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user):
        yield mock_admin_user


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


def make_release(job, release, stage="Cut Start", stage_group="FABRICATION",
                 fab_order=10, job_name="Test Job", **extra):
    """Single source of truth for constructing a Releases row in tests.

    stage/stage_group/fab_order are positional-or-keyword so the ordering and
    fab-order suites can call make_release(job, release, stage, group, fab_order)
    positionally; everything else (trello_card_id, start_install_*, etc.) flows
    through **extra. Flushes (not commits) so the row is queryable in-request.
    """
    from app.models import Releases, db
    r = Releases(
        job=job, release=release, job_name=job_name,
        stage=stage, stage_group=stage_group, fab_order=fab_order,
        **extra,
    )
    db.session.add(r)
    db.session.flush()
    return r


def make_subcontractor(email, *, company_name="Acme Electrical", contact_name="Sam Sub",
                        is_active=True, invited_by_user_id=None, accepted=False,
                        password_hash="x", **extra):
    """Single source of truth for constructing a Subcontractor row in tests.
    accepted=True sets invite_accepted_at (and a password_hash) so the row
    behaves like a subcontractor who's already logged in once; leave False
    for token/invite-flow tests where acceptance is the thing under test.
    """
    from datetime import datetime
    from app.models import Subcontractor, db
    sub = Subcontractor(
        email=email.lower(),
        company_name=company_name,
        contact_name=contact_name,
        is_active=is_active,
        invited_by_user_id=invited_by_user_id,
        invited_at=datetime.utcnow(),
        password_hash=password_hash if accepted else None,
        invite_accepted_at=datetime.utcnow() if accepted else None,
        **extra,
    )
    db.session.add(sub)
    db.session.commit()
    return sub
