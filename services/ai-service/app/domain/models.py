"""Core domain models for architecture analysis."""
from dataclasses import dataclass, field
from datetime import datetime


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
class Component:
    """Component in an architecture."""
    name: str
    component_type: str
    description: str


@dataclass(frozen=True)
class Risk:
    """Risk in an architecture."""
    severity: str
    description: str
    recommendation: str


@dataclass(frozen=True)
class AnalysisResult:
    """Result of the analysis of an architecture."""
    components: list[Component] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    summary: str = ""
    # How the model interpreted OCR/limitations (distinct from executive summary).
    source_assessment: str = ""


@dataclass(frozen=True)
class DiagramTextExtraction:
    """Raw diagram text plus how it was obtained (multimodal LLM vs Tesseract)."""
    text: str
    # "llm_multimodal" | "tesseract"
    source: str
    # Value of LLM_OCR from settings (for display whether or not it was used).
    multimodal_model: str
    detail_pt: str
