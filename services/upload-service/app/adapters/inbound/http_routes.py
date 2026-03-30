"""FastAPI inbound adapter: maps HTTP ↔ application use cases."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File

from app.adapters.inbound.schemas import UploadResponse, UploadListItemSchema, UploadDetailSchema
from app.application.upload_file import UploadFileUseCase, ListUploadsUseCase, GetUploadUseCase
from app.domain.exceptions import FileTooLargeError, InvalidFileTypeError, UploadNotFoundError, StorageError, MessageQueueError


def get_upload_use_case(request: Request) -> UploadFileUseCase:
    """Dependency injection for upload use case."""
    return request.app.state.upload_use_case


def get_list_uploads_use_case(request: Request) -> ListUploadsUseCase:
    """Dependency injection for list uploads use case."""
    return request.app.state.list_uploads_use_case


def get_get_upload_use_case(request: Request) -> GetUploadUseCase:
    """Dependency injection for get upload use case."""
    return request.app.state.get_upload_use_case


def build_router() -> APIRouter:
    """Build and configure the HTTP router."""
    router = APIRouter()

    @router.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "service": "upload-service"}

    @router.post("/upload", response_model=UploadResponse)
    async def upload_file(
        file: UploadFile = File(...),
        upload_use_case: UploadFileUseCase = Depends(get_upload_use_case),
    ):
        """Upload a file."""
        try:
            content = await file.read()
            result = await upload_use_case.execute(
                filename=file.filename,
                content=content,
                content_type=file.content_type or "application/octet-stream",
            )
            
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
