import asyncio
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.rag.embeddings import embed_texts
from app.utils.constants import DOC_STATUS_ERROR, DOC_STATUS_PROCESSING, DOC_STATUS_READY
from app.rag.splitter import split_pages
from app.rag.vectorstore import add_chunks, delete_document_chunks
from app.utils.file_parsers import parse_file


async def ingest_document(
    db: AsyncSession,
    file_path: Path,
    filename: str,
    file_size: int,
) -> Document:
    """Parse, chunk, embed, and store a document."""
    file_type = file_path.suffix.lstrip(".").lower()

    # Create document record
    doc = Document(
        id=uuid.uuid4(),
        filename=filename,
        file_type=file_type,
        file_size=file_size,
        status=DOC_STATUS_PROCESSING,
    )
    db.add(doc)
    await db.commit()

    try:
        # Parse file (CPU-bound)
        pages = await asyncio.to_thread(parse_file, file_path)

        # Split into chunks (CPU-bound)
        chunks = await asyncio.to_thread(split_pages, pages)

        if not chunks:
            doc.status = DOC_STATUS_ERROR
            doc.chunk_count = 0
            await db.commit()
            return doc

        # Embed chunks (CPU-bound, model inference)
        texts = [c["text"] for c in chunks]
        embeddings = await asyncio.to_thread(embed_texts, texts)

        # Store in ChromaDB (IO-bound)
        await asyncio.to_thread(
            add_chunks,
            doc_id=str(doc.id),
            filename=filename,
            file_type=file_type,
            chunks=chunks,
            embeddings=embeddings,
        )

        # Update document status
        doc.chunk_count = len(chunks)
        doc.status = DOC_STATUS_READY
        await db.commit()
        await db.refresh(doc)

    except Exception as e:
        doc.status = DOC_STATUS_ERROR
        await db.commit()
        raise e

    return doc


async def list_documents(db: AsyncSession) -> list[Document]:
    result = await db.execute(
        select(Document).order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_document(db: AsyncSession, doc_id: uuid.UUID) -> bool:
    doc = await db.get(Document, doc_id)
    if not doc:
        return False

    # Remove from ChromaDB
    await asyncio.to_thread(delete_document_chunks, str(doc_id))

    # Remove from database
    await db.delete(doc)
    await db.commit()
    return True
