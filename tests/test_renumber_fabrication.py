"""
Tests for renumber_fabrication_fab_orders — the admin-triggered Job Log cascade
that compresses FABRICATION-group fab_orders to a contiguous 3..N block.
"""
import pytest
from unittest.mock import patch

from app.models import Releases, ReleaseEvents, TrelloOutbox, db
from app.brain.job_log.features.fab_order.renumber_fabrication import (
    renumber_fabrication_fab_orders,
)


@pytest.fixture(autouse=True)
def setup_auth(mock_admin_user):
    with patch('app.auth.utils.get_current_user', return_value=mock_admin_user):
        yield


def make_release(job, release, stage, stage_group, fab_order, trello_card_id=None, job_name="Test"):
    r = Releases(
        job=job,
        release=release,
        job_name=job_name,
        stage=stage,
        stage_group=stage_group,
        fab_order=fab_order,
        trello_card_id=trello_card_id,
    )
    db.session.add(r)
    db.session.flush()
    return r


def test_compresses_drifted_fabrication_fab_orders(app):
    """FABRICATION rows with drifted values (20, 25, 30, 40) compress to (3, 4, 5, 6)
    preserving relative order."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 20)
        make_release(2, "A", "Cut start", "FABRICATION", 25)
        make_release(3, "A", "Fit Up Complete.", "FABRICATION", 30)
        make_release(4, "A", "Weld Complete", "FABRICATION", 40)
        db.session.commit()

        result = renumber_fabrication_fab_orders()

        assert result['changed'] == 4
        assert result['unchanged'] == 0
        assert result['total_fabrication'] == 4

        # Order preserved: 20 < 25 < 30 < 40 → 3 < 4 < 5 < 6
        assert Releases.query.filter_by(job=1, release="A").first().fab_order == 3
        assert Releases.query.filter_by(job=2, release="A").first().fab_order == 4
        assert Releases.query.filter_by(job=3, release="A").first().fab_order == 5
        assert Releases.query.filter_by(job=4, release="A").first().fab_order == 6


def test_does_not_touch_non_fabrication_rows(app):
    """Welded QC, Paint Start, fixed-tier, and Complete rows are untouched."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 50)
        make_release(2, "A", "Welded QC", "READY_TO_SHIP", 3)
        make_release(3, "A", "Paint Start", "READY_TO_SHIP", 4)
        make_release(4, "A", "Shipping completed", "COMPLETE", 1)
        make_release(5, "A", "Paint complete", "READY_TO_SHIP", 2)
        make_release(6, "A", "Complete", "COMPLETE", None)
        db.session.commit()

        renumber_fabrication_fab_orders()

        assert Releases.query.filter_by(job=1).first().fab_order == 3  # FAB compressed
        assert Releases.query.filter_by(job=2).first().fab_order == 3  # Welded QC untouched
        assert Releases.query.filter_by(job=3).first().fab_order == 4  # Paint Start untouched
        assert Releases.query.filter_by(job=4).first().fab_order == 1  # Shipping untouched
        assert Releases.query.filter_by(job=5).first().fab_order == 2  # Paint complete untouched
        assert Releases.query.filter_by(job=6).first().fab_order is None  # Complete untouched


def test_dry_run_does_not_commit(app):
    """dry_run=True returns the change list but rolls back; no events created."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 20)
        make_release(2, "A", "Cut start", "FABRICATION", 25)
        db.session.commit()

        events_before = ReleaseEvents.query.count()

        result = renumber_fabrication_fab_orders(dry_run=True)

        assert result['changed'] == 2
        assert len(result['changes']) == 2

        assert Releases.query.filter_by(job=1).first().fab_order == 20
        assert Releases.query.filter_by(job=2).first().fab_order == 25
        assert ReleaseEvents.query.count() == events_before


def test_no_trello_outbox_queued(app):
    """Renumber is audit-only: no Trello outbox items are queued (sandbox has no board)."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 20, trello_card_id="abc123")
        make_release(2, "A", "Cut start", "FABRICATION", 25, trello_card_id=None)
        db.session.commit()

        renumber_fabrication_fab_orders()

        outbox_items = TrelloOutbox.query.filter_by(
            destination='trello', action='update_fab_order'
        ).all()
        assert len(outbox_items) == 0


def test_idempotent(app):
    """Running renumber twice produces zero changes the second time."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 50)
        make_release(2, "A", "Cut start", "FABRICATION", 60)
        db.session.commit()

        renumber_fabrication_fab_orders()
        result2 = renumber_fabrication_fab_orders()

        assert result2['changed'] == 0
        assert result2['unchanged'] == 2


def test_excludes_archived_and_inactive(app):
    """Archived or soft-deleted releases are excluded from the renumber set."""
    with app.app_context():
        active = Releases(
            job=1, release="A", job_name="T", stage="Released",
            stage_group="FABRICATION", fab_order=20,
            is_active=True, is_archived=False,
        )
        archived = Releases(
            job=2, release="A", job_name="T", stage="Released",
            stage_group="FABRICATION", fab_order=21,
            is_active=True, is_archived=True,
        )
        inactive = Releases(
            job=3, release="A", job_name="T", stage="Released",
            stage_group="FABRICATION", fab_order=22,
            is_active=False, is_archived=False,
        )
        db.session.add_all([active, archived, inactive])
        db.session.commit()

        result = renumber_fabrication_fab_orders()

        assert result['total_fabrication'] == 1
        assert Releases.query.filter_by(job=1).first().fab_order == 3
        assert Releases.query.filter_by(job=2).first().fab_order == 21  # untouched
        assert Releases.query.filter_by(job=3).first().fab_order == 22  # untouched


def test_duplicate_fab_orders_compress_to_same_slot(app):
    """Releases sharing the same current fab_order share the same new value
    and consume only one slot in the compressed sequence."""
    with app.app_context():
        # Three rows tied at 12 should all become the same new value;
        # next distinct group bumps to the next slot.
        make_release(1, "A", "Released", "FABRICATION", 5)
        make_release(2, "A", "Cut start", "FABRICATION", 12)
        make_release(3, "A", "Cut start", "FABRICATION", 12)
        make_release(4, "A", "Cut start", "FABRICATION", 12)
        make_release(5, "A", "Fit Up Complete.", "FABRICATION", 18)
        db.session.commit()

        renumber_fabrication_fab_orders()

        # 5 → 3, the three 12s → 4, 18 → 5
        assert Releases.query.filter_by(job=1).first().fab_order == 3
        assert Releases.query.filter_by(job=2).first().fab_order == 4
        assert Releases.query.filter_by(job=3).first().fab_order == 4
        assert Releases.query.filter_by(job=4).first().fab_order == 4
        assert Releases.query.filter_by(job=5).first().fab_order == 5


def test_default_fab_order_placeholder_is_preserved(app):
    """Releases at DEFAULT_FAB_ORDER (80.555) are 'no position yet' — preserve them
    and don't consume sequence slots."""
    from app.api.helpers import DEFAULT_FAB_ORDER

    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 20)
        make_release(2, "A", "Cut start", "FABRICATION", 25)
        make_release(3, "A", "Released", "FABRICATION", DEFAULT_FAB_ORDER)
        make_release(4, "A", "Released", "FABRICATION", DEFAULT_FAB_ORDER)
        db.session.commit()

        result = renumber_fabrication_fab_orders()

        # Only the two non-placeholder rows should be renumbered, but totals
        # reflect the full FABRICATION set so the modal lines up with the
        # frontend Fab filter view.
        assert result['changed'] == 2
        assert result['placeholder_preserved'] == 2
        assert result['unchanged'] == 2  # the 2 placeholder rows
        assert result['total_fabrication'] == 4
        assert Releases.query.filter_by(job=1).first().fab_order == 3
        assert Releases.query.filter_by(job=2).first().fab_order == 4
        # Placeholders untouched
        assert Releases.query.filter_by(job=3).first().fab_order == DEFAULT_FAB_ORDER
        assert Releases.query.filter_by(job=4).first().fab_order == DEFAULT_FAB_ORDER


def test_changes_payload_includes_from_to(app):
    """The returned changes list contains job, release, stage, from, to."""
    with app.app_context():
        make_release(1, "A", "Released", "FABRICATION", 50)
        db.session.commit()

        result = renumber_fabrication_fab_orders(dry_run=True)

        assert len(result['changes']) == 1
        change = result['changes'][0]
        assert change['job'] == 1
        assert change['release'] == "A"
        assert change['stage'] == "Released"
        assert change['from'] == 50
        assert change['to'] == 3
