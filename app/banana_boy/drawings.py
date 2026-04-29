"""Fab-drawing PDF loaders for Banana Boy compliance scans.

V1 reads from the local filesystem under BANANA_BOY_DRAWINGS_DIR using the
naming convention {job}-{release}-fc.pdf. V2 will swap in a Procore loader;
the abstract base keeps the tool/prompt code stable across that change.
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
