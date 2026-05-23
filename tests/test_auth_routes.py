"""Tests for app/auth/routes.py — login, logout, /me, check-user, set-password."""
from app.models import User
from app.auth.utils import hash_password

from tests.conftest import make_user as _make_base_user


def _make_user(username, password="hunter2", *, password_set=True, **kwargs):
    return _make_base_user(
        username,
        password_hash=hash_password(password) if password_set else "",
        password_set=password_set,
        **kwargs,
    )


def test_login_success_returns_user_and_creates_session(app, client):
    with app.app_context():
        _make_user("alice@example.com", "correct-horse")

    resp = client.post(
        "/api/auth/login",
        json={"username": "alice@example.com", "password": "correct-horse"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    assert body["user"]["username"] == "alice@example.com"

    # Session is set — /me should now return the user
    me = client.get("/api/auth/me")
    assert me.status_code == 200


def test_login_username_is_case_insensitive(app, client):
    with app.app_context():
        _make_user("alice@example.com", "pw-1234567")

    resp = client.post(
        "/api/auth/login",
        json={"username": "ALICE@EXAMPLE.COM", "password": "pw-1234567"},
    )
    assert resp.status_code == 200


def test_login_wrong_password_returns_401(app, client):
    with app.app_context():
        _make_user("alice@example.com", "correct-horse")

    resp = client.post(
        "/api/auth/login",
        json={"username": "alice@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_unknown_user_returns_401(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "ghost@example.com", "password": "anything"},
    )
    assert resp.status_code == 401


def test_login_inactive_user_returns_403(app, client):
    with app.app_context():
        _make_user("alice@example.com", "pw-1234567", is_active=False)

    resp = client.post(
        "/api/auth/login",
        json={"username": "alice@example.com", "password": "pw-1234567"},
    )
    assert resp.status_code == 403


def test_login_missing_fields_returns_400(client):
    assert client.post("/api/auth/login", json={}).status_code == 400
    assert client.post("/api/auth/login", json={"username": "x"}).status_code == 400


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------

def test_logout_clears_session(app, client):
    with app.app_context():
        _make_user("alice@example.com", "pw-1234567")
    client.post(
        "/api/auth/login",
        json={"username": "alice@example.com", "password": "pw-1234567"},
    )

    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200

    me = client.get("/api/auth/me")
    assert me.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

def test_me_unauthenticated_returns_401(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_authenticated_returns_profile(app, client):
    with app.app_context():
        _make_user("alice@example.com", "pw-1234567", is_admin=True)
    client.post(
        "/api/auth/login",
        json={"username": "alice@example.com", "password": "pw-1234567"},
    )
    resp = client.get("/api/auth/me")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["username"] == "alice@example.com"
    assert body["is_admin"] is True


# ---------------------------------------------------------------------------
# POST /api/auth/check-user
# ---------------------------------------------------------------------------

def test_check_user_existing_password_already_set(app, client):
    with app.app_context():
        _make_user("alice@example.com", "pw-1234567", password_set=True)
    resp = client.post("/api/auth/check-user", json={"username": "alice@example.com"})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["exists"] is True
    assert body["needs_password_setup"] is False


def test_check_user_existing_needs_password(app, client):
    with app.app_context():
        _make_user("alice@example.com", password_set=False)
    resp = client.post("/api/auth/check-user", json={"username": "alice@example.com"})
    body = resp.get_json()
    assert body["exists"] is True
    assert body["needs_password_setup"] is True


def test_check_user_nonexistent(client):
    resp = client.post("/api/auth/check-user", json={"username": "ghost@example.com"})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["exists"] is False


def test_check_user_inactive_does_not_offer_setup(app, client):
    with app.app_context():
        _make_user("alice@example.com", is_active=False, password_set=False)
    resp = client.post("/api/auth/check-user", json={"username": "alice@example.com"})
    body = resp.get_json()
    assert body["exists"] is True
    assert body["needs_password_setup"] is False


# ---------------------------------------------------------------------------
# POST /api/auth/set-password
# ---------------------------------------------------------------------------

def test_set_password_first_login_succeeds(app, client):
    with app.app_context():
        _make_user("alice@example.com", password_set=False)

    resp = client.post(
        "/api/auth/set-password",
        json={
            "username": "alice@example.com",
            "new_password": "secure-pw-1",
            "confirm_password": "secure-pw-1",
        },
    )
    assert resp.status_code == 200
    # Session is created, /me works
    assert client.get("/api/auth/me").status_code == 200

    # password_set is now True — second call must fail
    with app.app_context():
        u = User.query.filter_by(username="alice@example.com").first()
        assert u.password_set is True


def test_set_password_already_set_returns_400(app, client):
    with app.app_context():
        _make_user("alice@example.com", "old-pw-1234567", password_set=True)

    resp = client.post(
        "/api/auth/set-password",
        json={
            "username": "alice@example.com",
            "new_password": "new-pw-1234",
            "confirm_password": "new-pw-1234",
        },
    )
    assert resp.status_code == 400


def test_set_password_too_short_returns_400(app, client):
    with app.app_context():
        _make_user("alice@example.com", password_set=False)

    resp = client.post(
        "/api/auth/set-password",
        json={
            "username": "alice@example.com",
            "new_password": "short",
            "confirm_password": "short",
        },
    )
    assert resp.status_code == 400


def test_set_password_mismatch_returns_400(app, client):
    with app.app_context():
        _make_user("alice@example.com", password_set=False)

    resp = client.post(
        "/api/auth/set-password",
        json={
            "username": "alice@example.com",
            "new_password": "matching-pw-1",
            "confirm_password": "different-pw-2",
        },
    )
    assert resp.status_code == 400


def test_set_password_unknown_user_returns_404(client):
    resp = client.post(
        "/api/auth/set-password",
        json={
            "username": "ghost@example.com",
            "new_password": "secure-pw-1",
            "confirm_password": "secure-pw-1",
        },
    )
    assert resp.status_code == 404
