"""Project pipeline pull — active releases + open drafting for a job."""
from datetime import date

from app.brain.lookahead.pipeline import (
    classify_install_date,
    get_project_pipeline,
    KIND_HARD,
    KIND_MISSING,
    KIND_PROJECTED,
)
from app.models import Releases, Submittals, db


def _release(job=500, release="100", **kw):
    defaults = dict(
        job=job,
        release=release,
        job_name="Novel Flatiron",
        description=f"Scope {release}",
        stage="Released",
        stage_group="FABRICATION",
        fab_hrs=40.0,
        install_hrs=16.0,
        fab_order=10.0,
        is_active=True,
        is_archived=False,
        start_install_asap=False,
        start_install_no_color=False,
    )
    defaults.update(kw)
    return Releases(**defaults)


def _drr(project_number="500", submittal_id="s1", **kw):
    defaults = dict(
        submittal_id=submittal_id,
        project_number=str(project_number),
        project_name="Novel Flatiron",
        title="Building A Rails",
        status="Open",
        type="Drafting Release Review",
        submittal_drafting_status="STARTED",
        rel=200,
    )
    defaults.update(kw)
    return Submittals(**defaults)


def test_classify_install_date_kinds():
    from app.brain.lookahead.pipeline import KIND_ASAP, KIND_NEUTRAL

    assert classify_install_date({
        "start_install": date(2026, 8, 1),
        "start_install_formulaTF": False,
        "start_install_asap": False,
        "start_install_no_color": False,
    }) == KIND_HARD
    assert classify_install_date({
        "start_install": date(2026, 8, 1),
        "start_install_formulaTF": True,
    }) == KIND_PROJECTED
    assert classify_install_date({"start_install": None}) == KIND_MISSING
    # ASAP labels a HARD date as a rush. schedule_builder maps KIND_ASAP to SOURCE_HARD,
    # so the flag on a projected date must NOT win — that would report an estimate as a
    # commitment. Since ASAP stopped stamping its own date, a flag without a hard date is
    # reachable (the API takes the flag alone; the modal is what requires the date).
    assert classify_install_date({
        "start_install": date(2026, 8, 1),
        "start_install_formulaTF": False,
        "start_install_asap": True,
    }) == KIND_ASAP
    assert classify_install_date({
        "start_install": date(2026, 8, 1),
        "start_install_formulaTF": True,
        "start_install_asap": True,
    }) == KIND_PROJECTED
    assert classify_install_date({
        "start_install": date(2026, 8, 1),
        "start_install_formulaTF": False,
        "start_install_no_color": True,
    }) == KIND_NEUTRAL


def test_pipeline_empty_job(app):
    with app.app_context():
        out = get_project_pipeline(999)
        assert out["found"] is False
        assert out["job"] == 999
        assert out["releases"] == []
        assert out["drafting"] == []


def test_pipeline_invalid_job():
    out = get_project_pipeline("not-a-number")
    assert out["found"] is False
    assert "error" in out


def test_pipeline_job_500_shaped(app):
    with app.app_context():
        db.session.add_all([
            _release(
                release="615",
                description="SE Canopy Embed Mods",
                stage="Ship Planning",
                stage_group="READY_TO_SHIP",
                start_install=date(2026, 8, 5),
                start_install_formulaTF=False,
                ship_date=date(2026, 8, 4),
                comp_eta=date(2026, 8, 6),
                fab_order=5.0,
            ),
            _release(
                release="650",
                description="RFI 256 Added Beam",
                stage="Released",
                start_install=None,
                start_install_formulaTF=None,
                fab_order=80.555,  # unqueued default
            ),
            _release(
                release="999",
                description="Archived noise",
                is_archived=True,
                start_install=date(2026, 7, 1),
                start_install_formulaTF=False,
            ),
            _drr(submittal_id="drr-1", title="Stair Core 3", rel=300, due_date=date(2026, 8, 10)),
            _drr(
                submittal_id="drr-closed",
                title="Closed package",
                status="Closed",
                rel=301,
            ),
            Submittals(
                submittal_id="gc-1",
                project_number="500",
                project_name="Novel Flatiron",
                title="Guardrails for GC",
                status="Open",
                type="Submittal for GC  Approval",
                submittal_drafting_status="",
            ),
        ])
        db.session.commit()

        out = get_project_pipeline(500)
        assert out["found"] is True
        assert out["job"] == 500
        assert out["project_name"] == "Novel Flatiron"

        codes = {r["code"] for r in out["releases"]}
        assert codes == {"500-615", "500-650"}
        assert "500-999" not in codes  # archived excluded

        by_code = {r["code"]: r for r in out["releases"]}
        assert by_code["500-615"]["date_kind"] == KIND_HARD
        assert by_code["500-615"]["ship_date"] == "2026-08-04"
        assert by_code["500-650"]["date_kind"] == KIND_MISSING
        assert by_code["500-650"]["unqueued"] is True

        assert len(out["drafting"]) == 1
        assert out["drafting"][0]["title"] == "Stair Core 3"
        assert out["drafting"][0]["due_date"] == "2026-08-10"

        assert len(out["gc_approvals"]) == 1
        assert out["gc_approvals"][0]["title"] == "Guardrails for GC"

        flag_codes = {f["code"] for f in out["flags"]}
        assert "unqueued" in flag_codes
        assert "missing_install_date" in flag_codes
