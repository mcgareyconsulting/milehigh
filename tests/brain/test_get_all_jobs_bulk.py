"""Tests for /brain/get-all-jobs bulk paging + comp_eta_effective, and the
row-shape parity contract between /get-all-jobs and the /jobs cursor endpoint.

These lock in the shared-releases-layer guarantees:
  - per_page is honored, capped at 2000, and defaults to 100
  - comp_eta_effective follows the comp_eta -> calculator -> start_install chain
  - both serializers emit the exact same key set (a cursor row missing
    comp_eta_effective would silently blank Gantt bars after the Map merge)
"""
from datetime import date

import pytest

from app.models import Releases, db
from app.brain.job_log.scheduling.calculator import calculate_install_complete_date
from tests.conftest import make_release


@pytest.fixture(autouse=True)
def setup_auth(admin_session):
    yield


def _seed(n, **common):
    for i in range(1, n + 1):
        make_release(
            job=i,
            release="A",
            job_name=f"Job {i}",
            stage="Cut Start",
            stage_group="FABRICATION",
            fab_order=float(i),
            **common,
        )
    db.session.commit()


class TestPerPage:
    def test_defaults_to_100(self, app, admin_client):
        with app.app_context():
            _seed(150)
            resp = admin_client.get("/brain/get-all-jobs")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["pagination"]["limit"] == 100
            assert body["pagination"]["returned_count"] == 100
            assert body["pagination"]["total_count"] == 150
            assert body["pagination"]["has_more"] is True

    def test_per_page_honored(self, app, admin_client):
        with app.app_context():
            _seed(150)
            resp = admin_client.get("/brain/get-all-jobs?per_page=200")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["pagination"]["limit"] == 200
            assert body["pagination"]["returned_count"] == 150
            assert body["pagination"]["has_more"] is False

    def test_per_page_capped_at_2000(self, app, admin_client):
        with app.app_context():
            _seed(5)
            resp = admin_client.get("/brain/get-all-jobs?per_page=999999")
            assert resp.status_code == 200
            assert resp.get_json()["pagination"]["limit"] == 2000

    def test_per_page_floored_at_1(self, app, admin_client):
        with app.app_context():
            _seed(5)
            resp = admin_client.get("/brain/get-all-jobs?per_page=0")
            assert resp.status_code == 200
            assert resp.get_json()["pagination"]["limit"] == 1


class TestCompEtaEffective:
    def test_uses_comp_eta_when_set(self, app, admin_client):
        with app.app_context():
            make_release(
                10, "A", job_name="J", stage="Cut Start", stage_group="FABRICATION",
                start_install=date(2026, 1, 5), install_hrs=40, num_guys=2,
                comp_eta=date(2026, 2, 2),
            )
            db.session.commit()
            row = _row_for(admin_client, "/brain/get-all-jobs", 10)
            assert row["comp_eta_effective"] == "2026-02-02"

    def test_falls_back_to_calculator_when_comp_eta_null(self, app, admin_client):
        with app.app_context():
            start = date(2026, 1, 5)
            make_release(
                11, "A", job_name="J", stage="Cut Start", stage_group="FABRICATION",
                start_install=start, install_hrs=40, num_guys=2, comp_eta=None,
            )
            db.session.commit()
            expected = calculate_install_complete_date(start, 40, 2)
            row = _row_for(admin_client, "/brain/get-all-jobs", 11)
            assert row["comp_eta_effective"] == expected.isoformat()

    def test_install_hrs_none_falls_back_to_start_install(self, app, admin_client):
        with app.app_context():
            start = date(2026, 1, 5)
            make_release(
                12, "A", job_name="J", stage="Cut Start", stage_group="FABRICATION",
                start_install=start, install_hrs=None, num_guys=2, comp_eta=None,
            )
            db.session.commit()
            row = _row_for(admin_client, "/brain/get-all-jobs", 12)
            assert row["comp_eta_effective"] == start.isoformat()

    def test_install_hrs_zero_falls_back_to_start_install(self, app, admin_client):
        with app.app_context():
            start = date(2026, 1, 5)
            make_release(
                13, "A", job_name="J", stage="Cut Start", stage_group="FABRICATION",
                start_install=start, install_hrs=0, num_guys=2, comp_eta=None,
            )
            db.session.commit()
            row = _row_for(admin_client, "/brain/get-all-jobs", 13)
            assert row["comp_eta_effective"] == start.isoformat()

    def test_install_hrs_nan_falls_back_to_start_install(self, app, admin_client):
        with app.app_context():
            start = date(2026, 1, 5)
            make_release(
                14, "A", job_name="J", stage="Cut Start", stage_group="FABRICATION",
                start_install=start, install_hrs=float("nan"), num_guys=2, comp_eta=None,
            )
            db.session.commit()
            row = _row_for(admin_client, "/brain/get-all-jobs", 14)
            assert row["comp_eta_effective"] == start.isoformat()


class TestRowShapeParity:
    def test_get_all_jobs_and_jobs_rows_have_identical_keys(self, app, admin_client):
        """Lock the two serializers together so the cursor poll never ships a
        row missing a field the bulk load provides (or vice-versa)."""
        with app.app_context():
            make_release(
                20, "A", job_name="J", stage="Cut Start", stage_group="FABRICATION",
                start_install=date(2026, 1, 5), install_hrs=40, num_guys=2,
                comp_eta=date(2026, 2, 2),
            )
            db.session.commit()

            bulk = admin_client.get("/brain/get-all-jobs").get_json()["jobs"]
            cursor = admin_client.get("/brain/jobs").get_json()["jobs"]

            assert len(bulk) == 1 and len(cursor) == 1
            assert set(bulk[0].keys()) == set(cursor[0].keys())
            # And the new shared fields are present on both
            for k in ("comp_eta_effective", "num_guys", "is_active"):
                assert k in bulk[0]
                assert k in cursor[0]


def _row_for(client, path, job_number):
    body = client.get(path).get_json()
    rows = [r for r in body["jobs"] if r["Job #"] == job_number]
    assert rows, f"job {job_number} not found in {path} response"
    return rows[0]
