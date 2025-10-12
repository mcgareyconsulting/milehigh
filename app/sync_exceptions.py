"""
Custom exception classes for sync operations to improve error handling and reduce conditional complexity.
"""
from typing import Optional, Dict, Any


class SyncException(Exception):
    """Base exception for sync operations."""
    
    def __init__(self, message: str, operation_id: Optional[str] = None, 
                 error_type: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.operation_id = operation_id
        self.error_type = error_type or self.__class__.__name__
        self.context = context or {}


class SyncValidationError(SyncException):
    """Raised when sync data validation fails."""
    pass


class SyncCardNotFoundError(SyncException):
    """Raised when a Trello card is not found."""
    pass


class SyncNoValidIdentifierError(SyncException):
    """Raised when no valid identifier can be extracted from card name."""
    pass


class SyncParseError(SyncException):
    """Raised when parsing job-release identifier fails."""
    pass


class SyncAlreadyExistsError(SyncException):
    """Raised when attempting to create a duplicate record."""
    pass


class SyncNotInExcelError(SyncException):
    """Raised when job-release is not found in Excel."""
    pass


class SyncDatabaseError(SyncException):
    """Raised when database operations fail."""
    pass


class SyncExcelError(SyncException):
    """Raised when Excel operations fail."""
    pass


class SyncTrelloError(SyncException):
    """Raised when Trello API operations fail."""
    pass


class SyncDuplicateUpdateError(SyncException):
    """Raised when attempting a duplicate update."""
    pass
