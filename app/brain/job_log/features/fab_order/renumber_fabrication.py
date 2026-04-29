"""
@milehigh-header
schema_version: 1
purpose: Compress FABRICATION-group fab_order values to a contiguous 3..N block while preserving relative order. Triggered by an admin button on the Job Log.
exports:
  renumber_fabrication_fab_orders: Reassign fab_order for active FABRICATION releases starting at 3
imports_from: [app.models, app.services.job_event_service, app.services.outbox_service, app.logging_config]
imported_by: [app/brain/job_log/routes.py, tests/test_renumber_fabrication.py]
invariants:
  - Only releases with stage_group='FABRICATION' are touched; Welded QC, Paint Start, fixed-tier, and Complete rows are untouched
  - Releases at DEFAULT_FAB_ORDER (80.555 placeholder for "no position assigned yet") are preserved as-is — they don't consume a sequence slot
  - Releases sharing the same current fab_order share the same new fab_order (intentional ties survive renumber)
  - Relative order is preserved (sort by current fab_order asc nullslast, tie-break by job/release)
  - dry_run=True rolls back all DB changes and creates no events or outbox items
  - For each changed release with a trello_card_id, a JobEvent is created and a Trello outbox item is queued. Releases without a card get the event closed immediately. When Config.FAB_ORDER_FIELD_ID is unset (sandbox/local without Trello creds) the outbox is skipped entirely — events still recorded for audit.
updated_by_agent: 2026-04-29T00:00:00Z
"""
from datetime import datetime

from app.models import Releases, db
from app.api.helpers import DEFAULT_FAB_ORDER, STAGE_TO_GROUP
from app.services.job_event_service import JobEventService
from app.services.outbox_service import OutboxService
from app.config import Config
from app.logging_config import get_logger

logger = get_logger(__name__)

MAX_CHANGES_IN_RESPONSE = 200
START_FAB_ORDER = 3


def renumber_fabrication_fab_orders(dry_run=False):
    """Compress FABRICATION-group fab_order values to a contiguous 3..N block.

    Preserves the current relative order. Does not touch any release outside
    FABRICATION (Welded QC, Paint Start, Shipping, Paint complete, Store,
    Shipping planning, Complete) — fab_order space is split per stage_group.

    Args:
        dry_run: If True, build the change list but rollback all DB writes
                 and skip event/outbox creation.

    Returns:
        dict: {
            'changed': int,
            'unchanged': int,
            'total_fabrication': int,
            'changes': [{'job', 'release', 'stage', 'from', 'to'}, ...]  # capped
        }
    """
    active_filter = (
        (Releases.is_archived == False) &  # noqa: E712
        ((Releases.is_active == True) | (Releases.is_active.is_(None)))  # noqa: E712
    )

    # Match the frontend Fab filter: it derives Stage Group from `stage` via
    # STAGE_TO_GROUP at serialization time (see routes.py /get-all-jobs), not
    # from the `stage_group` column. Some rows have stale or NULL stage_group
    # in the DB, so filtering on the column undercounts — derive from stage instead.
    fab_stage_variants = [s for s, g in STAGE_TO_GROUP.items() if g == 'FABRICATION']
    all_fab_releases = (
        Releases.query
        .filter(active_filter, Releases.stage.in_(fab_stage_variants))
        .order_by(
            Releases.fab_order.asc().nullslast(),
            Releases.job.asc(),
            Releases.release.asc(),
        )
        .all()
    )

    # Working set: rows we actually renumber. DEFAULT_FAB_ORDER is the "no position
    # assigned yet" sentinel — those rows keep their placeholder value, not collapse
    # into the sequence.
    fab_releases = [r for r in all_fab_releases if r.fab_order != DEFAULT_FAB_ORDER]
    placeholder_count = len(all_fab_releases) - len(fab_releases)

    mappings = []  # full preview: every working-set row, changed or not
    changed_count = 0
    unchanged = 0
    next_order = START_FAB_ORDER
    _SENTINEL = object()
    prev_old = _SENTINEL
    current_assigned = None

    for r in fab_releases:
        old = r.fab_order

        # Group ties: rows sharing the same current fab_order share the same new value
        # and consume only one slot in the compressed sequence.
        if old != prev_old:
            current_assigned = float(next_order)
            next_order += 1
            prev_old = old
        new = current_assigned

        mapping = {
            'job': r.job,
            'release': r.release,
            'stage': r.stage,
            'from': old,
            'to': new,
            'changed': old != new,
        }
        mappings.append(mapping)

        if old == new:
            unchanged += 1
            continue

        changed_count += 1

        if dry_run:
            continue

        # Apply the change
        r.fab_order = new
        r.last_updated_at = datetime.utcnow()
        # Releases.source_of_update is VARCHAR(16) — keep this short (in-memory
        # SQLite tests don't enforce the cap; Postgres rejects overflow).
        r.source_of_update = 'Brain:bulk_fab'

        event = JobEventService.create(
            job=r.job,
            release=r.release,
            action='update_fab_order',
            source='Brain',
            payload={'from': old, 'to': new},
        )

        if event is None:
            logger.info(
                "Bulk renumber: event deduped",
                extra={'job': r.job, 'release': r.release},
            )
            continue

        # Queue Trello sync only when a card exists AND the Trello custom-field
        # ID is configured. Sandbox/local envs without Trello creds (no
        # FAB_ORDER_FIELD_ID) skip the outbox so we don't pile up failures.
        trello_configured = bool(getattr(Config, 'FAB_ORDER_FIELD_ID', None))
        if r.trello_card_id and trello_configured:
            OutboxService.add(
                destination='trello',
                action='update_fab_order',
                event_id=event.id,
            )
        else:
            JobEventService.close(event.id)

    if dry_run:
        db.session.rollback()
        logger.info(
            "Renumber FABRICATION dry-run",
            extra={'changed': changed_count, 'unchanged': unchanged},
        )
    else:
        db.session.commit()
        logger.info(
            "Renumber FABRICATION applied",
            extra={'changed': changed_count, 'unchanged': unchanged},
        )

    return {
        'changed': changed_count,
        # Placeholder rows are not changed — surface them as part of the unchanged
        # tally so totals reconcile with the frontend Fab filter view.
        'unchanged': unchanged + placeholder_count,
        'placeholder_preserved': placeholder_count,
        'total_fabrication': len(all_fab_releases),
        # Full mapping (changed and unchanged) so the preview shows every working-set
        # row — users can see ties at 3 and 4 staying put rather than wondering why
        # the list "starts at 5".
        'changes': mappings[:MAX_CHANGES_IN_RESPONSE],
    }
