"""Service-layer tests for the Release Issue Register: validation, numbering, change
history, mentions, summary math, and the release events that feed Change Log / Activity."""
from decimal import Decimal

import pytest

from app.brain.release_issues import service
from app.brain.release_issues.service import IssueValidationError
from app.models import (
    Notification,
    ReleaseEvents,
    ReleaseIssue,
    ReleaseIssueChange,
    db,
)
from tests.release_issues.conftest import valid_issue_payload


def _events(action=None):
    q = ReleaseEvents.query
    if action:
        q = q.filter(ReleaseEvents.action == action)
    return q.order_by(ReleaseEvents.id).all()


# --- create ----------------------------------------------------------------


@pytest.mark.parametrize('missing', ['title', 'description', 'department', 'category'])
def test_create_requires_core_fields(release, admin, missing):
    with pytest.raises(IssueValidationError):
        service.create_issue(release, valid_issue_payload(**{missing: ''}), admin)
    assert ReleaseIssue.query.count() == 0


def test_create_rejects_values_outside_the_lists(release, admin):
    with pytest.raises(IssueValidationError):
        service.create_issue(release, valid_issue_payload(department='welding'), admin)
    with pytest.raises(IssueValidationError):
        service.create_issue(release, valid_issue_payload(priority='whenever'), admin)


def test_create_numbers_issues_per_release(release, other_release, admin):
    first = service.create_issue(release, valid_issue_payload(), admin)
    second = service.create_issue(release, valid_issue_payload(title='Missing hardware'), admin)
    elsewhere = service.create_issue(other_release, valid_issue_payload(), admin)

    assert (first.seq, second.seq, elsewhere.seq) == (1, 2, 1)
    assert first.display_id == '290-153-I1'
    assert second.display_id == '290-153-I2'
    assert elsewhere.display_id == '410-108-I1'


def test_create_defaults_status_open_and_keeps_original_description(release, admin):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    assert issue.status == 'open'
    assert issue.original_description == issue.description
    assert issue.created_by_name == 'Ada Admin'


@pytest.mark.parametrize('raw', [None, '', '  ', 'TBD', 'unknown'])
def test_blank_cost_is_unknown_not_zero(release, admin, raw):
    issue = service.create_issue(release, valid_issue_payload(estimated_cost=raw), admin)
    assert issue.estimated_cost is None


def test_cost_accepts_currency_formatting_and_rejects_bad_values(release, admin):
    issue = service.create_issue(release, valid_issue_payload(estimated_cost='$1,234.5'), admin)
    assert issue.estimated_cost == Decimal('1234.50')

    with pytest.raises(IssueValidationError):
        service.create_issue(release, valid_issue_payload(estimated_cost='-5'), admin)
    with pytest.raises(IssueValidationError):
        service.create_issue(release, valid_issue_payload(estimated_cost='lots'), admin)


# --- update + history --------------------------------------------------------


def test_update_logs_only_fields_that_actually_changed(release, admin):
    issue = service.create_issue(release, valid_issue_payload(), admin)

    changes = service.update_issue(issue, {
        'status': 'in_progress',
        'priority': 'high',          # unchanged
        'estimated_cost': '1200.00',  # unchanged value, different spelling
    }, admin)

    assert [c.field for c in changes] == ['status']
    row = ReleaseIssueChange.query.one()
    assert (row.old_value, row.new_value) == ('open', 'in_progress')
    assert row.changed_by_name == 'Ada Admin'


def test_noop_update_writes_no_history(release, admin):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    assert service.update_issue(issue, {'status': 'open'}, admin) == []
    assert ReleaseIssueChange.query.count() == 0


def test_cost_edit_keeps_prior_amount_and_unknown(release, admin):
    issue = service.create_issue(release, valid_issue_payload(estimated_cost=''), admin)
    service.update_issue(issue, {'estimated_cost': '850'}, admin)
    service.update_issue(issue, {'estimated_cost': '900.25'}, admin)

    rows = ReleaseIssueChange.query.order_by(ReleaseIssueChange.id).all()
    assert [(r.old_value, r.new_value) for r in rows] == [(None, '850.00'), ('850.00', '900.25')]


def test_description_edit_keeps_original(release, admin):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    service.update_issue(issue, {'description': 'Bent AND scratched.'}, admin)

    assert issue.description == 'Bent AND scratched.'
    assert issue.original_description == 'Stringer arrived bent at the jobsite.'


def test_update_validates_before_writing_anything(release, admin):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    with pytest.raises(IssueValidationError):
        service.update_issue(issue, {'status': 'in_progress', 'title': ''}, admin)
    db.session.refresh(issue)
    assert issue.status == 'open'
    assert ReleaseIssueChange.query.count() == 0


# --- mentions ----------------------------------------------------------------


def test_comment_mention_notifies_with_issue_and_comment_links(release, admin, dave):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    comment = service.add_comment(issue, 'Can you look at this @Dave?', admin)

    notif = Notification.query.one()
    assert notif.user_id == dave.id
    assert notif.release_issue_id == issue.id
    assert notif.release_issue_comment_id == comment.id
    assert notif.message == 'Ada Admin mentioned you on issue 290-153-I1'


def test_description_mention_on_create_notifies(release, admin, dave):
    service.create_issue(release, valid_issue_payload(description='@dave please check'), admin)
    notif = Notification.query.one()
    assert notif.user_id == dave.id
    assert notif.release_issue_comment_id is None


def test_description_edit_notifies_only_newly_added_names(release, admin, dave):
    issue = service.create_issue(release, valid_issue_payload(description='@Dave see this'), admin)
    assert Notification.query.count() == 1

    service.update_issue(issue, {'description': '@Dave see this, updated'}, admin)
    assert Notification.query.count() == 1

    service.update_issue(issue, {'description': '@Dave and @Ada see this'}, admin)
    assert Notification.query.count() == 2
    assert Notification.query.order_by(Notification.id.desc()).first().user_id == admin.id


def test_blank_comment_rejected(release, admin):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    with pytest.raises(IssueValidationError):
        service.add_comment(issue, '   ', admin)


def test_notification_to_dict_carries_issue_context(release, admin, dave):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    service.add_comment(issue, '@Dave heads up', admin)

    data = Notification.query.one().to_dict()
    assert data['release_issue_id'] == issue.id
    assert data['release_issue_display_id'] == '290-153-I1'
    assert data['release_issue_title'] == 'Bent stair stringer'
    assert data['release_id'] == release.id
    assert data['release_job_number'] == 290
    assert data['excerpt'] == '@Dave heads up'
    assert data['author_name'] == 'Ada Admin'


# --- summary -----------------------------------------------------------------


def test_summary_excludes_resolved_and_closed(release, admin):
    open_a = service.create_issue(release, valid_issue_payload(estimated_cost='100'), admin)
    service.create_issue(release, valid_issue_payload(estimated_cost=''), admin)
    done = service.create_issue(release, valid_issue_payload(estimated_cost='5000'), admin)
    closed = service.create_issue(release, valid_issue_payload(estimated_cost='7000'), admin)
    service.update_issue(done, {'status': 'resolved'}, admin)
    service.update_issue(closed, {'status': 'closed'}, admin)
    service.update_issue(open_a, {'status': 'waiting_on_others'}, admin)

    summary = service.summarize(service.list_for_release(release.id))
    assert summary == {
        'total_count': 4,
        'open_count': 2,
        'open_estimated_cost': 100.0,
        'open_unknown_cost_count': 1,
    }


# --- release events (Change Log / Activity) ----------------------------------


def test_create_writes_one_labeled_release_event(release, admin):
    issue = service.create_issue(release, valid_issue_payload(), admin)

    (event,) = _events()
    assert event.action == 'create_issue'
    assert (event.job, event.release) == (290, '153')
    assert event.internal_user_id == admin.id
    assert event.applied_at is not None
    assert event.payload['from'] is None
    assert event.payload['to'] == {
        'issue_id': issue.id,
        'display_id': '290-153-I1',
        'title': 'Bent stair stringer',
        'department': 'Fab',
        'category': 'Damage',
        'priority': 'High',
        'estimated_cost': '1200.00',
    }


def test_update_event_uses_labels_and_omits_description_text(release, admin):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    service.update_issue(issue, {
        'status': 'in_progress',
        'department': 'ship_install',
        'description': 'Secret long text',
    }, admin)

    (event,) = _events('update_issue')
    changes = {c['field']: c for c in event.payload['to']['changes']}
    assert changes['status'] == {'field': 'status', 'from': 'Open', 'to': 'In Progress'}
    assert changes['department'] == {'field': 'department', 'from': 'Fab', 'to': 'Ship/Install'}
    assert changes['description'] == {'field': 'description', 'from': None, 'to': None}


def test_noop_update_and_comments_write_no_release_event(release, admin):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    service.update_issue(issue, {'priority': 'high'}, admin)
    service.add_comment(issue, 'Just a note', admin)
    assert [e.action for e in _events()] == ['create_issue']


def test_attachment_writes_release_event(release, admin, storage_root):
    issue = service.create_issue(release, valid_issue_payload(), admin)
    service.add_attachment(
        issue, file_bytes=b'%PDF-1.4 test', filename='rework.pdf',
        mime_type='application/pdf', user=admin,
    )

    (event,) = _events('add_issue_attachment')
    assert event.payload['to']['filename'] == 'rework.pdf'
    assert event.payload['to']['is_pdf'] is True
    assert event.payload['to']['display_id'] == '290-153-I1'


def test_attachment_rejects_comment_from_another_issue(release, admin, storage_root):
    a = service.create_issue(release, valid_issue_payload(), admin)
    b = service.create_issue(release, valid_issue_payload(title='Other'), admin)
    comment_on_b = service.add_comment(b, 'on B', admin)

    with pytest.raises(IssueValidationError):
        service.add_attachment(
            a, file_bytes=b'%PDF-1.4', filename='x.pdf', mime_type='application/pdf',
            user=admin, comment_id=comment_on_b.id,
        )
