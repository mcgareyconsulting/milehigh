"""Tests for the DB-backed and composite DrawingLoaders.

The composite loader is what app/__init__.py wires for production: try the
ReleaseDrawingVersionLoader (latest marked-up PDF) first, fall back to the
LocalDrawingLoader (on-disk {job}-{release}-fc.pdf).
"""
from pathlib import Path

import pytest

from app.banana_boy.drawings import (
    CompositeDrawingLoader,
    LocalDrawingLoader,
    ReleaseDrawingVersionLoader,
)
from app.brain.job_log.features.pdf_markup.storage import save_pdf
from app.models import ReleaseDrawingVersion, db
from tests.conftest import make_release, make_user


PDF_V1 = b"%PDF-1.4\n%v1-original-no-markup\n%%EOF\n"
PDF_V2 = b"%PDF-1.4\n%v2-with-pen-and-text\n%%EOF\n"


@pytest.fixture
def storage_root(app, tmp_path):
    """Point the PDF storage helpers at a tmp directory for the test."""
    app.config['PDF_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


def _make_version(*, release_id, version_number, data, source_version_id=None,
                  is_deleted=False, uploader=None):
    storage_key = save_pdf(release_id, version_number, data)
    v = ReleaseDrawingVersion(
        release_id=release_id,
        version_number=version_number,
        storage_key=storage_key,
        original_filename=f"v{version_number}.pdf",
        mime_type='application/pdf',
        file_size_bytes=len(data),
        uploaded_by_user_id=uploader.id if uploader else 1,
        source_version_id=source_version_id,
        is_deleted=is_deleted,
    )
    db.session.add(v)
    db.session.flush()
    return v


def test_release_loader_returns_latest_version(app, storage_root):
    with app.app_context():
        user = make_user("drafter1", first_name="Sam", last_name="Stark", is_drafter=True)
        rel = make_release(480, "299")
        v1 = _make_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader=user)
        _make_version(release_id=rel.id, version_number=2, data=PDF_V2,
                      source_version_id=v1.id, uploader=user)
        db.session.commit()

        loaded = ReleaseDrawingVersionLoader().load(480, "299")

    assert loaded is not None
    pdf_bytes, meta = loaded
    assert pdf_bytes == PDF_V2
    assert meta["source"] == "release_drawing_versions"
    assert meta["version_number"] == 2
    assert meta["uploaded_by"] == "Sam Stark"
    assert meta["size_bytes"] == len(PDF_V2)


def test_release_loader_skips_soft_deleted(app, storage_root):
    """A soft-deleted latest version must be ignored; loader returns prior."""
    with app.app_context():
        user = make_user("drafter2", is_drafter=True)
        rel = make_release(480, "299")
        v1 = _make_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader=user)
        _make_version(release_id=rel.id, version_number=2, data=PDF_V2,
                      source_version_id=v1.id, uploader=user, is_deleted=True)
        db.session.commit()

        loaded = ReleaseDrawingVersionLoader().load(480, "299")

    assert loaded is not None
    pdf_bytes, meta = loaded
    assert pdf_bytes == PDF_V1
    assert meta["version_number"] == 1


def test_release_loader_returns_none_when_no_versions(app, storage_root):
    with app.app_context():
        make_release(480, "299")
        db.session.commit()
        assert ReleaseDrawingVersionLoader().load(480, "299") is None


def test_release_loader_returns_none_for_unknown_release(app, storage_root):
    with app.app_context():
        assert ReleaseDrawingVersionLoader().load(999, "999") is None


def test_release_loader_blank_inputs(app, storage_root):
    with app.app_context():
        assert ReleaseDrawingVersionLoader().load(None, "299") is None
        assert ReleaseDrawingVersionLoader().load(480, "") is None
        assert ReleaseDrawingVersionLoader().load(480, "   ") is None


def test_release_loader_handles_missing_blob_gracefully(app, storage_root):
    """If the DB has a row but the file is gone, loader returns None (not raises)."""
    with app.app_context():
        user = make_user("drafter3", is_drafter=True)
        rel = make_release(480, "299")
        v = _make_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader=user)
        db.session.commit()
        # Wipe the file out from under the row.
        Path(storage_root / v.storage_key).unlink()

        loaded = ReleaseDrawingVersionLoader().load(480, "299")

    assert loaded is None


def test_composite_loader_prefers_first_loader(app, storage_root, tmp_path):
    """When the DB has a marked-up version, composite returns it (not the FC PDF)."""
    fc_dir = tmp_path / "fc"
    fc_dir.mkdir()
    (fc_dir / "480-299-fc.pdf").write_bytes(b"%PDF-fc-on-disk%%EOF")

    with app.app_context():
        user = make_user("drafter4", is_drafter=True)
        rel = make_release(480, "299")
        _make_version(release_id=rel.id, version_number=1, data=PDF_V2, uploader=user)
        db.session.commit()

        composite = CompositeDrawingLoader(
            ReleaseDrawingVersionLoader(),
            LocalDrawingLoader(fc_dir),
        )
        loaded = composite.load(480, "299")

    assert loaded is not None
    pdf_bytes, meta = loaded
    assert pdf_bytes == PDF_V2
    assert meta["source"] == "release_drawing_versions"


def test_composite_loader_falls_back_when_db_empty(app, storage_root, tmp_path):
    """No marked-up versions → composite returns the on-disk FC PDF."""
    fc_dir = tmp_path / "fc"
    fc_dir.mkdir()
    (fc_dir / "480-299-fc.pdf").write_bytes(b"%PDF-fc-on-disk%%EOF")

    with app.app_context():
        make_release(480, "299")
        db.session.commit()

        composite = CompositeDrawingLoader(
            ReleaseDrawingVersionLoader(),
            LocalDrawingLoader(fc_dir),
        )
        loaded = composite.load(480, "299")

    assert loaded is not None
    pdf_bytes, meta = loaded
    assert pdf_bytes == b"%PDF-fc-on-disk%%EOF"
    assert meta["source"] == "local"


def test_composite_loader_returns_none_when_all_miss(app, storage_root, tmp_path):
    fc_dir = tmp_path / "fc"
    fc_dir.mkdir()  # empty
    with app.app_context():
        composite = CompositeDrawingLoader(
            ReleaseDrawingVersionLoader(),
            LocalDrawingLoader(fc_dir),
        )
        assert composite.load(480, "299") is None


def test_composite_loader_rejects_empty_loader_list():
    with pytest.raises(ValueError):
        CompositeDrawingLoader()
