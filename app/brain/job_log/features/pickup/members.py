"""
@milehigh-header
schema_version: 1
purpose: Resolve the Trello member-id list for a pick-up card — always-on members plus the release's PM.
exports:
  parse_pm_map: Parse the "INITIALS:trello_id,..." config string into a dict.
  resolve_member_ids: Build the comma-separated idMembers string for a given release PM.
  resolve_member_users: Resolve the same members to User rows (by User.trello_id) for on-board display chips.
imports_from: [app.config, app.models (User, lazy)]
imported_by: [app/services/outbox_service (create_pickup_card branch), app/brain/job_log/routes (/brain/pickup/board)]
invariants:
  - Always-on members come from Config.PICKUP_TRELLO_MEMBER_IDS (comma-separated ids).
  - The release's PM (Releases.pm initials, e.g. "GA", "DR", "RL", "WO") maps to one
    Trello id via Config.PICKUP_PM_TRELLO_IDS; PM lookup is case-insensitive.
  - The PM id is appended only if present and not already in the always-list (deduped,
    order preserved). An unknown/blank PM simply yields the always-list.
"""
from app.config import Config as cfg
from app.logging_config import get_logger

logger = get_logger(__name__)


def parse_pm_map(raw: str) -> dict:
    """Parse "RL:id1,GA:id2" → {"RL": "id1", "GA": "id2"} (keys upper-cased)."""
    out = {}
    if not raw:
        return out
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        key, _, val = pair.partition(":")
        key, val = key.strip().upper(), val.strip()
        if key and val:
            out[key] = val
    return out


def resolve_member_ids(release_pm: str) -> str:
    """Return the comma-separated Trello idMembers for a pick-up card.

    Always-on members + the mapped PM id for this release (if any), deduped.
    """
    ids = [x.strip() for x in (cfg.PICKUP_TRELLO_MEMBER_IDS or "").split(",") if x.strip()]

    pm_key = (release_pm or "").strip().upper()
    if pm_key:
        pm_id = parse_pm_map(cfg.PICKUP_PM_TRELLO_IDS).get(pm_key)
        if pm_id and pm_id not in ids:
            ids.append(pm_id)
        elif not pm_id:
            logger.warning(f"Pickup: no Trello id mapped for PM '{pm_key}' (PICKUP_PM_TRELLO_IDS)")

    return ",".join(ids)


def _member_id_order(release_pm: str) -> list:
    """The ordered, deduped Trello member ids for a pick-up card: always-on + PM."""
    ids = [x.strip() for x in (cfg.PICKUP_TRELLO_MEMBER_IDS or "").split(",") if x.strip()]
    pm_key = (release_pm or "").strip().upper()
    if pm_key:
        pm_id = parse_pm_map(cfg.PICKUP_PM_TRELLO_IDS).get(pm_key)
        if pm_id and pm_id not in ids:
            ids.append(pm_id)
    return ids


def _display_name(u) -> str:
    name = " ".join(p for p in [u.first_name, u.last_name] if p).strip()
    return name or u.username


def _initials(u) -> str:
    parts = [p for p in [u.first_name, u.last_name] if p]
    if parts:
        return "".join(p[0] for p in parts[:2]).upper()
    return (u.username or "?")[:2].upper()


def resolve_member_users(release_pm: str) -> list:
    """Resolve a pick-up card's assigned members to Users for on-board display.

    Same membership as resolve_member_ids (always-on PICKUP_TRELLO_MEMBER_IDS + the
    release PM's mapped id), but returns the matching rows from our own users table —
    looked up by User.trello_id — as lightweight display dicts in config order. A
    Trello member id with no linked User (e.g. a malformed config entry) is skipped
    and logged, so the card shows everyone we can positively identify and no blanks.

    Returns: [{"username", "name", "initials"}], order-preserving and deduped.
    """
    from app.models import User

    ids = _member_id_order(release_pm)
    if not ids:
        return []

    by_tid = {u.trello_id: u for u in User.query.filter(User.trello_id.in_(ids)).all()}

    out = []
    for tid in ids:
        u = by_tid.get(tid)
        if not u:
            logger.info(f"Pickup: no User linked to Trello member id {tid!r}; skipping chip")
            continue
        out.append({
            "username": u.username,
            "name": _display_name(u),
            "initials": _initials(u),
        })
    return out
