import httpx
from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    services = {
        "postgres": await _check_postgres(),
        "chromadb": await _check_chromadb(),
        "ollama": await _check_ollama(),
    }
    checks = {
        "status": "ok" if all(services.values()) else "degraded",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.ollama_model if settings.llm_provider == "ollama" else settings.vertexai_model,
        "guardrails_enabled": settings.guardrails_enabled,
        "embedding_model": settings.embedding_model,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "retrieval_top_k": settings.retrieval_top_k,
        "services": services,
    }
    return checks


async def _check_postgres() -> bool:
    try:
        from sqlalchemy import text
        from app.database import async_session

        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _check_chromadb() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"http://{settings.chroma_host}:{settings.chroma_port}/api/v2/heartbeat"
            )
            return resp.status_code == 200
    except Exception:
        return False


async def _check_ollama() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False
