"""
@milehigh-header
schema_version: 1
purpose: Delayed reconcile safety net for Procore submittal webhooks — re-fetches a submittal a short while after a webhook to catch field changes dropped by burst dedup or not yet propagated by Procore at live-processing time.
exports:
  ProcoreReconcileService: schedule() enqueues a coalescing reconcile; process_due() runs due reconciles via the outbox worker.
imports_from: [app.models, app.config, app.logging_config, app.procore.procore]
imported_by: [app/procore/__init__.py, app/__init__.py]
invariants:
  - schedule() is coalescing: at most one 'pending' row per submittal_id, so a webhook burst produces a single reconcile read.
  - process_due() must never enqueue another reconcile (only the webhook route schedules), so there is no reconcile loop.
  - A reconcile that applies any field change is a 'rescue' — the live webhook missed it — and is surfaced via a structlog warning plus a SystemLogs WARNING row.
updated_by_agent: 2026-05-23T00:00:00Z
"""
from datetime import datetime, timedelta

from app.logging_config import get_logger

logger = get_logger(__name__)

# Cap reconcile retries so a persistently failing submittal doesn't churn forever.
MAX_RECONCILE_ATTEMPTS = 3


class ProcoreReconcileService:
    """Schedule and run delayed re-fetches of Procore submittals."""

    @staticmethod
    def schedule(submittal_id, project_id, delay_seconds=None):
        """
        Enqueue a delayed reconcile for a submittal.

        Coalescing: if a 'pending' row already exists for this submittal_id, do nothing
        (a single reconcile covers the whole burst). Never raises — a scheduling failure
        must not break the webhook response.
        """
        from app.models import SubmittalReconcile, db
        from app.config import Config as cfg

        try:
            existing = SubmittalReconcile.query.filter_by(
                submittal_id=str(submittal_id), status='pending'
            ).first()
            if existing:
                logger.debug(
                    "reconcile_schedule_coalesced", submittal_id=str(submittal_id),
                    existing_id=existing.id,
                )
                return existing

            if delay_seconds is None:
                delay_seconds = cfg.PROCORE_RECONCILE_DELAY_SECONDS

            row = SubmittalReconcile(
                submittal_id=str(submittal_id),
                project_id=int(project_id),
                scheduled_for=datetime.utcnow() + timedelta(seconds=delay_seconds),
                status='pending',
                attempts=0,
                created_at=datetime.utcnow(),
            )
            db.session.add(row)
            db.session.commit()
            logger.info(
                "reconcile_scheduled", submittal_id=str(submittal_id),
                project_id=int(project_id), delay_seconds=delay_seconds,
                scheduled_for=row.scheduled_for.isoformat(),
            )
            return row
        except Exception as e:
            logger.warning(
                "reconcile_schedule_failed", submittal_id=str(submittal_id), error=str(e),
                exc_info=True,
            )
            try:
                db.session.rollback()
            except Exception:
                pass
            return None

    @staticmethod
    def process_due(limit=10):
        """
        Process pending reconciles whose scheduled_for is in the past.

        For each due row: flip to 'processing' (commit, so concurrent runs serialize),
        re-run check_and_update_submittal, and surface a rescue if any field changed.
        Returns the number of rows processed.
        """
        from app.models import SubmittalReconcile, db

        now = datetime.utcnow()
        due = (
            SubmittalReconcile.query.filter(
                SubmittalReconcile.status == 'pending',
                SubmittalReconcile.scheduled_for <= now,
            )
            .order_by(SubmittalReconcile.scheduled_for.asc())
            .limit(limit)
            .all()
        )
        if not due:
            return 0

        processed = 0
        for row in due:
            try:
                ProcoreReconcileService._process_one(row)
                processed += 1
            except Exception as e:
                logger.error(
                    "reconcile_process_error", reconcile_id=row.id,
                    submittal_id=row.submittal_id, error=str(e), exc_info=True,
                )
        return processed

    @staticmethod
    def _process_one(row):
        from app.models import db
        from app.procore.procore import check_and_update_submittal

        # Claim the row so a second worker won't double-process it.
        row.status = 'processing'
        row.attempts = (row.attempts or 0) + 1
        db.session.commit()

        try:
            ball_updated, status_updated, title_updated, manager_updated, record, _bic, _status = (
                check_and_update_submittal(row.project_id, row.submittal_id, source='Procore')
            )

            rescued = [
                name for name, changed in (
                    ('ball_in_court', ball_updated),
                    ('status', status_updated),
                    ('title', title_updated),
                    ('submittal_manager', manager_updated),
                ) if changed
            ]
            if rescued:
                ProcoreReconcileService._record_rescue(row, rescued, record)
            else:
                logger.info(
                    "reconcile_noop", reconcile_id=row.id, submittal_id=row.submittal_id,
                )

            row.status = 'completed'
            row.completed_at = datetime.utcnow()
            row.last_error = None
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            row.last_error = str(e)[:500]
            if (row.attempts or 0) >= MAX_RECONCILE_ATTEMPTS:
                row.status = 'failed'
                logger.error(
                    "reconcile_failed", reconcile_id=row.id, submittal_id=row.submittal_id,
                    attempts=row.attempts, error=str(e), exc_info=True,
                )
            else:
                # Re-arm with a short backoff so the worker retries it later.
                row.status = 'pending'
                row.scheduled_for = datetime.utcnow() + timedelta(seconds=30 * row.attempts)
                logger.warning(
                    "reconcile_retry", reconcile_id=row.id, submittal_id=row.submittal_id,
                    attempts=row.attempts, error=str(e),
                )
            db.session.commit()

    @staticmethod
    def _record_rescue(row, rescued_fields, record):
        """
        A reconcile applied a change the live webhook missed. Surface it loudly:
        structlog warning + a queryable SystemLogs WARNING row.
        """
        from app.models import SystemLogs, db

        logger.warning(
            "reconcile_rescue", submittal_id=row.submittal_id,
            project_id=row.project_id, rescued_fields=rescued_fields,
        )
        try:
            db.session.add(SystemLogs(
                timestamp=datetime.utcnow(),
                level='WARNING',
                category='procore',
                operation='reconcile_rescue',
                message=(
                    f"Reconcile caught {len(rescued_fields)} field change(s) the live "
                    f"webhook missed for submittal {row.submittal_id}: {', '.join(rescued_fields)}"
                ),
                context={
                    'submittal_id': row.submittal_id,
                    'project_id': row.project_id,
                    'rescued_fields': rescued_fields,
                    'reconcile_id': row.id,
                    'title': getattr(record, 'title', None),
                    'project_name': getattr(record, 'project_name', None),
                },
            ))
            db.session.commit()
        except Exception as e:
            logger.warning("reconcile_rescue_log_failed", error=str(e))
            db.session.rollback()
