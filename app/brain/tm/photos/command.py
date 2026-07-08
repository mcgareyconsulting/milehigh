"""Commands for T&M ticket photo/video attachments.

UploadTMTicketAttachmentCommand writes the file to storage and inserts a
TMTicketAttachment row. On any failure after the file is written, the file is
unlinked before the exception propagates so we don't leak orphans.

Mirrors app/brain/board/photos/command.py, plus a draft-only gate: field
evidence is captured during ticket creation/edit, so attachments can only be
added or removed while the parent ticket is still a 'draft' (same rule as
service.update_ticket). Viewing/listing is unrestricted by status.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import TMTicket, TMTicketAttachment, db
from app.logging_config import get_logger

from app.brain.tm.photos.storage import (
    save_attachment,
    delete_attachment_file,
    extension_for_mime,
)

logger = get_logger(__name__)


@dataclass
class UploadTMTicketAttachmentCommand:
    """Attach a single photo/video to a T&M ticket."""
    tm_ticket_id: int
    file_bytes: bytes
    filename: Optional[str]
    mime_type: str
    uploaded_by_user_id: int

    def execute(self) -> TMTicketAttachment:
        ticket: TMTicket = db.session.get(TMTicket, self.tm_ticket_id)
        if not ticket:
            raise ValueError(f"T&M ticket {self.tm_ticket_id} not found")
        if ticket.status != "draft":
            raise PermissionError(f"Ticket is {ticket.status}; attachments can only be added to a draft")

        attachment = TMTicketAttachment(
            tm_ticket_id=self.tm_ticket_id,
            storage_key='',  # filled in after we know the row id
            original_filename=self.filename,
            mime_type=self.mime_type,
            file_size_bytes=len(self.file_bytes),
            uploaded_by_user_id=self.uploaded_by_user_id,
            uploaded_at=datetime.utcnow(),
        )
        db.session.add(attachment)
        db.session.flush()  # assigns attachment.id

        ext = extension_for_mime(self.mime_type)
        storage_key = save_attachment(self.tm_ticket_id, f"{attachment.id}{ext}", self.file_bytes)

        try:
            attachment.storage_key = storage_key
            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_attachment_file(storage_key)
            raise

        logger.info("tm_ticket_attachment_uploaded", tm_ticket_id=self.tm_ticket_id,
                    attachment_id=attachment.id, mime_type=self.mime_type)
        return attachment


def delete_attachment(attachment: TMTicketAttachment) -> None:
    """Soft-delete an attachment. Draft-only, mirroring the upload gate."""
    if attachment.ticket.status != "draft":
        raise PermissionError(f"Ticket is {attachment.ticket.status}; attachments can only be removed from a draft")
    attachment.is_deleted = True
    db.session.commit()
    logger.info("tm_ticket_attachment_deleted", tm_ticket_id=attachment.tm_ticket_id,
                attachment_id=attachment.id)
