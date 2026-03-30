"""Domain-specific exceptions."""


class DomainError(Exception):
    """Base exception for domain errors."""
    pass


class ReportNotFoundError(DomainError):
    """Raised when report is not found."""
    pass


class InvalidRatingError(DomainError):
    """Raised when rating is invalid."""
    pass


class UploadNotFoundError(DomainError):
    """Raised when upload is not found."""
    pass


class DatabaseError(DomainError):
    """Raised when database operation fails."""
    pass
