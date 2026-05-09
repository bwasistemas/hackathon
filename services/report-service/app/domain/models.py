"""Core domain models for report management."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class User:
    """User entity for authentication."""
    id: str
    username: str
    email: str
    hashed_password: str
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class Report:
    """Report entity representing an analysis report."""
    id: str
    filename: str
    status: str
    analysis: dict
    created_at: datetime


@dataclass(frozen=True)
class ReportSummary:
    """Summary of a report for list views."""
    id: str
    filename: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class Feedback:
    """Feedback entity for report ratings."""
    id: int
    upload_id: str
    rating: int
    comment: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class Statistics:
    """Statistics about uploads and feedback."""
    total_uploads: int
    by_status: dict
    avg_rating: float
    total_feedback: int
