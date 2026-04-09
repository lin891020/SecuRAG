import chromadb

from app.config import settings

_client: chromadb.HttpClient | None = None


def get_chroma_client() -> chromadb.HttpClient:
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    return _client


def get_collection() -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )


def add_chunks(
    doc_id: str,
    filename: str,
    file_type: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> None:
    collection = get_collection()
    collection.add(
        ids=[f"{doc_id}_chunk_{i}" for i in range(len(chunks))],
        embeddings=embeddings,
        documents=[c["text"] for c in chunks],
        metadatas=[
            {
                "doc_id": doc_id,
                "filename": filename,
                "file_type": file_type,
                "chunk_index": i,
                "page_number": c["page"] or 0,
            }
            for i, c in enumerate(chunks)
        ],
    )


def query_chunks(
    query_embedding: list[float], top_k: int = 5
) -> dict:
    collection = get_collection()
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )


def delete_document_chunks(doc_id: str) -> None:
    collection = get_collection()
    collection.delete(where={"doc_id": doc_id})
