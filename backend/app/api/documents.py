import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.audit_service import log_event
from app.services.document_service import (
    delete_document,
    ingest_document,
    list_documents,
)
from app.utils.request import get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = Path(settings.upload_dir)
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.get("", response_model=DocumentListResponse)
async def get_documents(db: AsyncSession = Depends(get_db)):
    docs = await list_documents(db)
    return DocumentListResponse(documents=[DocumentResponse.model_validate(d) for d in docs])


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    request: Request,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # Read and enforce size limit
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    # Save uploaded file
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / f"{uuid.uuid4()}{suffix}"
    file_path.write_bytes(content)

    ip_address = get_client_ip(request)
    try:
        doc = await ingest_document(
            db=db,
            file_path=file_path,
            filename=file.filename,
            file_size=len(content),
        )
        await log_event(
            db,
            event_type="upload",
            detail={"filename": file.filename, "file_size": len(content), "doc_id": str(doc.id)},
            ip_address=ip_address,
        )
        return DocumentResponse.model_validate(doc)
    except Exception:
        logger.exception("Document ingestion failed for %s", file.filename)
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Document processing failed. Please try again.")


@router.delete("/{doc_id}")
async def remove_document(
    request: Request,
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_document(db, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    await log_event(
        db,
        event_type="delete",
        detail={"doc_id": str(doc_id)},
        ip_address=get_client_ip(request),
    )
    return {"message": "Document deleted"}
