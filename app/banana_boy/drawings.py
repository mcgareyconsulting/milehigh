"""Fab-drawing PDF loaders for Banana Boy compliance scans.

The CompositeDrawingLoader chains a DB-backed loader (latest marked-up
release_drawing_versions blob) and a filesystem fallback ({job}-{release}-fc.pdf
under BANANA_BOY_DRAWINGS_DIR). Banana Boy reads the marked-up PDF when one
exists so Sonnet vision sees drafter annotations directly.
"""
from abc import ABC, abstractmethod
from pathlib import Path

from app.logging_config import get_logger

logger = get_logger(__name__)


class DrawingLoader(ABC):
    """Source-agnostic loader for a job-release fab-package PDF."""

    @abstractmethod
    def load(self, job: int, release: str) -> tuple[bytes, dict] | None:
        """Return (pdf_bytes, source_metadata) or None if not found."""


class LocalDrawingLoader(DrawingLoader):
    """Reads {job}-{release}-fc.pdf from a local directory."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def load(self, job: int, release: str) -> tuple[bytes, dict] | None:
        if job is None or release is None or str(release).strip() == "":
            return None
        path = self.root / f"{job}-{release}-fc.pdf"
        if not path.is_file():
            logger.info("drawing_not_found", job=job, release=release, path=str(path))
            return None
        stat = path.stat()
        return path.read_bytes(), {
            "source": "local",
            "path": str(path),
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
        }


class ReleaseDrawingVersionLoader(DrawingLoader):
    """Reads the latest non-deleted release_drawing_versions blob for a release.

    Joins (job, release) → Releases.id → ReleaseDrawingVersion.release_id, picks
    max(version_number), pulls bytes from the PDF storage helper. Returns None
    when the release has no markup history yet (caller can fall back).
    """

    def load(self, job: int, release: str) -> tuple[bytes, dict] | None:
        if job is None or release is None or str(release).strip() == "":
            return None

        from app.brain.job_log.features.pdf_markup.storage import read_pdf
        from app.models import ReleaseDrawingVersion, Releases

        release_row = Releases.query.filter_by(job=job, release=str(release)).first()
        if release_row is None:
            return None

        latest = (
            ReleaseDrawingVersion.query
            .filter_by(release_id=release_row.id, is_deleted=False)
            .order_by(ReleaseDrawingVersion.version_number.desc())
            .first()
        )
        if latest is None:
            return None

        try:
            pdf_bytes = read_pdf(latest.storage_key)
        except FileNotFoundError:
            logger.warning(
                "release_drawing_version_blob_missing",
                job=job, release=release, version_id=latest.id,
                storage_key=latest.storage_key,
            )
            return None

        uploaded_by_name = None
        if latest.uploaded_by is not None:
            first = (latest.uploaded_by.first_name or "").strip()
            last = (latest.uploaded_by.last_name or "").strip()
            uploaded_by_name = (f"{first} {last}".strip()) or latest.uploaded_by.username

        return pdf_bytes, {
            "source": "release_drawing_versions",
            "version_id": latest.id,
            "version_number": latest.version_number,
            "uploaded_at": latest.uploaded_at.isoformat() if latest.uploaded_at else None,
            "uploaded_by": uploaded_by_name,
            "note": latest.note,
            "size_bytes": latest.file_size_bytes,
        }


class CompositeDrawingLoader(DrawingLoader):
    """Tries each child loader in order and returns the first hit."""

    def __init__(self, *loaders: DrawingLoader):
        if not loaders:
            raise ValueError("CompositeDrawingLoader needs at least one loader")
        self.loaders = loaders

    def load(self, job: int, release: str) -> tuple[bytes, dict] | None:
        for loader in self.loaders:
            result = loader.load(job, release)
            if result is not None:
                return result
        return None
