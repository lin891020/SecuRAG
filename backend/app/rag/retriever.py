from app.config import settings
from app.rag.embeddings import embed_query
from app.rag.vectorstore import query_chunks


def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """Retrieve relevant chunks for a query.

    Returns a list of dicts with keys: text, doc_id, filename, chunk_index, page_number, distance
    """
    if top_k is None:
        top_k = settings.retrieval_top_k

    query_embedding = embed_query(query)
    results = query_chunks(query_embedding, top_k=top_k)

    if not results["documents"] or not results["documents"][0]:
        return []

    chunks = []
    for i, doc_text in enumerate(results["documents"][0]):
        metadata = results["metadatas"][0][i]
        distance = results["distances"][0][i] if results.get("distances") else None
        chunks.append({
            "text": doc_text,
            "doc_id": metadata.get("doc_id", ""),
            "filename": metadata.get("filename", ""),
            "chunk_index": metadata.get("chunk_index", 0),
            "page_number": metadata.get("page_number"),
            "distance": distance,
        })

    return chunks
