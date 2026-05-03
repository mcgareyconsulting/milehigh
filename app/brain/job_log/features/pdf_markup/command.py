"""Commands for the PDF markup feature.

Each command writes the PDF to storage, inserts a `ReleaseDrawingVersion` row,
and emits a `ReleaseEvents` row via JobEventService.create_and_close. On any
failure after the file has been written, the file is unlinked before the
exception propagates so we don't leak orphans.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func

from app.models import Releases, ReleaseDrawingVersion, db
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

from app.brain.job_log.features.pdf_markup.storage import save_pdf, delete_pdf_file

logger = get_logger(__name__)


def _username_suffix(user_id: Optional[int]) -> str:
    if not user_id:
        return "Brain"
    from app.models import User
    user = db.session.get(User, user_id)
    if not user:
        return "Brain"
    return f"Brain:{user.username}"


@dataclass
class UploadInitialDrawingCommand:
    """First-time upload of a release's PDF (creates v1)."""
    release_id: int
    file_bytes: bytes
    filename: Optional[str]
    mime_type: str
    uploaded_by_user_id: int
    note: Optional[str] = None

    def execute(self) -> ReleaseDrawingVersion:
        release: Releases = db.session.get(Releases, self.release_id)
        if not release:
            raise ValueError(f"Release {self.release_id} not found")

        existing = db.session.query(func.count(ReleaseDrawingVersion.id)).filter(
            ReleaseDrawingVersion.release_id == self.release_id,
        ).scalar()
        if existing:
            raise ValueError("Drawing already exists for this release; use SaveDrawingVersionCommand")

        storage_key = save_pdf(self.release_id, 1, self.file_bytes)

        try:
            version = ReleaseDrawingVersion(
                release_id=self.release_id,
                version_number=1,
                storage_key=storage_key,
                original_filename=self.filename,
                mime_type=self.mime_type,
                file_size_bytes=len(self.file_bytes),
                uploaded_by_user_id=self.uploaded_by_user_id,
                uploaded_at=datetime.utcnow(),
                source_version_id=None,
                note=self.note,
            )
            db.session.add(version)
            db.session.flush()

            JobEventService.create_and_close(
                job=release.job,
                release=release.release,
                action='upload_drawing',
                source=_username_suffix(self.uploaded_by_user_id),
                payload={
                    'from': None,
                    'to': {
                        'version': 1,
                        'version_id': version.id,
                        'filename': self.filename,
                    },
                },
            )

            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_pdf_file(storage_key)
            raise

        logger.info(
            "upload_drawing complete",
            extra={'release_id': self.release_id, 'version_id': version.id},
        )
        return version


@dataclass
class SaveDrawingVersionCommand:
    """Save a marked-up PDF as the next version derived from `source_version_id`."""
    release_id: int
    file_bytes: bytes
    uploaded_by_user_id: int
    source_version_id: int
    note: Optional[str] = None
    mime_type: str = 'application/pdf'

    def execute(self) -> ReleaseDrawingVersion:
        release: Releases = db.session.get(Releases, self.release_id)
        if not release:
            raise ValueError(f"Release {self.release_id} not found")

        source = db.session.get(ReleaseDrawingVersion, self.source_version_id)
        if not source or source.release_id != self.release_id:
            raise ValueError(
                f"source_version_id {self.source_version_id} not found for release {self.release_id}"
            )

        current_max = db.session.query(func.max(ReleaseDrawingVersion.version_number)).filter(
            ReleaseDrawingVersion.release_id == self.release_id,
        ).scalar() or 0
        next_version = current_max + 1

        storage_key = save_pdf(self.release_id, next_version, self.file_bytes)

        try:
            version = ReleaseDrawingVersion(
                release_id=self.release_id,
                version_number=next_version,
                storage_key=storage_key,
                original_filename=source.original_filename,
                mime_type=self.mime_type,
                file_size_bytes=len(self.file_bytes),
                uploaded_by_user_id=self.uploaded_by_user_id,
                uploaded_at=datetime.utcnow(),
                source_version_id=self.source_version_id,
                note=self.note,
            )
            db.session.add(version)
            db.session.flush()

            JobEventService.create_and_close(
                job=release.job,
                release=release.release,
                action='save_drawing_version',
                source=_username_suffix(self.uploaded_by_user_id),
                payload={
                    'from': {'version': source.version_number, 'version_id': source.id},
                    'to': {
                        'version': next_version,
                        'version_id': version.id,
                        'source_version_id': self.source_version_id,
                        'note': self.note,
                    },
                },
            )

            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_pdf_file(storage_key)
            raise

        logger.info(
            "save_drawing_version complete",
            extra={
                'release_id': self.release_id,
                'version_id': version.id,
                'version_number': next_version,
                'source_version_id': self.source_version_id,
            },
        )
        return version
