"""FastAPI inbound adapter: maps HTTP ↔ application use cases."""
import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from slowapi import Limiter

from app.adapters.inbound.schemas import UploadResponse, UploadListItemSchema, UploadDetailSchema, Token
from app.adapters.helpers.auth import create_access_token, verify_token
from app.application.upload_file import UploadFileUseCase, ListUploadsUseCase, GetUploadUseCase
from app.domain.exceptions import FileTooLargeError, InvalidFileTypeError, UploadNotFoundError, StorageError, MessageQueueError
from app.config import Settings

logger = logging.getLogger(__name__)


# OAuth2 scheme – tokenUrl is the path used by Swagger UI to fetch tokens.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_upload_use_case(request: Request) -> UploadFileUseCase:
    """Dependency injection for upload use case."""
    return request.app.state.upload_use_case


def get_list_uploads_use_case(request: Request) -> ListUploadsUseCase:
    """Dependency injection for list uploads use case."""
    return request.app.state.list_uploads_use_case


def get_get_upload_use_case(request: Request) -> GetUploadUseCase:
    """Dependency injection for get upload use case."""
    return request.app.state.get_upload_use_case


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate the bearer token and return the username."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = verify_token(token, credentials_exception)
    return token_data.username


def build_router(settings: Settings, limiter: Limiter) -> APIRouter:
    """Build and configure the HTTP router."""
    router = APIRouter()

    @router.get("/health")
    async def health():
        """Health check endpoint (public)."""
        return {"status": "healthy", "service": "upload-service"}

    @router.post("/token", response_model=Token)
    @limiter.limit("5/minute")
    async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
        """Login and issue a short-lived JWT.

        This is the SINGLE source of token issuance for the platform. Other
        services (`ai-service`, `report-service`) only verify tokens using the
        shared `JWT_SECRET_KEY` and never issue their own.
        """
        client_ip = request.client.host if request.client else "unknown"

        admin_user = settings.admin_user
        admin_password = settings.admin_password

        # Refuse to authenticate if the platform is still using insecure defaults.
        if not admin_user or not admin_password or admin_password == "admin123":
            logger.error(
                "Refusing to authenticate: ADMIN_USER/ADMIN_PASSWORD not configured "
                "or still using insecure defaults"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is not configured on the server",
            )

        # Constant-time comparison to mitigate timing attacks.
        username_ok = secrets.compare_digest(
            (form_data.username or "").encode("utf-8"),
            admin_user.encode("utf-8"),
        )
        password_ok = secrets.compare_digest(
            (form_data.password or "").encode("utf-8"),
            admin_password.encode("utf-8"),
        )

        if not (username_ok and password_ok):
            logger.warning(
                "Failed login attempt for username=%r from %s",
                form_data.username,
                client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.info("Successful login for user %r from %s", form_data.username, client_ip)
        access_token = create_access_token(data={"sub": form_data.username})
        return {"access_token": access_token, "token_type": "bearer"}

    @router.post("/upload", response_model=UploadResponse)
    @limiter.limit("5/minute")
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),
        current_user: str = Depends(get_current_user),
        upload_use_case: UploadFileUseCase = Depends(get_upload_use_case),
    ):
        """Upload a file."""
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"Upload attempt by user {current_user} from {client_ip}: {file.filename} ({file.content_type})")
        
        try:
            content = await file.read()
            result = await upload_use_case.execute(
                filename=file.filename,
                content=content,
                content_type=file.content_type or "application/octet-stream",
            )
            
            logger.info(f"Upload successful: {result.id} by user {current_user}")
            return UploadResponse(
                id=result.id,
                filename=result.filename,
                status=result.status,
                message=result.message,
                minio_url=result.minio_url,
            )
        
        except FileTooLargeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except InvalidFileTypeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except StorageError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except MessageQueueError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/uploads", response_model=list[UploadListItemSchema])
    async def list_uploads(
        current_user: str = Depends(get_current_user),
        list_use_case: ListUploadsUseCase = Depends(get_list_uploads_use_case),
    ):
        """List recent uploads."""
        try:
            results = await list_use_case.execute()
            return [
                UploadListItemSchema(
                    id=r.id,
                    filename=r.filename,
                    status=r.status,
                    created_at=datetime.now(),
                    minio_url=r.minio_url,
                )
                for r in results
            ]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/uploads/{upload_id}", response_model=UploadDetailSchema)
    async def get_upload(
        upload_id: str,
        current_user: str = Depends(get_current_user),
        get_use_case: GetUploadUseCase = Depends(get_get_upload_use_case),
    ):
        """Get upload details by ID."""
        try:
            upload = await get_use_case.execute(upload_id)
            if not upload:
                raise HTTPException(status_code=404, detail="Upload not found")
            
            return UploadDetailSchema(
                id=upload.id,
                filename=upload.filename,
                content_type=upload.content_type,
                file_size=upload.file_size,
                status=upload.status,
                file_path=upload.file_path,
                minio_url=upload.minio_url,
                created_at=upload.created_at,
                updated_at=upload.updated_at,
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
