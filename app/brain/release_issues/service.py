"""Write and read logic for the Release Issue Register.

Routes stay thin: they parse the request, call in here, and serialize. Every
tracked field edit writes a ReleaseIssueChange row in the same commit as the
edit, so the history can never disagree with the record.

Creating an issue, editing it, and attaching evidence also write a ReleaseEvents
row on the release (actions create_issue / update_issue / add_issue_attachment),
so the release hub's Change Log and Activity rail show them. Comments stay on the
issue's own timeline. Payloads nest an object under `to` with `from` None, the same
shape as upload_photo, so the from/to diff renderers never treat them as a no-op.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func

from app.brain.mentions import parse_mentions, resolve_mentioned_users, user_display_name
from app.brain.release_issues import constants as C
from app.brain.release_issues.storage import extension_for_mime, save_attachment
from app.logging_config import get_logger
from app.services.job_event_service import JobEventService
from app.models import (
    Notification,
    ReleaseIssue,
    ReleaseIssueAttachment,
    ReleaseIssueChange,
    ReleaseIssueComment,
    db,
)

logger = get_logger(__name__)

# Fields whose edits land in the change history, in display order.
TRACKED_FIELDS = (
    'title', 'description', 'department', 'category', 'priority', 'status', 'estimated_cost',
)


class IssueValidationError(ValueError):
    """Bad input from the client — the route turns it into a 400."""


def _parse_cost(value):
    """'' / None / 'unknown' → None (Unknown/TBD); otherwise a non-negative Decimal."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace('$', '').replace(',', '')
        if value == '' or value.lower() in ('unknown', 'tbd'):
            return None
    try:
        cost = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise IssueValidationError('Estimated cost must be a number or left blank (Unknown/TBD)')
    if cost < 0:
        raise IssueValidationError('Estimated cost cannot be negative')
    return cost


def _require_choice(value, allowed, label):
    value = (value or '').strip()
    if value not in allowed:
        raise IssueValidationError(f'{label} is required and must be one of the listed options')
    return value


def _clean_title(value):
    title = (value or '').strip()
    if not title:
        raise IssueValidationError('Title is required')
    if len(title) > C.TITLE_MAX:
        raise IssueValidationError(f'Title must be {C.TITLE_MAX} characters or fewer')
    return title


def _clean_description(value):
    description = (value or '').strip()
    if not description:
        raise IssueValidationError('Description is required')
    return description


def _as_text(field, value):
    if value is None:
        return None
    if field == 'estimated_cost':
        return f'{value:.2f}'
    return str(value)


def _notify_mentions(names, *, message, issue, comment=None):
    users = resolve_mentioned_users(names)
    for user in users:
        db.session.add(Notification(
            user_id=user.id,
            type='mention',
            message=message,
            release_issue_id=issue.id,
            release_issue_comment_id=comment.id if comment else None,
        ))
    return len(users)


def _record_release_event(issue, action, user, detail):
    """Write the release-level event in the caller's transaction (commit is the caller's)."""
    release = issue.release
    JobEventService.create_and_close(
        job=release.job,
        release=release.release,
        action=action,
        source='Brain',
        internal_user_id=user.id,
        payload={
            'from': None,
            'to': {'issue_id': issue.id, 'display_id': issue.display_id, 'title': issue.title, **detail},
        },
    )


def summarize(issues):
    """Open count + total known estimated cost across a list of issues."""
    open_issues = [i for i in issues if i.status not in C.CLOSED_STATUSES]
    open_cost = sum((i.estimated_cost for i in open_issues if i.estimated_cost is not None), Decimal('0'))
    return {
        'total_count': len(issues),
        'open_count': len(open_issues),
        'open_estimated_cost': float(open_cost),
        'open_unknown_cost_count': sum(1 for i in open_issues if i.estimated_cost is None),
    }


def list_for_release(release_id):
    return (ReleaseIssue.query
            .filter(ReleaseIssue.release_id == release_id)
            .order_by(ReleaseIssue.seq.desc())
            .all())


def create_issue(release, data, user):
    title = _clean_title(data.get('title'))
    description = _clean_description(data.get('description'))
    department = _require_choice(data.get('department'), C.DEPARTMENT_KEYS, 'Department')
    category = _require_choice(data.get('category'), C.CATEGORY_KEYS, 'Category')
    priority = _require_choice(data.get('priority') or 'normal', C.PRIORITY_KEYS, 'Priority')
    estimated_cost = _parse_cost(data.get('estimated_cost'))

    author_name = user_display_name(user)
    next_seq = (db.session.query(func.max(ReleaseIssue.seq))
                .filter(ReleaseIssue.release_id == release.id)
                .scalar() or 0) + 1
    now = datetime.utcnow()

    issue = ReleaseIssue(
        release_id=release.id,
        seq=next_seq,
        title=title,
        description=description,
        original_description=description,
        department=department,
        category=category,
        priority=priority,
        status='open',
        estimated_cost=estimated_cost,
        created_by_user_id=user.id,
        created_by_name=author_name,
        created_at=now,
        updated_at=now,
    )
    db.session.add(issue)
    db.session.flush()

    _record_release_event(issue, 'create_issue', user, {
        'department': C.value_label('department', department),
        'category': C.value_label('category', category),
        'priority': C.value_label('priority', priority),
        'estimated_cost': _as_text('estimated_cost', estimated_cost),
    })
    mentioned = _notify_mentions(
        parse_mentions(description),
        message=f'{author_name} mentioned you on issue {issue.display_id}',
        issue=issue,
    )
    db.session.commit()

    logger.info(
        'release_issue_created',
        release_issue_id=issue.id, release_id=release.id, job=release.job,
        release=release.release, department=department, category=category,
        priority=priority, user_id=user.id, mentions=mentioned,
    )
    return issue


def update_issue(issue, data, user):
    """Apply a partial edit. Returns the list of ReleaseIssueChange rows written."""
    proposed = {}
    if 'title' in data:
        proposed['title'] = _clean_title(data.get('title'))
    if 'description' in data:
        proposed['description'] = _clean_description(data.get('description'))
    if 'department' in data:
        proposed['department'] = _require_choice(data.get('department'), C.DEPARTMENT_KEYS, 'Department')
    if 'category' in data:
        proposed['category'] = _require_choice(data.get('category'), C.CATEGORY_KEYS, 'Category')
    if 'priority' in data:
        proposed['priority'] = _require_choice(data.get('priority'), C.PRIORITY_KEYS, 'Priority')
    if 'status' in data:
        proposed['status'] = _require_choice(data.get('status'), C.STATUS_KEYS, 'Status')
    if 'estimated_cost' in data:
        proposed['estimated_cost'] = _parse_cost(data.get('estimated_cost'))

    author_name = user_display_name(user)
    now = datetime.utcnow()
    changes = []
    old_description = issue.description

    for field in TRACKED_FIELDS:
        if field not in proposed:
            continue
        old, new = getattr(issue, field), proposed[field]
        if old == new:
            continue
        setattr(issue, field, new)
        change = ReleaseIssueChange(
            issue_id=issue.id,
            field=field,
            old_value=_as_text(field, old),
            new_value=_as_text(field, new),
            changed_by_user_id=user.id,
            changed_by_name=author_name,
            changed_at=now,
        )
        db.session.add(change)
        changes.append(change)

    if not changes:
        return []

    issue.updated_at = now
    _record_release_event(issue, 'update_issue', user, {
        'changes': [
            # Long text is not copied into the release log; the issue history keeps it.
            {'field': c.field, 'from': None, 'to': None} if c.field == 'description'
            else {'field': c.field,
                  'from': C.value_label(c.field, c.old_value),
                  'to': C.value_label(c.field, c.new_value)}
            for c in changes
        ],
    })
    # A description edit notifies only names that were not already mentioned.
    if 'description' in proposed and proposed['description'] != old_description:
        added = parse_mentions(proposed['description']) - parse_mentions(old_description)
        _notify_mentions(
            added,
            message=f'{author_name} mentioned you on issue {issue.display_id}',
            issue=issue,
        )
    db.session.commit()

    logger.info(
        'release_issue_updated',
        release_issue_id=issue.id, release_id=issue.release_id,
        fields=[c.field for c in changes], status=issue.status, user_id=user.id,
    )
    return changes


def add_comment(issue, body, user):
    body = (body or '').strip()
    if not body:
        raise IssueValidationError('Comment body is required')

    author_name = user_display_name(user)
    comment = ReleaseIssueComment(
        issue_id=issue.id,
        release_id=issue.release_id,
        body=body,
        author_id=user.id,
        author_name=author_name,
    )
    db.session.add(comment)
    issue.updated_at = datetime.utcnow()
    db.session.flush()

    mentioned = _notify_mentions(
        parse_mentions(body),
        message=f'{author_name} mentioned you on issue {issue.display_id}',
        issue=issue,
        comment=comment,
    )
    db.session.commit()

    logger.info(
        'release_issue_comment_added',
        release_issue_id=issue.id, release_id=issue.release_id,
        comment_id=comment.id, user_id=user.id, mentions=mentioned,
    )
    return comment


def add_attachment(issue, *, file_bytes, filename, mime_type, user, comment_id=None):
    if comment_id is not None:
        comment = db.session.get(ReleaseIssueComment, comment_id)
        if not comment or comment.issue_id != issue.id:
            raise IssueValidationError('Comment does not belong to this issue')

    attachment = ReleaseIssueAttachment(
        issue_id=issue.id,
        comment_id=comment_id,
        storage_key='pending',
        original_filename=(filename or None) and filename[:256],
        mime_type=mime_type,
        file_size_bytes=len(file_bytes),
        uploaded_by_user_id=user.id,
        uploaded_by_name=user_display_name(user),
    )
    db.session.add(attachment)
    db.session.flush()

    try:
        attachment.storage_key = save_attachment(
            issue.id, f'{attachment.id}{extension_for_mime(mime_type)}', file_bytes,
        )
    except Exception:
        db.session.rollback()
        logger.error(
            'release_issue_attachment_write_failed',
            release_issue_id=issue.id, user_id=user.id, exc_info=True,
        )
        raise

    issue.updated_at = datetime.utcnow()
    _record_release_event(issue, 'add_issue_attachment', user, {
        'filename': attachment.original_filename,
        'is_pdf': mime_type == 'application/pdf',
    })
    db.session.commit()

    logger.info(
        'release_issue_attachment_added',
        release_issue_id=issue.id, attachment_id=attachment.id,
        mime_type=mime_type, file_size_bytes=attachment.file_size_bytes, user_id=user.id,
    )
    return attachment


def detail(issue):
    """Issue plus its comments, attachments and change history (oldest first)."""
    comments = issue.comments.order_by(ReleaseIssueComment.created_at.asc(), ReleaseIssueComment.id.asc()).all()
    attachments = (issue.attachments
                   .filter(ReleaseIssueAttachment.is_deleted.is_(False))
                   .order_by(ReleaseIssueAttachment.uploaded_at.asc(), ReleaseIssueAttachment.id.asc())
                   .all())
    changes = issue.changes.order_by(ReleaseIssueChange.changed_at.asc(), ReleaseIssueChange.id.asc()).all()
    return {
        'issue': issue.to_dict(),
        'comments': [c.to_dict() for c in comments],
        'attachments': [a.to_dict() for a in attachments],
        'changes': [c.to_dict() for c in changes],
    }
