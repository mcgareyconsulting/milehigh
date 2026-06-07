"""Commands for release photo attachments.

UploadPhotoCommand writes the image to storage, inserts a `ReleasePhoto` row,
and emits a `ReleaseEvents` row via JobEventService.create_and_close. On any
failure after the file is written, the file is unlinked before the exception
propagates so we don't leak orphans.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import Releases, ReleasePhoto, db
from app.services.job_event_service import JobEventService
from app.logging_config import get_logger

from app.brain.job_log.features.photos.storage import (
    save_photo,
    delete_photo_file,
    extension_for_mime,
)

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
class UploadPhotoCommand:
    """Attach a single image to a release."""
    release_id: int
    file_bytes: bytes
    filename: Optional[str]
    mime_type: str
    uploaded_by_user_id: int
    note: Optional[str] = None
    stage: Optional[str] = None

    def execute(self) -> ReleasePhoto:
        release: Releases = db.session.get(Releases, self.release_id)
        if not release:
            raise ValueError(f"Release {self.release_id} not found")

        photo = ReleasePhoto(
            release_id=self.release_id,
            storage_key='',  # filled in after we know the row id
            original_filename=self.filename,
            mime_type=self.mime_type,
            file_size_bytes=len(self.file_bytes),
            note=self.note,
            stage=self.stage,
            uploaded_by_user_id=self.uploaded_by_user_id,
            uploaded_at=datetime.utcnow(),
        )
        db.session.add(photo)
        db.session.flush()  # assigns photo.id

        ext = extension_for_mime(self.mime_type)
        storage_key = save_photo(self.release_id, f"{photo.id}{ext}", self.file_bytes)

        try:
            photo.storage_key = storage_key

            JobEventService.create_and_close(
                job=release.job,
                release=release.release,
                action='upload_photo',
                source=_username_suffix(self.uploaded_by_user_id),
                payload={
                    'from': None,
                    'to': {
                        'photo_id': photo.id,
                        'filename': self.filename,
                        'note': self.note,
                        'stage': self.stage,
                    },
                },
            )

            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_photo_file(storage_key)
            raise

        logger.info(
            "upload_photo complete",
            extra={'release_id': self.release_id, 'photo_id': photo.id},
        )
        return photo
