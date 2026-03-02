"""
Trello helpers for user resolution and event attribution.
"""

from typing import Optional


def resolve_internal_user_id_from_trello(trello_user_id: Optional[str]) -> Optional[int]:
    """
    Resolve Trello user id (member id) to our User record.
    Uses users.trello_id (stored as string) for lookup.

    Returns:
        users.id if found, else None
    """
    if not trello_user_id or not str(trello_user_id).strip():
        return None
    from app.models import User
    trello_id_str = str(trello_user_id).strip()
    user = User.query.filter_by(trello_id=trello_id_str).first()
    return user.id if user else None
