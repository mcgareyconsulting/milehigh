"""HTTP tests for the admin-only on-demand mail pull endpoint.

admin_required resolves the user via app.auth.utils.get_current_user, so that's
the single patch target. m365_mail.pull is mocked so no Graph call happens.
"""
from unittest.mock import patch

from app.lake.ingest import m365_mail


def _enable(app):
    app.config["BB_MAIL_INGEST_ENABLED"] = True


def test_pull_endpoint_requires_auth(app, client):
    _enable(app)
    with patch("app.auth.utils.get_current_user", return_value=None):
        resp = client.post("/lake/ingest/mail/pull", json={})
    assert resp.status_code == 401


def test_pull_endpoint_requires_admin(app, client, mock_non_admin_user):
    _enable(app)
    with patch("app.auth.utils.get_current_user", return_value=mock_non_admin_user):
        resp = client.post("/lake/ingest/mail/pull", json={})
    assert resp.status_code == 403


def test_pull_endpoint_admin_ok(app, client, mock_admin_user):
    _enable(app)
    fake = {
        "mailbox": "bb@mhmw.com", "fetched": 1, "created": 1, "updated": 0,
        "unchanged": 0, "landed_ids": ["A"], "max_occurred_at": None,
    }
    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user), \
         patch.object(m365_mail, "pull", return_value=fake) as p:
        resp = client.post("/lake/ingest/mail/pull", json={"query": "RFI 042"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok" and data["created"] == 1
    assert "max_occurred_at" not in data  # stripped (datetime, internal-only)
    assert p.call_args.kwargs.get("query") == "RFI 042"


def test_pull_endpoint_disabled_returns_503(app, client, mock_admin_user):
    app.config["BB_MAIL_INGEST_ENABLED"] = False
    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user):
        resp = client.post("/lake/ingest/mail/pull", json={})
    assert resp.status_code == 503
