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
  list_activity_for_subcontractor: One crew release's Activity rows (SUB_ACTIVITY_ACTIONS only)
  add_note_for_subcontractor: Post a note to a crew release's thread, attributed "sub:<id>"
  list_attachments_for_subcontractor / resolve_drawing_file_for_subcontractor /
    resolve_photo_file_for_subcontractor: The attachments reader
  upload_photo_for_subcontractor: Attach a photo to a crew release, uploader = the account
  upload_file_for_subcontractor: Attach a PDF as the next drawing version, uploader = the account
  SUB_STAGES / set_stage_for_subcontractor: Field-side stage changes through UpdateStageCommand
imports_from: [app.models, app.brain.job_log.utils, app.brain.install_schedule.service,
  app.brain.job_log.features.notes.command, app.brain.job_log.features.splice.command, app.logging_config]
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

from app.brain.install_schedule.service import build_day_schedule, build_month_schedule
from app.brain.job_log.utils import serialize_value
from app.logging_config import get_logger
from app.models import (
    ChecklistItem, Notification, ReleaseDrawingVersion, ReleaseEvents, ReleasePhoto,
    Releases, Subcontractor, User, db,
)

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


def build_day_schedule_for_subcontractor(subcontractor, days=14, past_days=14, month=None):
    """The phone Timeline (days as rows) for exactly this crew.

    Reuses the internal builder with the crew pinned server-side, so a sub can never
    widen the filter by omitting a query param; then strips the internal-only card
    keys. Same cards as the staff calendar, minus what the sub is not shown.
    `month` ("YYYY-MM") switches to the one-month window (the phone's month filter).
    """
    crew = _crew(subcontractor) or _NO_CREW_SENTINEL
    if month:
        year, mon = (int(p) for p in month.split('-', 1))
        envelope = build_month_schedule(year, mon, installer=crew)
    else:
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


# A to-do is "unread" while its assignment / deadline ping is unread; a mention is
# unread while its row is. The tab badge is the sum; the To-Dos page clears the to-do
# pings when that segment is shown and mentions one tap at a time.
TODO_NOTIFICATION_TYPES = ('checklist_assigned', 'checklist_due')
MENTION_NOTIFICATION_TYPES = ('mention',)


def unread_count_for_subcontractor(subcontractor):
    """{unread_count, unread_todos, unread_mentions} — one round trip for the badges."""
    rows = (_sub_notifications(subcontractor)
            .filter(Notification.is_read.is_(False))
            .with_entities(Notification.type)
            .all())
    todos = sum(1 for (t,) in rows if t in TODO_NOTIFICATION_TYPES)
    mentions = sum(1 for (t,) in rows if t in MENTION_NOTIFICATION_TYPES)
    return {'unread_count': len(rows), 'unread_todos': todos, 'unread_mentions': mentions}


def mark_notification_read_for_subcontractor(subcontractor, notification_id):
    n = _sub_notifications(subcontractor).filter(Notification.id == notification_id).first()
    if not n:
        return None
    if not n.is_read:
        n.is_read = True
        db.session.commit()
    return serialize_notification_for_sub(n)


def mark_all_read_for_subcontractor(subcontractor, types=None):
    """Mark the sub's unread rows read; `types` narrows the sweep (e.g. just the to-do
    pings when the To-Dos segment is viewed, leaving mentions unread)."""
    q = _sub_notifications(subcontractor).filter(Notification.is_read.is_(False))
    if types:
        q = q.filter(Notification.type.in_(list(types)))
    updated = q.update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    return updated


# ---------------------------------------------------------------------------
# Release page: Activity, notes, attachments (read-only reader).
# ---------------------------------------------------------------------------

def _crew_release_row(subcontractor, release_id):
    crew = _crew(subcontractor)
    if not crew:
        return None
    return _crew_release_query(crew).filter(Releases.id == release_id).first()


# Event actions a subcontractor's Activity tab may show. The staff rail's
# ACTIVITY_ACTIONS minus fab-order (shop sequencing) and the issue register
# (staff-only); plus the notes thread. Blocked by never being served, not by a
# hidden tab (ROADMAP T3 2026-09-07: Activity yes, Changelog never).
SUB_ACTIVITY_ACTIONS = (
    'update_notes', 'update_stage', 'update_ship_date', 'update_start_install',
    'clear_hard_date', 'update_installer', 'update_num_guys',
    'upload_photo', 'delete_photo', 'upload_drawing', 'save_drawing_version',
    'delete_drawing_version',
)

SUB_ACTOR_PREFIX = 'sub:'


def _actor_names(events):
    """{event.id: (name, kind)} for staff (users) and subcontractor ("sub:<id>") actors."""
    uids = {e.internal_user_id for e in events if e.internal_user_id}
    sids = set()
    for e in events:
        ext = e.external_user_id or ''
        if ext.startswith(SUB_ACTOR_PREFIX) and ext[len(SUB_ACTOR_PREFIX):].isdigit():
            sids.add(int(ext[len(SUB_ACTOR_PREFIX):]))
    users = {u.id: u for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}
    subs = {s.id: s for s in Subcontractor.query.filter(Subcontractor.id.in_(sids)).all()} if sids else {}
    out = {}
    for e in events:
        if e.internal_user_id and e.internal_user_id in users:
            u = users[e.internal_user_id]
            name = f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or u.username
            out[e.id] = (name, 'staff')
            continue
        ext = e.external_user_id or ''
        if ext.startswith(SUB_ACTOR_PREFIX) and ext[len(SUB_ACTOR_PREFIX):].isdigit():
            sub = subs.get(int(ext[len(SUB_ACTOR_PREFIX):]))
            if sub:
                out[e.id] = (sub.contact_name, 'sub')
                continue
        out[e.id] = (None, 'system')
    return out


def list_activity_for_subcontractor(subcontractor, release_id, limit=200):
    """Activity rows for one crew release, newest first, in the shape the shared
    buildTimeline() transform reads (action / payload / source / user_name / created_at).
    None when the release is not on the caller's crew."""
    from app.datetime_utils import format_datetime_mountain
    release = _crew_release_row(subcontractor, release_id)
    if release is None:
        return None
    events = (ReleaseEvents.query
              .filter(ReleaseEvents.job == release.job,
                      ReleaseEvents.release == release.release,
                      ReleaseEvents.action.in_(SUB_ACTIVITY_ACTIONS),
                      ReleaseEvents.is_system_echo.is_(False))
              .order_by(ReleaseEvents.created_at.desc())
              .limit(max(1, min(limit, 500)))
              .all())
    names = _actor_names(events)
    rows = []
    for e in events:
        name, kind = names[e.id]
        rows.append({
            'id': e.id,
            'action': e.action,
            'payload': e.payload,
            'source': e.source,
            'user_name': name,
            'actor_kind': kind,
            'created_at': format_datetime_mountain(e.created_at),
        })
    return rows


def add_note_for_subcontractor(subcontractor, release_id, text):
    """Post a note to a crew release's thread via the ONE writer of Releases.notes
    (UpdateNotesCommand), attributed to the account as external_user_id "sub:<id>".
    Returns (event_id, notes) or None when off-crew; raises ValueError on an empty
    body or a dedup hit, exactly like the staff route."""
    from app.brain.job_log.features.notes.command import UpdateNotesCommand
    release = _crew_release_row(subcontractor, release_id)
    if release is None:
        return None
    body = (text or '').strip()
    if not body:
        raise ValueError('Note is empty')
    result = UpdateNotesCommand(
        job_id=release.job, release=release.release, notes=body,
        source='Brain', source_of_update='Brain:sub',
        external_user_id=f'{SUB_ACTOR_PREFIX}{subcontractor.id}',
    ).execute()
    logger.info("sub_note_posted", release_id=release.id, job=release.job,
                release=release.release, subcontractor_id=subcontractor.id, event_id=result.event_id)
    return result.event_id, result.notes


def _uploader_name(row):
    if getattr(row, 'uploaded_by_subcontractor_id', None):
        s = row.uploaded_by_subcontractor
        return s.contact_name if s else None
    u = row.uploaded_by
    if not u:
        return None
    return f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or u.username


def list_attachments_for_subcontractor(subcontractor, release_id):
    """Drawings (the release family's versions, newest first, current flagged) and photos
    for one crew release. Allowlisted: no storage keys, no markup/comment internals.
    None when off-crew."""
    from app.brain.job_log.features.splice.command import release_family
    release = _crew_release_row(subcontractor, release_id)
    if release is None:
        return None
    members = release_family(release)
    if release not in members:
        members.append(release)
    order = {r.id: i for i, r in enumerate(members)}
    labels = {r.id: f"{r.job}-{r.release}" for r in members}

    versions = (ReleaseDrawingVersion.query
                .filter(ReleaseDrawingVersion.release_id.in_(list(order)),
                        ReleaseDrawingVersion.is_deleted.is_(False))
                .all())
    versions.sort(key=lambda v: (order[v.release_id], -v.version_number))
    latest = {}
    for v in versions:
        latest.setdefault(v.release_id, v.version_number)
    drawings = [{
        'id': v.id,
        'release_id': v.release_id,
        'release_label': labels[v.release_id],
        'version_number': v.version_number,
        'is_current': v.version_number == latest[v.release_id],
        'original_filename': v.original_filename,
        'file_size_bytes': v.file_size_bytes,
        'uploaded_at': v.uploaded_at.isoformat() if v.uploaded_at else None,
        'uploaded_by_name': _uploader_name(v),
        'note': v.note,
    } for v in versions]

    photos = (ReleasePhoto.query
              .filter(ReleasePhoto.release_id == release.id, ReleasePhoto.is_deleted.is_(False))
              .order_by(ReleasePhoto.uploaded_at.desc(), ReleasePhoto.id.desc())
              .all())
    photo_rows = [{
        'id': p.id,
        'original_filename': p.original_filename,
        'mime_type': p.mime_type,
        'file_size_bytes': p.file_size_bytes,
        'note': p.note,
        'stage': p.stage,
        'uploaded_at': p.uploaded_at.isoformat() if p.uploaded_at else None,
        'uploaded_by_name': _uploader_name(p),
    } for p in photos]
    return {'release_id': release.id, 'drawings': drawings, 'photos': photo_rows}


def resolve_drawing_file_for_subcontractor(subcontractor, release_id, version_id):
    """The ReleaseDrawingVersion row a sub may stream, or None (off-crew, off-family,
    deleted, unknown — all indistinguishable to the caller)."""
    from app.brain.job_log.features.splice.command import release_family
    release = _crew_release_row(subcontractor, release_id)
    if release is None:
        return None
    version = db.session.get(ReleaseDrawingVersion, version_id)
    if not version or version.is_deleted:
        return None
    family_ids = {r.id for r in release_family(release)} | {release.id}
    return version if version.release_id in family_ids else None


def resolve_photo_file_for_subcontractor(subcontractor, release_id, photo_id):
    release = _crew_release_row(subcontractor, release_id)
    if release is None:
        return None
    photo = db.session.get(ReleasePhoto, photo_id)
    if not photo or photo.is_deleted or photo.release_id != release.id:
        return None
    return photo


def upload_photo_for_subcontractor(subcontractor, release_id, file_bytes, filename, mime_type, note=None):
    """Attach an image to a crew release with the account as uploader. None when
    off-crew; ValueError when the bytes are not an image."""
    from app.brain.job_log.features.photos.command import UploadPhotoCommand
    from app.brain.job_log.features.photos.payloads import is_probably_image, sniff_image_mime
    release = _crew_release_row(subcontractor, release_id)
    if release is None:
        return None
    if not is_probably_image(file_bytes, mime_type or '', filename or ''):
        raise ValueError('File must be an image')
    resolved = sniff_image_mime(file_bytes) or (mime_type if (mime_type or '').startswith('image/') else 'image/jpeg')
    photo = UploadPhotoCommand(
        release_id=release.id, file_bytes=file_bytes, filename=filename or None,
        mime_type=resolved, uploaded_by_user_id=None, note=(note or '').strip() or None,
        uploaded_by_subcontractor_id=subcontractor.id,
    ).execute()
    logger.info("sub_photo_uploaded", release_id=release.id, photo_id=photo.id,
                subcontractor_id=subcontractor.id)
    return {
        'id': photo.id, 'original_filename': photo.original_filename, 'mime_type': photo.mime_type,
        'file_size_bytes': photo.file_size_bytes, 'note': photo.note, 'stage': photo.stage,
        'uploaded_at': photo.uploaded_at.isoformat() if photo.uploaded_at else None,
        'uploaded_by_name': subcontractor.contact_name,
    }


# Stages a subcontractor may set from the field: the post-shipping / installation
# stages, in workflow order. Shop stages (fabrication, paint, shipping holds) stay
# staff-only — a crew reports what happened on site, it does not sequence the shop.
SUB_STAGES = ('Ship Complete', 'Install Start', 'Install Complete', 'Complete')


def set_stage_for_subcontractor(subcontractor, release_id, stage):
    """Change a crew release's stage through UpdateStageCommand (all cascades: job_comp,
    fab-order tier, Trello move, scheduling) attributed "sub:<id>". None when
    off-crew; ValueError for a stage outside SUB_STAGES or a dedup hit."""
    from app.brain.job_log.features.stage.command import UpdateStageCommand
    release = _crew_release_row(subcontractor, release_id)
    if release is None:
        return None
    stage = (stage or '').strip()
    if stage not in SUB_STAGES:
        raise ValueError(f"'{stage}' is not a stage you can set from the field")
    result = UpdateStageCommand(
        job_id=release.job, release=release.release, stage=stage,
        source='Brain', source_of_update='Brain:sub',
        external_user_id=f'{SUB_ACTOR_PREFIX}{subcontractor.id}',
    ).execute()
    logger.info("sub_stage_changed", release_id=release.id, job=release.job, release=release.release,
                to_stage=stage, subcontractor_id=subcontractor.id, event_id=result.event_id)
    return result


def upload_file_for_subcontractor(subcontractor, release_id, file_bytes, filename, mime_type, note=None):
    """Attach a PDF to a crew release as its next drawing version — the same thing the
    staff hub's Upload does — with the account as uploader. A release with no drawing
    yet gets v1; otherwise v(N+1) derived from the current latest. None when off-crew;
    ValueError when the bytes are not a PDF."""
    from app.brain.job_log.features.pdf_markup.command import (
        SaveDrawingVersionCommand, UploadInitialDrawingCommand,
    )
    from app.brain.job_log.features.pdf_markup.payloads import is_pdf_bytes
    release = _crew_release_row(subcontractor, release_id)
    if release is None:
        return None
    if not is_pdf_bytes(file_bytes):
        raise ValueError('File must be a PDF or an image')
    latest = (ReleaseDrawingVersion.query
              .filter(ReleaseDrawingVersion.release_id == release.id)
              .order_by(ReleaseDrawingVersion.version_number.desc())
              .first())
    note = (note or '').strip() or f'Uploaded from the field by {subcontractor.contact_name}'
    if latest is None:
        version = UploadInitialDrawingCommand(
            release_id=release.id, file_bytes=file_bytes, filename=filename or None,
            mime_type='application/pdf', uploaded_by_user_id=None, note=note,
            uploaded_by_subcontractor_id=subcontractor.id,
        ).execute()
    else:
        version = SaveDrawingVersionCommand(
            release_id=release.id, file_bytes=file_bytes, uploaded_by_user_id=None,
            source_version_id=latest.id, note=note,
            uploaded_by_subcontractor_id=subcontractor.id,
        ).execute()
        if filename and not version.original_filename:
            version.original_filename = filename
            db.session.commit()
    logger.info("sub_file_uploaded", release_id=release.id, version_id=version.id,
                version=version.version_number, subcontractor_id=subcontractor.id)
    return {
        'id': version.id, 'release_id': version.release_id, 'version_number': version.version_number,
        'original_filename': version.original_filename, 'file_size_bytes': version.file_size_bytes,
        'uploaded_at': version.uploaded_at.isoformat() if version.uploaded_at else None,
        'uploaded_by_name': subcontractor.contact_name, 'note': version.note,
    }
