import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.document_service import (
    delete_document,
    ingest_document,
    list_documents,
)

router = APIRouter()

UPLOAD_DIR = Path("/app/uploads")
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}


@router.get("", response_model=DocumentListResponse)
async def get_documents(db: AsyncSession = Depends(get_db)):
    docs = await list_documents(db)
    return DocumentListResponse(documents=[DocumentResponse.model_validate(d) for d in docs])


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
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

    # Save uploaded file
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / f"{uuid.uuid4()}{suffix}"
    content = await file.read()
    file_path.write_bytes(content)

    try:
        doc = await ingest_document(
            db=db,
            file_path=file_path,
            filename=file.filename,
            file_size=len(content),
        )
        return DocumentResponse.model_validate(doc)
    except Exception as e:
        # Clean up file on failure
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{doc_id}")
async def remove_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_document(db, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted"}
