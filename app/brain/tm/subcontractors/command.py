"""Write orchestration for subcontractor invites and ticket assignment.

InviteSubcontractorCommand / resend_invite own the ONLY implementation of
token generation so create and resend can never drift. Email send is NOT
swallowed on failure — the Subcontractor row is committed with a valid token
before send is attempted, so a failed send still leaves a resendable account;
letting the exception propagate means the admin sees a clear "created but
email failed" rather than a false success.

Every action here sends TWO separate, distinctly-worded emails rather than one
email with the admin CC'd — a CC on the sub's own "you're invited"/"you've
been added" email reads confusingly from the admin's inbox (it looks like
mail meant for someone else). The admin gets their own "you did X" confirmation
instead. Both send from the shared Carmen Miranda persona mailbox
(`Config.CARMEN_MAILBOX`, app-only Graph — see app/microsoft/mailer.py), not
from the admin's own address and not from bb@mhmw.com (whose inbox is wired to
ingestion pollers — a subcontractor's reply would otherwise land there as
unrelated bronze data).

The subcontractor-facing email (invite link / ticket link) is NOT swallowed on
failure (surfaced to the admin as a 502 — see routes.py) since it's the
subcontractor's only path to the account/ticket. The admin-facing confirmation
IS swallowed (logged as ERROR, not raised) — it's a courtesy receipt, and the
real action (invite/assignment) already succeeded, so a flaky second send
shouldn't read as a failed action.

Every link in those emails is built through `_external_link`, which refuses to
mail a link against the localhost APP_BASE_URL default outside a local
environment. BUG-10 was that failing silently: an invite went to a real inbox
carrying http://localhost:5173/... and nothing anywhere said so.
"""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import Config as cfg, LOCAL_APP_BASE_URL, current_environment, is_local_environment
from app.models import Subcontractor, TMTicket, TMTicketSubcontractor, db
from app.microsoft.mailer import send_mail
from app.logging_config import get_logger

logger = get_logger(__name__)

INVITE_TOKEN_TTL_DAYS = 7


class OutboundLinkNotConfiguredError(RuntimeError):
    """APP_BASE_URL is unset (or still the localhost default) on a deployed
    environment, so any link built here would be unreachable by the recipient.

    Raised instead of mailing a dead link. BUG-10 was exactly this failing
    silently: a real invite went to a real inbox carrying
    http://localhost:5173/sub/accept-invite/... and the only symptom anyone
    could see was "the link doesn't work".
    """


def _external_link(path: str) -> str:
    """Build an absolute link for an outbound email, or refuse to.

    Deployed environments must have APP_BASE_URL set to the real domain; if it
    is missing we raise rather than send, because the recipient has no way to
    recover from a localhost link and the sender gets no signal. Locally the
    default is legitimate (it points at the Vite dev server) and only whispers
    at DEBUG.
    """
    base = (cfg.APP_BASE_URL or "").strip().rstrip("/")
    if not base or base == LOCAL_APP_BASE_URL:
        if not is_local_environment():
            logger.error(
                "app_base_url_not_configured",
                environment=current_environment(),
                path=path,
                status="refused",
                error="APP_BASE_URL is unset; refusing to email a localhost link",
                error_type="OutboundLinkNotConfiguredError",
                exc_info=True,
            )
            raise OutboundLinkNotConfiguredError(
                "APP_BASE_URL is not set for this environment, so the email would "
                "carry an unreachable link. Set APP_BASE_URL to the Brain's public "
                "domain and try again."
            )
        logger.debug("app_base_url_local_default", path=path)
    return f"{base}{path}"


def _require_external_link_base() -> None:
    """Fail before any state changes when outbound links are unbuildable.

    The invite paths commit (a new row, or a rotated token that invalidates the
    previous one) before they send. Checking up front means a misconfigured
    environment costs nothing instead of leaving a dead subcontractor row or a
    burned token behind.
    """
    _external_link("")


def _generate_and_store_invite_token(subcontractor: Subcontractor) -> str:
    """Generate a fresh invite token, store only its hash+expiry, return the
    raw token for the caller to embed in the email link — never persisted raw."""
    raw_token = secrets.token_urlsafe(32)
    subcontractor.invite_token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    subcontractor.invite_token_expires_at = datetime.utcnow() + timedelta(days=INVITE_TOKEN_TTL_DAYS)
    return raw_token


def _invite_email_html(subcontractor: Subcontractor, raw_token: str, invited_by_name: str) -> str:
    link = _external_link(f"/sub/accept-invite/{raw_token}")
    return (
        f"<p>Hi {subcontractor.contact_name},</p>"
        f"<p>{invited_by_name} has invited you to MHMW Brain to fill out Time &amp; Material "
        f"tickets for {subcontractor.company_name}.</p>"
        f'<p><a href="{link}">Accept your invite</a> to set a password and get started.</p>'
        f"<p>This link expires in {INVITE_TOKEN_TTL_DAYS} days.</p>"
    )


def _assignment_email_html(ticket: TMTicket, subcontractor: Subcontractor, assigned_by_name: str) -> str:
    link = _external_link(f"/sub/tickets/{ticket.id}")
    job_bit = f" for job {ticket.job}" if ticket.job else ""
    where_bit = f" ({ticket.location})" if ticket.location else ""
    return (
        f"<p>Hi {subcontractor.contact_name},</p>"
        f"<p>{assigned_by_name} has added you to Time &amp; Material ticket #{ticket.id}"
        f"{job_bit}{where_bit}.</p>"
        f'<p><a href="{link}">Open the ticket</a> to fill it out and submit.</p>'
    )


def _invite_confirmation_email_html(subcontractor: Subcontractor) -> str:
    return (
        f"<p>You invited <strong>{subcontractor.contact_name}</strong> "
        f"({subcontractor.company_name}) to MHMW Brain as a subcontractor.</p>"
        f"<p>An invite link was sent to {subcontractor.email}. You'll see their status "
        f"update on the Subcontractors roster once they accept.</p>"
    )


def _resend_confirmation_email_html(subcontractor: Subcontractor) -> str:
    return (
        f"<p>You resent the MHMW Brain invite to <strong>{subcontractor.contact_name}</strong> "
        f"({subcontractor.company_name}) at {subcontractor.email}.</p>"
    )


def _assignment_confirmation_email_html(ticket: TMTicket, subcontractor: Subcontractor) -> str:
    job_bit = f" for job {ticket.job}" if ticket.job else ""
    return (
        f"<p>You added <strong>{subcontractor.contact_name}</strong> "
        f"({subcontractor.company_name}) to Time &amp; Material ticket #{ticket.id}{job_bit}.</p>"
        f"<p>They've been notified at {subcontractor.email} and can access the ticket once "
        f"they log in.</p>"
    )


@dataclass
class InviteSubcontractorCommand:
    company_name: str
    contact_name: str
    email: str
    invited_by_user_id: int
    invited_by_email: str
    invited_by_name: str

    def execute(self) -> Subcontractor:
        _require_external_link_base()  # fail before the row exists, not after
        sub = Subcontractor(
            company_name=self.company_name,
            contact_name=self.contact_name,
            email=self.email,
            invited_by_user_id=self.invited_by_user_id,
            invited_at=datetime.utcnow(),
        )
        db.session.add(sub)
        raw_token = _generate_and_store_invite_token(sub)
        db.session.commit()  # row + token persist even if the send below fails

        send_mail(
            from_mailbox=cfg.CARMEN_MAILBOX,
            to_address=sub.email,
            subject="You're invited to MHMW Brain",
            html_content=_invite_email_html(sub, raw_token, self.invited_by_name),
        )
        logger.info("subcontractor_invited", subcontractor_id=sub.id, email=sub.email,
                    invited_by_user_id=self.invited_by_user_id, invited_by_email=self.invited_by_email)

        try:
            send_mail(
                from_mailbox=cfg.CARMEN_MAILBOX,
                to_address=self.invited_by_email,
                subject=f"You invited {sub.contact_name} to MHMW Brain",
                html_content=_invite_confirmation_email_html(sub),
            )
        except Exception as exc:
            logger.error("subcontractor_invite_confirmation_failed", subcontractor_id=sub.id,
                         invited_by_email=self.invited_by_email, error=str(exc), exc_info=True)

        return sub


def resend_invite(subcontractor: Subcontractor, resent_by_email: str, resent_by_name: str) -> None:
    """Confirms to whoever clicks resend NOW, not necessarily the original
    inviter (invited_by_user_id on the row is left untouched — it stays the
    original-invite audit field; the resend's confirmation just goes to this
    call's requester, not persisted anywhere). Send identity is always
    CARMEN_MAILBOX."""
    _require_external_link_base()  # fail before the old token is rotated away
    raw_token = _generate_and_store_invite_token(subcontractor)
    subcontractor.invited_at = datetime.utcnow()
    db.session.commit()

    send_mail(
        from_mailbox=cfg.CARMEN_MAILBOX,
        to_address=subcontractor.email,
        subject="Your MHMW Brain invite",
        html_content=_invite_email_html(subcontractor, raw_token, resent_by_name),
    )
    logger.info("subcontractor_invite_resent", subcontractor_id=subcontractor.id,
                email=subcontractor.email, resent_by_email=resent_by_email)

    try:
        send_mail(
            from_mailbox=cfg.CARMEN_MAILBOX,
            to_address=resent_by_email,
            subject=f"Invite resent to {subcontractor.contact_name}",
            html_content=_resend_confirmation_email_html(subcontractor),
        )
    except Exception as exc:
        logger.error("subcontractor_resend_confirmation_failed", subcontractor_id=subcontractor.id,
                     resent_by_email=resent_by_email, error=str(exc), exc_info=True)


def set_active(subcontractor: Subcontractor, is_active: bool) -> None:
    subcontractor.is_active = is_active
    db.session.commit()
    logger.info("subcontractor_active_changed", subcontractor_id=subcontractor.id, is_active=is_active)


def assign_to_ticket(ticket: TMTicket, subcontractor: Subcontractor, assigned_by_user_id: int,
                      assigned_by_email: str | None = None, assigned_by_name: str | None = None) -> TMTicketSubcontractor:
    """Idempotent: re-assigning an already-assigned subcontractor is a no-op
    (returns the existing row, sends no email — only a NEW assignment notifies).

    The notification email is best-effort, unlike the invite email: the
    assignment itself already succeeded and already grants ticket access, so
    a failed send is logged as an ERROR (see logging-standard.md — a lost
    outbound notification is an error, not a warning) but does not undo or
    mask that success back to the admin who just assigned it.
    """
    existing = TMTicketSubcontractor.query.filter_by(
        tm_ticket_id=ticket.id, subcontractor_id=subcontractor.id).first()
    if existing:
        return existing
    assignment = TMTicketSubcontractor(
        tm_ticket_id=ticket.id,
        subcontractor_id=subcontractor.id,
        assigned_by_user_id=assigned_by_user_id,
        assigned_at=datetime.utcnow(),
    )
    db.session.add(assignment)
    db.session.commit()
    logger.info("tm_ticket_assigned_to_subcontractor", tm_ticket_id=ticket.id,
                subcontractor_id=subcontractor.id, assigned_by_user_id=assigned_by_user_id)

    if assigned_by_email:
        try:
            send_mail(
                from_mailbox=cfg.CARMEN_MAILBOX,
                to_address=subcontractor.email,
                subject=f"You've been added to T&M Ticket #{ticket.id}",
                html_content=_assignment_email_html(ticket, subcontractor, assigned_by_name or assigned_by_email),
            )
        except Exception as exc:
            logger.error("tm_ticket_assignment_notification_failed", tm_ticket_id=ticket.id,
                         subcontractor_id=subcontractor.id, error=str(exc), exc_info=True)

        try:
            send_mail(
                from_mailbox=cfg.CARMEN_MAILBOX,
                to_address=assigned_by_email,
                subject=f"You added {subcontractor.contact_name} to T&M Ticket #{ticket.id}",
                html_content=_assignment_confirmation_email_html(ticket, subcontractor),
            )
        except Exception as exc:
            logger.error("tm_ticket_assignment_confirmation_failed", tm_ticket_id=ticket.id,
                         subcontractor_id=subcontractor.id, error=str(exc), exc_info=True)

    return assignment


def unassign_from_ticket(ticket_id: int, subcontractor_id: int) -> bool:
    """Hard delete — an assignment row only encodes current visibility, no
    audit reason to soft-delete (see model docstring). Returns False if no
    such assignment existed."""
    assignment = TMTicketSubcontractor.query.filter_by(
        tm_ticket_id=ticket_id, subcontractor_id=subcontractor_id).first()
    if not assignment:
        return False
    db.session.delete(assignment)
    db.session.commit()
    logger.info("tm_ticket_unassigned_from_subcontractor", tm_ticket_id=ticket_id,
                subcontractor_id=subcontractor_id)
    return True
