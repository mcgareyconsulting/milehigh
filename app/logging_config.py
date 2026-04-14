"""
@milehigh-header
schema_version: 1
purpose: Configures structlog with JSON rendering and provides get_logger() and SyncContext so every module logs with correlation IDs and consistent format.
exports:
  configure_logging: Sets up structlog processors, console + rotating file handlers
  get_logger: Returns a structlog.BoundLogger for a given module name
  SyncContext: Context manager that wraps sync operations with correlation ID, timing, and success/error logging
  log_sync_operation: One-shot structured log for sync events
imports_from: [structlog, logging]
imported_by: [app/__init__.py, app/services/outbox_service.py, app/services/job_event_service.py, app/brain/board/routes.py, app/trello/sync.py, app/procore/__init__.py, app/brain/job_log/routes.py, app/auth/utils.py, app/sync/context.py, app/admin/__init__.py, ...and 28 more]
invariants:
  - Rotating file handler writes to logs/app.log (10 MB max, 5 backups); ensure the logs/ directory exists.
  - configure_logging() must be called once at app startup (in app/__init__.py) before any get_logger() calls.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
import logging
import logging.config
import structlog
from datetime import datetime
import uuid
from typing import Any, Dict, Optional
import sys
import os

def configure_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """
    Configure structured logging for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path. If None, logs to stdout only.
    """
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Standard logging configuration
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "json": {
                "()": "structlog.stdlib.ProcessorFormatter",
                "processor": structlog.processors.JSONRenderer()
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "detailed",
                "stream": sys.stdout
            }
        },
        "loggers": {
            "": {  # Root logger
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            },
            "app": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            }
        }
    }
    
    # Add file handler if log_file is specified
    if log_file:
        log_config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": log_level,
            "formatter": "json",
            "filename": log_file,
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        }
        log_config["loggers"][""]["handlers"].append("file")
        log_config["loggers"]["app"]["handlers"].append("file")
    
    logging.config.dictConfig(log_config)
    
    # Set up application logger
    logger = structlog.get_logger("app")
    logger.info("Logging configured", level=log_level, file=log_file)
    
    return logger

def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)

class SyncContext:
    """Context manager for sync operations with correlation ID."""
    
    def __init__(self, operation_type: str, operation_id: Optional[str] = None):
        self.operation_type = operation_type
        self.operation_id = operation_id or str(uuid.uuid4())[:8]
        self.logger = get_logger("app.sync")
        self.start_time = None
        
    def __enter__(self):
        self.start_time = datetime.utcnow()
        self.logger.info(
            "Sync operation started",
            operation_type=self.operation_type,
            operation_id=self.operation_id,
            start_time=self.start_time.isoformat()
        )
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.utcnow() - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.info(
                "Sync operation completed",
                operation_type=self.operation_type,
                operation_id=self.operation_id,
                duration_seconds=duration,
                status="success"
            )
        else:
            self.logger.error(
                "Sync operation failed",
                operation_type=self.operation_type,
                operation_id=self.operation_id,
                duration_seconds=duration,
                status="error",
                error_type=exc_type.__name__,
                error_message=str(exc_val)
            )
        
        return False  # Don't suppress exceptions

def log_sync_operation(operation_type: str, **kwargs):
    """Log a sync operation with structured data."""
    logger = get_logger("app.sync")
    logger.info("Sync operation", operation_type=operation_type, **kwargs)
