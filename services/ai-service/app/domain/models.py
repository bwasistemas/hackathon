"""Core domain models for architecture analysis."""
from dataclasses import dataclass, field


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
