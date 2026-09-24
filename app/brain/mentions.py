"""Shared helpers for parsing @FirstName mentions and resolving to users.

Used by board comments, DWL notes and drawing-version comments. Keeping this
centralized ensures parsing stays consistent with the frontend MentionInput
component (regex `/@(\\w+)/`), and that every writer stamps the mentioner's name
the same way — `user_display_name` is re-exported here so a mention producer
imports its byline from the same place it imports its parser.

Subcontractor accounts are mention targets too (T3), on the RELEASE-linked producers
only — drawing comments and release issues — because those are the surfaces a sub can
actually open. A sub matches on the first word of `contact_name`, the same "@FirstName"
rule staff use, so a mention that lands on both a staffer and a sub sharing a first
name notifies both: the writer typed one name, and silently picking one would hide
the other. `mention_targets` is the one-call form producers should use.
"""
import re

from app.models import Subcontractor, User, db, user_display_name  # noqa: F401  (re-exported)


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


def resolve_mentioned_subcontractors(names):
    """Resolve a set of lowercased first-names to active Subcontractor rows.

    The handle is the first word of `contact_name` ("Sam Sub" -> "sam"), matched
    case-insensitively. Inactive accounts never match: a deactivated sub keeps no
    inbox, so a mention of them is dropped rather than queued for a login that
    cannot happen.
    """
    if not names:
        return []
    wanted = {n.lower() for n in names}
    subs = Subcontractor.query.filter(Subcontractor.is_active.is_(True)).all()
    return [
        s for s in subs
        if (s.contact_name or '').strip().split(' ', 1)[0].lower() in wanted
    ]


def mention_targets(names):
    """Every recipient a mention resolves to, as (users, subcontractors)."""
    return resolve_mentioned_users(names), resolve_mentioned_subcontractors(names)
