"""FastAPI inbound adapter: maps HTTP ↔ application use cases."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.adapters.inbound.schemas import AnalysisResponse, AnalyzeRequest, ComponentSchema, RiskSchema
from app.adapters.helpers.auth import verify_token
from app.application.analyze_diagram import AnalyzeDiagramUseCase
from app.domain.exceptions import LlmAnalysisError, LlmNotConfiguredError
from app.config import Settings

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

# OAuth2 scheme: this service does NOT issue tokens. Clients must obtain a JWT
# from the upload-service `/token` endpoint and present it here.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/upload-service/token", auto_error=True)


def get_analyze_use_case(request: Request) -> AnalyzeDiagramUseCase:
    return request.app.state.analyze_use_case


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate the bearer token (issued by upload-service) and return the username."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = verify_token(token, credentials_exception)
    return token_data.username


def build_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health():
        return {"status": "healthy", "service": "ai-service"}

    @router.post("/analyze", response_model=AnalysisResponse)
    @limiter.limit("10/minute")
    async def analyze(
        request: Request,
        body: AnalyzeRequest,
        current_user: str = Depends(get_current_user),
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
                        recommendation=r.recommendation or "",
                    )
                    for r in result.risks
                ],
                summary=result.summary or "",
                source_assessment=result.source_assessment or "",
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
