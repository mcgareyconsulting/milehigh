"""
@milehigh-header
schema_version: 1
purpose: Scoped query + allowlist serializer for the subcontractor release view (T3 slice 1).
exports:
  SUB_FIELDS: The exact key set a subcontractor payload may contain
  list_releases_for_subcontractor: Crew-scoped release rows, allowlist-serialized
  serialize_release_for_sub: One row -> sub payload (exported for the allowlist test)
  get_release_for_subcontractor: One crew-scoped release (None when off-crew / missing)
  build_day_schedule_for_subcontractor: The phone timeline envelope, crew-scoped, notes stripped
  list_todos_for_subcontractor / set_todo_status_for_subcontractor: The sub's own to-dos
  list_notifications_for_subcontractor / mark_notification_read_for_subcontractor /
    mark_all_read_for_subcontractor / unread_count_for_subcontractor: The sub's own mentions
imports_from: [app.models, app.brain.job_log.utils, app.brain.install_schedule.service, app.logging_config]
imported_by: [app/brain/sub_portal/routes.py]
invariants:
  - Keys mirror the INTERNAL /brain/jobs serializer exactly, display casing included
    ('Job #', 'Comp. ETA'), because GanttChart reads those keys. A snake_case payload
    would render an empty timeline.
  - serialize_release_for_sub emits SUB_FIELDS and nothing else; the test asserts
    equality, not containment, so a new Releases column cannot leak in silently.
  - A subcontractor with no crew gets [] — never an unscoped query.
"""
from datetime import datetime

from app.brain.install_schedule.service import build_day_schedule
from app.brain.job_log.utils import serialize_value
from app.logging_config import get_logger
from app.models import ChecklistItem, Notification, Releases, db

logger = get_logger(__name__)

# The complete set of keys a subcontractor payload may carry.
#
# Chosen as (what GanttChart actually reads off a row) + (what Bill's release modal
# names) - (what he excludes). Casing matches the internal /brain/jobs serializer
# because the timeline reads these exact keys.
#
# Deliberately ABSENT, and why:
#   'Fab Hrs'          Bill's one stated exclusion [bill-2026-09-02#L921]
#   'Fab Order'        shop sequencing, not the sub's work
#   'Invoiced'         MHMW customer billing
#   'Notes'            the notes THREAD is its own scoped endpoint (slice 4); shipping
#                      a denormalized "latest" here invites the two to disagree
#   'Paint color'      not in the named scope; candidate if install asks for it
#   'Released'         internal drafting milestone
#   start_install_formula   the raw formula string, an internal scheduling detail
#   source_of_update / trello_card_id   internal plumbing and Trello identity
#   viewer_url / has_drawing / cover_photo_id / photo_count
#                      attachment plumbing pointing at @login_required routes — they
#                      would advertise doors that do not open until slice 4
#   is_active / is_archived   filtered server-side; the flags never travel
#
# 'last_updated_at' IS included: it carries no business information and the shared
# releases data contract needs a cursor for incremental refresh.
SUB_FIELDS = frozenset({
    'id',
    'Job #',
    'Release #',
    'Job',
    'Description',
    'Install HRS',
    'PM',
    'BY',
    'Stage',
    'Stage Group',
    'Start install',
    'start_install_formulaTF',
    'start_install_asap',
    'start_install_no_color',
    'Ship Date',
    'installer',
    'Comp. ETA',
    'comp_eta_effective',
    'num_guys',
    'Job Comp',
    'release_tag',
    'last_updated_at',
})


def serialize_release_for_sub(release: Releases) -> dict:
    """One release -> the subcontractor payload.

    Built by NAMING each allowed field rather than copying the internal row and
    deleting from it. The difference matters: a delete-list silently passes through
    every column added later, an allowlist does not.
    """
    # Imported lazily: both live in app/brain/job_log/routes, which registers routes on
    # brain_bp at import time. A module-level import here would couple registration order.
    from app.api.helpers import get_stage_group_from_stage
    from app.brain.job_log.routes import _comp_eta_effective

    stage = release.stage if release.stage else 'Released'
    return {
        'id': serialize_value(release.id),
        'Job #': serialize_value(release.job),
        'Release #': serialize_value(release.release),
        'Job': serialize_value(release.job_name),
        'Description': serialize_value(release.description),
        'Install HRS': serialize_value(release.install_hrs),
        'PM': serialize_value(release.pm),
        'BY': serialize_value(release.by),
        'Stage': stage,
        # Recomputed from the current stage, matching the internal serializer — a stale
        # stored stage_group would put the card in the wrong lane group.
        'Stage Group': serialize_value(get_stage_group_from_stage(stage)),
        'Start install': serialize_value(release.start_install),
        'start_install_formulaTF': serialize_value(release.start_install_formulaTF),
        'start_install_asap': serialize_value(release.start_install_asap),
        'start_install_no_color': serialize_value(release.start_install_no_color),
        'Ship Date': serialize_value(release.ship_date),
        'installer': serialize_value(release.installer),
        'Comp. ETA': serialize_value(release.comp_eta),
        'comp_eta_effective': serialize_value(_comp_eta_effective(release)),
        'num_guys': serialize_value(release.num_guys),
        'Job Comp': serialize_value(release.job_comp),
        'release_tag': serialize_value(release.release_tag),
        'last_updated_at': serialize_value(release.last_updated_at),
    }


def list_releases_for_subcontractor(subcontractor) -> list:
    """Releases on this subcontractor's crew, allowlist-serialized.

    Returns [] for an unscoped account. That is the fail-closed half of the crew
    model: an account with no crew must resolve to no releases, never to an
    unfiltered query, so a half-finished onboarding cannot expose the job log.

    Archived and soft-deleted rows are excluded here rather than shipped with flags
    for the client to filter — the flags themselves never travel.
    """
    crew = (subcontractor.installer_team or '').strip()
    if not crew:
        logger.debug("sub_releases_unscoped_account", subcontractor_id=subcontractor.id)
        return []

    rows = (
        Releases.query
        .filter(Releases.installer == crew)
        .filter(db.or_(Releases.is_archived == False, Releases.is_archived == None))  # noqa: E712
        .filter(db.or_(Releases.is_active == True, Releases.is_active == None))       # noqa: E712
        .order_by(Releases.start_install.asc(), Releases.id.asc())
        .all()
    )
    return [serialize_release_for_sub(r) for r in rows]


def _crew(subcontractor):
    return (subcontractor.installer_team or '').strip()


def _crew_release_query(crew):
    return (
        Releases.query
        .filter(Releases.installer == crew)
        .filter(db.or_(Releases.is_archived == False, Releases.is_archived == None))  # noqa: E712
        .filter(db.or_(Releases.is_active == True, Releases.is_active == None))       # noqa: E712
    )


def get_release_for_subcontractor(subcontractor, release_id):
    """One release, only if it sits on the caller's crew. None otherwise — the caller
    404s, and a sub probing ids off their crew learns nothing (not even "exists")."""
    crew = _crew(subcontractor)
    if not crew:
        return None
    row = _crew_release_query(crew).filter(Releases.id == release_id).first()
    return serialize_release_for_sub(row) if row else None


# A crew name no release can carry. Used so an UNSCOPED account still gets the
# day-row envelope shape (empty rows for the window) instead of a shape the phone
# view would have to special-case — while matching zero rows, never all of them.
_NO_CREW_SENTINEL = '\x00unscoped'

# Card keys the day-schedule builder emits that a subcontractor must not see.
# `notes` is the internal notes cell (the sub-facing notes thread is its own,
# later slice); everything else on the card is already inside SUB_FIELDS' spirit
# (code, project, crew, dates, install hours, stage).
_DAY_CARD_STRIP = ('notes',)


def build_day_schedule_for_subcontractor(subcontractor, days=14, past_days=14):
    """The phone Timeline (days as rows) for exactly this crew.

    Reuses the internal builder with the crew pinned server-side, so a sub can never
    widen the filter by omitting a query param; then strips the internal-only card
    keys. Same cards as the staff calendar, minus what the sub is not shown.
    """
    crew = _crew(subcontractor) or _NO_CREW_SENTINEL
    envelope = build_day_schedule(days=days, past_days=past_days, installer=crew)
    for card in envelope['past_due']:
        for k in _DAY_CARD_STRIP:
            card.pop(k, None)
    for row in envelope['days']:
        for card in row['cards']:
            for k in _DAY_CARD_STRIP:
                card.pop(k, None)
    envelope['window']['installer'] = _crew(subcontractor) or None
    return envelope


# ---------------------------------------------------------------------------
# To-dos: checklist items whose owner is THIS subcontractor account.
# ---------------------------------------------------------------------------

TODO_STATUSES = ('accepted', 'done')


def serialize_todo_for_sub(item):
    """Allowlist projection of a ChecklistItem for its subcontractor owner.

    Deliberately absent: meeting id/title and transcript context, proposed-owner and
    confidence fields, expected_update / brain_update_pending, reviewer. Those are the
    internal review trail; the sub gets the task, its due date, and the release it is
    about.
    """
    rel = item.release
    return {
        'id': item.id,
        'title': item.title,
        'detail': item.detail,
        'item_type': item.item_type,
        'status': item.status,
        'due_date': item.due_date.isoformat() if item.due_date else None,
        'release_id': item.release_id,
        'release_code': f"{rel.job}-{rel.release}" if rel else None,
        'release_job_name': rel.job_name if rel else None,
        'release_description': rel.description if rel else None,
        'created_at': item.created_at.isoformat() if item.created_at else None,
    }


def list_todos_for_subcontractor(subcontractor, status='open'):
    """The sub's own to-dos. status = open (default) | done | all."""
    q = ChecklistItem.query.filter(
        ChecklistItem.owner_subcontractor_id == subcontractor.id,
        ChecklistItem.status.in_(TODO_STATUSES),
    )
    if status == 'open':
        q = q.filter(ChecklistItem.status == 'accepted')
    elif status == 'done':
        q = q.filter(ChecklistItem.status == 'done')
    rows = q.order_by(
        ChecklistItem.due_date.is_(None),
        ChecklistItem.due_date.asc(),
        ChecklistItem.id.desc(),
    ).all()
    return [serialize_todo_for_sub(it) for it in rows]


def set_todo_status_for_subcontractor(subcontractor, item_id, new_status):
    """Mark one of the sub's own to-dos done, or reopen it. Returns the payload or
    None when the item is not theirs (the route 404s — ownership is the lookup)."""
    item = ChecklistItem.query.filter(
        ChecklistItem.id == item_id,
        ChecklistItem.owner_subcontractor_id == subcontractor.id,
        ChecklistItem.status.in_(TODO_STATUSES),
    ).first()
    if not item:
        return None
    if item.status != new_status:
        item.status = new_status
        db.session.commit()
        logger.info("todo_status_changed", item_id=item.id, status=new_status,
                    subcontractor_id=subcontractor.id)
    return serialize_todo_for_sub(item)


# ---------------------------------------------------------------------------
# Notifications: rows addressed to THIS subcontractor account.
# ---------------------------------------------------------------------------

# Keys of Notification.to_dict() a subcontractor may see. Absent on purpose: user_id,
# board_* (internal tracker), submittal_* (Procore), carmen_* (BB review), and the
# drawing_version_comment_id / release_issue_comment_id row pointers that only mean
# something to the staff deep-link router.
_SUB_NOTIFICATION_FIELDS = (
    'id', 'type', 'message', 'is_read', 'created_at', 'excerpt', 'author_name',
    'checklist_item_id', 'release_id', 'release_job_number', 'release_number',
    'release_issue_display_id', 'release_issue_title', 'drawing_version_number',
)


def serialize_notification_for_sub(n):
    d = n.to_dict()
    out = {k: d.get(k) for k in _SUB_NOTIFICATION_FIELDS}
    out['release_code'] = (
        f"{d['release_job_number']}-{d['release_number']}"
        if d.get('release_job_number') and d.get('release_number') else None
    )
    return out


def _sub_notifications(subcontractor):
    return Notification.query.filter(Notification.subcontractor_id == subcontractor.id)


def list_notifications_for_subcontractor(subcontractor, limit=50):
    rows = (_sub_notifications(subcontractor)
            .order_by(Notification.created_at.desc())
            .limit(max(1, min(limit, 200)))
            .all())
    return [serialize_notification_for_sub(n) for n in rows]


def unread_count_for_subcontractor(subcontractor):
    return _sub_notifications(subcontractor).filter(Notification.is_read.is_(False)).count()


def mark_notification_read_for_subcontractor(subcontractor, notification_id):
    n = _sub_notifications(subcontractor).filter(Notification.id == notification_id).first()
    if not n:
        return None
    if not n.is_read:
        n.is_read = True
        db.session.commit()
    return serialize_notification_for_sub(n)


def mark_all_read_for_subcontractor(subcontractor):
    q = _sub_notifications(subcontractor).filter(Notification.is_read.is_(False))
    updated = q.update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    return updated
