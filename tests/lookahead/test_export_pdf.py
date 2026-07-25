"""PDF render + artifact store for GC look-ahead."""
from datetime import date
from io import BytesIO

from pypdf import PdfReader

from app.brain.lookahead.export_pdf import render_schedule_pdf
from app.brain.lookahead.schedule_builder import build_lookahead_schedule
from app.brain.lookahead.artifacts import save_lookahead_pdf, read_lookahead_pdf, load_meta
from app.models import Releases, db


TODAY = date(2026, 7, 25)


def _schedule_with_bars():
    return build_lookahead_schedule(
        {
            "found": True,
            "job": 500,
            "project_name": "Novel Flatiron",
            "releases": [{
                "kind": "release",
                "code": "500-615",
                "release": "615",
                "job": 500,
                "description": "SE Canopy Embed Mods",
                "stage": "Released",
                "stage_group": "FABRICATION",
                "is_complete": False,
                "fab_hrs": 40.0,
                "install_hrs": 8.0,
                "num_guys": 2.0,
                "fab_order": 4.0,
                "unqueued": False,
                "released": "2026-07-01",
                "start_install": "2026-08-12",
                "start_install_formulaTF": False,
                "start_install_asap": False,
                "start_install_no_color": False,
                "date_kind": "hard",
                "ship_date": "2026-08-11",
                "comp_eta": "2026-08-13",
            }],
            "drafting": [{
                "kind": "drafting",
                "code": "500-DRR-400",
                "title": "Open package",
                "status": "Open",
                "rel": 400,
                "due_date": "2026-08-05",
                "start_install": None,
                "created_at": "2026-07-20",
            }],
            "gc_approvals": [],
            "flags": [],
        },
        weeks=3,
        today=TODAY,
    )


def test_render_schedule_pdf_is_valid_multi_page():
    schedule = _schedule_with_bars()
    pdf_bytes = render_schedule_pdf(schedule)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 500
    reader = PdfReader(BytesIO(pdf_bytes))
    # Gantt + appendix (at least 2 pages)
    assert len(reader.pages) >= 2
    text = "".join((p.extract_text() or "") for p in reader.pages)
    assert "Novel Flatiron" in text or "Look-Ahead" in text or "500" in text


def test_render_empty_schedule_still_pdf():
    pdf_bytes = render_schedule_pdf({
        "found": False,
        "job": 999,
        "project_name": None,
        "window": {"start": "2026-07-25", "end": "2026-08-15", "weeks": 3},
        "generated_on": "2026-07-25",
        "rows": [],
        "summary": {},
        "assumptions": {"paint_note": "provisional"},
        "flags": [],
    })
    assert pdf_bytes[:4] == b"%PDF"


def test_save_and_read_artifact(app, tmp_path):
    with app.app_context():
        app.config["LOOKAHEAD_PDF_STORAGE_ROOT"] = str(tmp_path)
        schedule = _schedule_with_bars()
        pdf_bytes = render_schedule_pdf(schedule)
        meta = save_lookahead_pdf(pdf_bytes, schedule=schedule, user_id=7)
        assert meta["artifact_id"]
        assert meta["download_path"].endswith(".pdf")
        assert meta["job"] == 500
        loaded = read_lookahead_pdf(meta["artifact_id"])
        assert loaded == pdf_bytes
        assert load_meta(meta["artifact_id"])["user_id"] == 7


def test_generate_and_download_routes(app, tmp_path):
    from contextlib import ExitStack
    from unittest.mock import patch
    from tests.conftest import make_user

    with app.app_context():
        app.config["LOOKAHEAD_PDF_STORAGE_ROOT"] = str(tmp_path)
        user = make_user("la@mhmw.com", is_admin=False)
        user.is_carmen_chat = True
        db.session.commit()

        db.session.add(Releases(
            job=500,
            release="615",
            job_name="Novel Flatiron",
            description="SE Canopy",
            stage="Weld Complete",
            stage_group="FABRICATION",
            fab_hrs=40.0,
            install_hrs=8.0,
            fab_order=4.0,
            start_install=date(2026, 8, 12),
            start_install_formulaTF=False,
            start_install_asap=False,
            start_install_no_color=False,
            ship_date=date(2026, 8, 11),
            comp_eta=date(2026, 8, 13),
            is_active=True,
            is_archived=False,
        ))
        db.session.commit()

        with ExitStack() as stack:
            for target in (
                "app.auth.utils.get_current_user",
                "app.brain.lookahead.routes.get_current_user",
            ):
                stack.enter_context(patch(target, return_value=user))
            client = app.test_client()
            resp = client.post("/brain/lookahead/pdf", json={"job": 500, "weeks": 3})
            assert resp.status_code == 200, resp.get_json()
            body = resp.get_json()
            assert body["found"] is True
            assert body["artifact_id"]
            path = body["download_path"]
            assert path.startswith("/brain/lookahead/artifacts/")

            dl = client.get(path)
            assert dl.status_code == 200
            assert dl.data[:4] == b"%PDF"
            assert "pdf" in (dl.mimetype or "")


def test_download_unknown_artifact_404(app, tmp_path):
    from contextlib import ExitStack
    from unittest.mock import patch
    from tests.conftest import make_user

    with app.app_context():
        app.config["LOOKAHEAD_PDF_STORAGE_ROOT"] = str(tmp_path)
        user = make_user("la2@mhmw.com", is_admin=True)
        db.session.commit()
        with ExitStack() as stack:
            for target in (
                "app.auth.utils.get_current_user",
                "app.brain.lookahead.routes.get_current_user",
            ):
                stack.enter_context(patch(target, return_value=user))
            client = app.test_client()
            resp = client.get("/brain/lookahead/artifacts/does-not-exist.pdf")
            assert resp.status_code == 404
