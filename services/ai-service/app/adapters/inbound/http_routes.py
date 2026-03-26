"""FastAPI inbound adapter: maps HTTP ↔ application use cases."""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.adapters.inbound.schemas import AnalysisResponse, AnalyzeRequest, ComponentSchema, RiskSchema
from app.application.analyze_diagram import AnalyzeDiagramUseCase
from app.domain.exceptions import LlmAnalysisError, LlmNotConfiguredError


def get_analyze_use_case(request: Request) -> AnalyzeDiagramUseCase:
    return request.app.state.analyze_use_case


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health():
        return {"status": "healthy", "service": "ai-service"}

    @router.post("/analyze", response_model=AnalysisResponse)
    async def analyze(
        body: AnalyzeRequest,
        analyze_use_case: AnalyzeDiagramUseCase = Depends(get_analyze_use_case),
    ):
        try:
            result = await analyze_use_case.execute(body.text)
        except LlmNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except LlmAnalysisError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        return AnalysisResponse(
            components=[
                ComponentSchema(
                    name=c.name,
                    type=c.component_type,
                    description=c.description,
                )
                for c in result.components
            ],
            risks=[
                RiskSchema(
                    severity=r.severity,
                    description=r.description,
                    recommendation=r.recommendation,
                )
                for r in result.risks
            ],
            summary=result.summary,
        )

    return router
