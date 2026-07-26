"""HTTP route test for the Job Log material-order status summary endpoint."""
from datetime import date, timedelta
from unittest.mock import patch

from app.models import MaterialOrder, Releases, db


def test_summary_requires_auth(client):
    resp = client.get("/brain/material-orders/summary")
    assert resp.status_code == 401


def test_summary_returns_rollup_for_releases_with_orders(app, client, mock_admin_user):
    with app.app_context():
        yesterday = date.today() - timedelta(days=1)
        db.session.add(Releases(job=700, release="1", job_name="Job 700",
                                start_install=yesterday, start_install_formulaTF=False))
        db.session.add(MaterialOrder(job=700, release="1", status="ordered",
                                     supplier="Drexel Supply", line_index=0))
        # A release with everything received rolls up to green.
        db.session.add(Releases(job=701, release="1", job_name="Job 701"))
        db.session.add(MaterialOrder(job=701, release="1", status="received",
                                     supplier="Dencol", line_index=0))
        db.session.commit()

    with patch("app.auth.utils.get_current_user", return_value=mock_admin_user):
        resp = client.get("/brain/material-orders/summary")

    assert resp.status_code == 200
    summary = {(r["job"], r["release"]): r["status"] for r in resp.get_json()["summary"]}
    assert summary == {(700, "1"): "overdue", (701, "1"): "received"}
