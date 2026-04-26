"""FastAPI inbound adapter: maps HTTP ↔ application use cases."""
import logging
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.adapters.inbound.schemas import AnalysisResponse, AnalyzeRequest, ComponentSchema, RiskSchema
from app.application.analyze_diagram import AnalyzeDiagramUseCase
from app.domain.exceptions import LlmAnalysisError, LlmNotConfiguredError, ValidationError

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


def get_analyze_use_case(request: Request) -> AnalyzeDiagramUseCase:
    return request.app.state.analyze_use_case


async def verify_api_key(x_api_key: str = Header(None)):
    valid_key = os.getenv("API_KEY", "")
    if not valid_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    if x_api_key != valid_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health():
        return {"status": "healthy", "service": "ai-service"}

    @router.post("/analyze", response_model=AnalysisResponse)
    @limiter.limit("10/minute")
    async def analyze(
        request: Request,
        body: AnalyzeRequest,
        api_key: str = Depends(verify_api_key),
        analyze_use_case: AnalyzeDiagramUseCase = Depends(get_analyze_use_case),
    ):
        request_id = str(uuid.uuid4())[:8]
        logger.info(f"[{request_id}] Analyze request: {len(body.text)} chars")
        
        try:
            result = await analyze_use_case.execute(body.text)
        
        except LlmNotConfiguredError as e:
            logger.warning(f"[{request_id}] LLM not configured")
            raise HTTPException(
                status_code=503,
                detail="AI service unavailable (not configured)"
            )
        
        except LlmAnalysisError as e:
            logger.error(
                f"[{request_id}] LLM analysis failed",
                exc_info=True,
                extra={"request_id": request_id, "error": str(e)}
            )
            raise HTTPException(
                status_code=500,
                detail="Analysis failed: could not process diagram"
            )
        
        except ValueError as e:
            # Input validation errors
            logger.warning(f"[{request_id}] Input validation error: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid input: {str(e)}"
            )
        
        except Exception as e:
            # Unexpected error - this is a bug in the service
            logger.critical(
                f"[{request_id}] Unexpected error",
                exc_info=True,
                extra={"request_id": request_id, "error_type": type(e).__name__}
            )
            raise HTTPException(
                status_code=500,
                detail="Internal server error (request logged)"
            )
        
        try:
            response = AnalysisResponse(
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
            logger.info(f"[{request_id}] Analysis success: {len(response.components)} components")
            return response
        
        except Exception as e:
            # Response building error
            logger.error(f"[{request_id}] Response serialization error", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Error formatting response"
            )
    
    return router
