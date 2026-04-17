"""Shared helpers for parsing @FirstName mentions and resolving to users.

Used by board comments and DWL notes. Keeping this centralized ensures parsing
stays consistent with the frontend MentionInput component (regex `/@(\\w+)/`).
"""
import re

from app.models import User, db


_MENTION_RE = re.compile(r'@(\w+)')


def parse_mentions(text):
    """Return a set of lowercased first-names mentioned in the text."""
    if not text:
        return set()
    return {m.lower() for m in _MENTION_RE.findall(text)}


def resolve_mentioned_users(names):
    """Resolve a set of lowercased first-names to active User rows.

    Self-mentions are allowed (useful for self-reminders and testing).
    """
    if not names:
        return []
    return User.query.filter(
        db.func.lower(User.first_name).in_(list(names)),
        User.is_active.is_(True),
    ).all()
