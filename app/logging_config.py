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
