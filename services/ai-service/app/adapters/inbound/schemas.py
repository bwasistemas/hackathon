"""HTTP request/response DTOs (adapter layer; may diverge from domain naming)."""
import re
from pydantic import BaseModel, Field, field_validator


class AnalyzeRequest(BaseModel):
    text: str = Field(
        min_length=10,
        max_length=50000,  # Prevent token exhaustion (OpenAI ~8k-128k context)
        description="OCR-extracted text from diagram"
    )
    
    @field_validator('text')
    @classmethod
    def validate_text_format(cls, v):
        # Reject null bytes, excessive control characters
        if '\x00' in v:
            raise ValueError("Null bytes not allowed")
        control_chars = sum(1 for c in v if ord(c) < 32 and c not in '\n\r\t')
        if control_chars > len(v) * 0.05:  # >5% control chars = suspicious
            raise ValueError("Excessive control characters detected")
        return v.strip()


class ComponentSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    description: str = Field(min_length=1, max_length=1000)


class RiskSchema(BaseModel):
    severity: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=1000)
    recommendation: str = Field(min_length=1, max_length=1000)


class AnalysisResponse(BaseModel):
    components: list[ComponentSchema] = Field(min_items=0, max_items=50)
    risks: list[RiskSchema] = Field(min_items=0, max_items=20)
    summary: str = Field(min_length=1, max_length=5000)
