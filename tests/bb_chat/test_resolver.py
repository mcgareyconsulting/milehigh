"""The resolver turns a typed message into a release/submittal anchor."""
from app.brain.bb_chat import resolver
from app.models import Submittals, db

from tests.conftest import make_release


def _submittal(sid, project_number, **extra):
    s = Submittals(submittal_id=sid, project_number=project_number,
                   submittal_drafting_status="", **extra)
    db.session.add(s)
    db.session.flush()
    return s


def test_resolves_hyphen_job_release(app):
    with app.app_context():
        make_release(290, "153")
        a = resolver.resolve("summarize 290-153 for me")
        assert a["kind"] == "release" and a["job"] == 290 and a["release"] == "153"


def test_resolves_space_and_word_forms(app):
    with app.app_context():
        make_release(290, "153")
        for text in ["how's 290 153 going", "job 290 release 153 status"]:
            a = resolver.resolve(text)
            assert a and a["job"] == 290 and a["release"] == "153", text


def test_job_only_reference(app):
    with app.app_context():
        make_release(290, "153")
        a = resolver.resolve("what's happening on job 290")
        assert a["kind"] == "release" and a["job"] == 290 and a["release"] is None


def test_resolves_submittal(app):
    with app.app_context():
        _submittal("SUB-1234", "290")
        a = resolver.resolve("what's the hold-up on submittal SUB-1234?")
        assert a["kind"] == "submittal" and a["submittal_id"] == "SUB-1234"


def test_no_reference_returns_none(app):
    with app.app_context():
        make_release(290, "153")
        assert resolver.resolve("hey, how are you today?") is None


def test_unknown_number_returns_none(app):
    with app.app_context():
        make_release(290, "153")
        assert resolver.resolve("summarize 999-999") is None
