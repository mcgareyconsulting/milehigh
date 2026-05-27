"""Tests for the list_drawing_versions tool executor."""
import pytest

from app.banana_boy import tools
from app.brain.job_log.features.pdf_markup.storage import save_pdf
from app.models import ReleaseDrawingVersion, db
from tests.conftest import make_release, make_user


PDF = b"%PDF-1.4\n%fixture\n%%EOF\n"


@pytest.fixture
def storage_root(app, tmp_path):
    app.config['PDF_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


def _add_version(*, release_id, version_number, source_version_id=None,
                 is_deleted=False, note=None, uploader=None):
    storage_key = save_pdf(release_id, version_number, PDF)
    v = ReleaseDrawingVersion(
        release_id=release_id,
        version_number=version_number,
        storage_key=storage_key,
        original_filename=f"v{version_number}.pdf",
        mime_type='application/pdf',
        file_size_bytes=len(PDF),
        uploaded_by_user_id=uploader.id if uploader else 1,
        source_version_id=source_version_id,
        is_deleted=is_deleted,
        note=note,
    )
    db.session.add(v)
    db.session.flush()
    return v


def test_list_versions_returns_descending_with_latest_flag(app, storage_root):
    with app.app_context():
        user = make_user("d1", first_name="Pat", last_name="Pico", is_drafter=True)
        rel = make_release(480, "299")
        v1 = _add_version(release_id=rel.id, version_number=1, uploader=user, note="first")
        _add_version(release_id=rel.id, version_number=2, uploader=user,
                     source_version_id=v1.id, note="redlines")
        db.session.commit()

        result = tools.list_drawing_versions(480, "299")

    assert result["job"] == 480
    assert result["release"] == "299"
    versions = result["versions"]
    assert [v["version_number"] for v in versions] == [2, 1]
    assert versions[0]["is_latest"] is True
    assert versions[1]["is_latest"] is False
    assert versions[0]["uploaded_by"] == "Pat Pico"
    assert versions[0]["note"] == "redlines"
    assert versions[0]["source_version_id"] == v1.id
    assert versions[1]["source_version_id"] is None


def test_list_versions_skips_soft_deleted(app, storage_root):
    with app.app_context():
        user = make_user("d2", is_drafter=True)
        rel = make_release(480, "299")
        _add_version(release_id=rel.id, version_number=1, uploader=user)
        _add_version(release_id=rel.id, version_number=2, uploader=user,
                     is_deleted=True)
        db.session.commit()

        result = tools.list_drawing_versions(480, "299")

    assert [v["version_number"] for v in result["versions"]] == [1]


def test_list_versions_empty_when_no_versions(app, storage_root):
    with app.app_context():
        make_release(480, "299")
        db.session.commit()
        result = tools.list_drawing_versions(480, "299")

    assert result["versions"] == []


def test_list_versions_unknown_release_errors(app, storage_root):
    with app.app_context():
        result = tools.list_drawing_versions(999, "999")
    assert "error" in result


def test_list_versions_requires_inputs(app, storage_root):
    with app.app_context():
        assert "error" in tools.list_drawing_versions(None, "299")
        assert "error" in tools.list_drawing_versions(480, "")
        assert "error" in tools.list_drawing_versions(480, "   ")


def test_list_versions_tool_registered():
    assert tools.TOOL_LIST_DRAWING_VERSIONS in tools.TOOL_EXECUTORS
    names = {t["name"] for t in tools.TOOL_DEFINITIONS}
    assert tools.TOOL_LIST_DRAWING_VERSIONS in names
    # Read-only — must NOT be in USER_SCOPED_TOOLS
    assert tools.TOOL_LIST_DRAWING_VERSIONS not in tools.USER_SCOPED_TOOLS
