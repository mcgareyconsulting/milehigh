"""Validation for subcontractor roster payloads — small and boring on purpose,
no email-deliverability checking beyond basic shape (Graph will reject a
malformed address at send time; this just catches obvious typos early)."""
import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_invite_payload(body: dict) -> str | None:
    """Returns an error string, or None if the payload is well-formed enough
    to attempt (existence/duplicate checks happen in the route, which needs
    a DB query the validator shouldn't own)."""
    company_name = (body.get("company_name") or "").strip()
    contact_name = (body.get("contact_name") or "").strip()
    email = (body.get("email") or "").strip()

    if not company_name:
        return "company_name is required"
    if not contact_name:
        return "contact_name is required"
    if not email or not _EMAIL_RE.match(email):
        return "A valid email is required"
    return None
