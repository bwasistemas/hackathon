"""Domain-specific exceptions."""


class DomainError(Exception):
    """Base exception for domain errors."""
    pass


class FileTooLargeError(DomainError):
    """Raised when uploaded file exceeds size limit."""
    pass


class InvalidFileTypeError(DomainError):
    """Raised when uploaded file type is not supported."""
    pass


class UploadNotFoundError(DomainError):
    """Raised when upload is not found."""
    pass


class StorageError(DomainError):
    """Raised when storage operation fails."""
    pass


class MessageQueueError(DomainError):
    """Raised when message queue operation fails."""
    pass
