"""Commands for board item photo attachments.

UploadBoardPhotoCommand writes the image to storage and inserts a
`BoardItemPhoto` row. On any failure after the file is written, the file is
unlinked before the exception propagates so we don't leak orphans.

Mirrors `app/brain/job_log/features/photos/command.py` but without the
release/Procore `JobEventService` audit step, which doesn't apply to the board.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import BoardItem, BoardItemPhoto, db
from app.logging_config import get_logger

from app.brain.board.photos.storage import (
    save_photo,
    delete_photo_file,
    extension_for_mime,
)

logger = get_logger(__name__)


@dataclass
class UploadBoardPhotoCommand:
    """Attach a single image to a board item."""
    board_item_id: int
    file_bytes: bytes
    filename: Optional[str]
    mime_type: str
    uploaded_by_user_id: int

    def execute(self) -> BoardItemPhoto:
        item: BoardItem = db.session.get(BoardItem, self.board_item_id)
        if not item:
            raise ValueError(f"Board item {self.board_item_id} not found")

        photo = BoardItemPhoto(
            board_item_id=self.board_item_id,
            storage_key='',  # filled in after we know the row id
            original_filename=self.filename,
            mime_type=self.mime_type,
            file_size_bytes=len(self.file_bytes),
            uploaded_by_user_id=self.uploaded_by_user_id,
            uploaded_at=datetime.utcnow(),
        )
        db.session.add(photo)
        db.session.flush()  # assigns photo.id

        ext = extension_for_mime(self.mime_type)
        storage_key = save_photo(self.board_item_id, f"{photo.id}{ext}", self.file_bytes)

        try:
            photo.storage_key = storage_key
            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_photo_file(storage_key)
            raise

        logger.info(
            "board upload_photo complete",
            extra={'board_item_id': self.board_item_id, 'photo_id': photo.id},
        )
        return photo
