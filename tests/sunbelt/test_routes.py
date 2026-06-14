"""Integration tests for the admin Sunbelt endpoints (HTTP via test_client)."""
import io

from tests.sunbelt.conftest import CSV_PATH


def _upload_sample(client):
    with open(CSV_PATH, "rb") as f:
        data = f.read()
    return client.post(
        "/admin/sunbelt/upload",
        data={"file": (io.BytesIO(data), "sunbelt.csv")},
        content_type="multipart/form-data",
    )


def _by_po(rentals, po):
    return next(r for r in rentals if r["po_number"] == po)


def test_non_admin_forbidden(non_admin_client):
    assert non_admin_client.get("/admin/sunbelt/report").status_code == 403


def test_upload_then_report_reconciles_and_flags(admin_client, seed_jobs):
    resp = _upload_sample(admin_client)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["snapshot"]["row_count"] == 21

    report = admin_client.get("/admin/sunbelt/report").get_json()
    rentals = report["rentals"]
    assert report["snapshot"] is not None
    assert report["totals"]["rental_count"] == 21

    # 480 Alta Flatirons -> exact PO match to our release.
    alta = _by_po(rentals, "480")
    assert alta["matched_job_number"] == 480
    assert alta["match_method"] == "po_number"

    # 520 "Oak Hil" -> resolved to job 530 via address, flagged on a finished job.
    oak = _by_po(rentals, "520")
    assert oak["matched_job_number"] == 530
    assert oak["match_method"] == "address"
    assert "on_finished_job" in {d["type"] for d in oak["discrepancies"]}

    # 490 Capital Hill -> submittal-only match.
    cap = _by_po(rentals, "490")
    assert cap["matched_job_number"] == 490
    assert cap["match_method"] == "submittal"

    # 170 Banyan -> est return long past, still billing -> overdue.
    banyan = _by_po(rentals, "170")
    assert "overdue" in {d["type"] for d in banyan["discrepancies"]}


def test_snapshot_history_and_diff(admin_client, seed_jobs):
    first = _upload_sample(admin_client).get_json()["snapshot"]["id"]
    second = _upload_sample(admin_client).get_json()["snapshot"]["id"]
    assert second != first

    snapshots = admin_client.get("/admin/sunbelt/snapshots").get_json()["snapshots"]
    assert len(snapshots) == 2

    # Latest report diffs against the prior identical upload -> every row 'unchanged'.
    report = admin_client.get("/admin/sunbelt/report").get_json()
    assert report["previous_snapshot"]["id"] == first
    assert all(r["change"] == "unchanged" for r in report["rentals"])

    # A specific historical snapshot: the first upload had no predecessor -> 'new'.
    hist = admin_client.get(f"/admin/sunbelt/report/{first}").get_json()
    assert hist["previous_snapshot"] is None
    assert all(r["change"] == "new" for r in hist["rentals"])


def test_report_empty_when_no_snapshots(admin_client):
    report = admin_client.get("/admin/sunbelt/report").get_json()
    assert report["snapshot"] is None
    assert report["rentals"] == []


def test_bad_csv_rejected(admin_client):
    resp = admin_client.post(
        "/admin/sunbelt/upload",
        data={"file": (io.BytesIO(b"foo,bar\n1,2\n"), "bad.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
