"""Tests for /api/version endpoint and the global Cache-Control after_request hook."""
from app.version import BUILD_SHA


def test_api_version_returns_sha_and_timestamp(client):
    response = client.get("/api/version")
    assert response.status_code == 200
    body = response.get_json()
    assert body["version"] == BUILD_SHA
    assert isinstance(body["releasedAt"], str) and "T" in body["releasedAt"]


def test_api_version_has_no_store_cache_header(client):
    response = client.get("/api/version")
    assert response.headers.get("Cache-Control") == "no-store"


def test_html_shell_has_no_cache_header(client):
    response = client.get("/")
    assert response.headers.get("Cache-Control") == "no-cache"


def test_assets_have_immutable_cache_header(client):
    # The static-assets route 404s when frontend/dist/assets isn't built (the test
    # environment); the after_request hook still stamps headers on the 404 response,
    # so we can verify policy without a real build artifact.
    response = client.get("/assets/main-deadbeef.js")
    assert response.headers.get("Cache-Control") == (
        "public, max-age=31536000, immutable"
    )


def test_api_auth_endpoints_are_no_store(client):
    # Auth blueprint mounts under /api/auth; verify the /api/* rule covers it,
    # not just /api/version.
    response = client.get("/api/auth/me")
    assert response.headers.get("Cache-Control") == "no-store"
