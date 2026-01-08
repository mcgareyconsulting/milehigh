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