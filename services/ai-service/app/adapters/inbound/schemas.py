"""HTTP request/response DTOs (adapter layer; may diverge from domain naming)."""
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    text: str


class ComponentSchema(BaseModel):
    name: str
    type: str
    description: str


class RiskSchema(BaseModel):
    severity: str
    description: str
    recommendation: str


class AnalysisResponse(BaseModel):
    components: list[ComponentSchema]
    risks: list[RiskSchema]
    summary: str
