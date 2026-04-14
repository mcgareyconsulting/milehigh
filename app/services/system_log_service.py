"""
@milehigh-header
schema_version: 1
purpose: Persist system-level errors to the SystemLogs table so they survive beyond log rotation and are queryable from the admin UI.
exports:
  SystemLogService: Static service with log_error() that writes structured error records including stack traces.
imports_from: [app.logging_config, app.models]
imported_by: [app/brain/job_log/routes.py]
invariants:
  - Each log_error call commits in its own transaction to avoid being rolled back with the caller's failed work.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
from datetime import datetime
from app.logging_config import get_logger
logger = get_logger(__name__)

class SystemLogService:
    """Service for system-level logging"""
    
    @staticmethod
    def log_error(category, operation, error, context=None):
        """Log system error to database"""
        from app.models import SystemLogs, db
        import traceback
        
        logger.error(f"System error: {category} in {operation}", exc_info=True)
        
        system_log = SystemLogs(
            timestamp=datetime.utcnow(),
            level='ERROR',
            category=category,
            operation=operation,
            message=str(error),
            context={
                'stack_trace': traceback.format_exc(),
                'error_type': type(error).__name__,
                **(context or {})
            }
        )
        
        db.session.add(system_log)
        db.session.commit()  # Separate transaction
        
        return system_log