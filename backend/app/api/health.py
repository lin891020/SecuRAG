import httpx
from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    checks = {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "guardrails_enabled": settings.guardrails_enabled,
        "services": {
            "postgres": await _check_postgres(),
            "chromadb": await _check_chromadb(),
            "ollama": await _check_ollama(),
        },
    }
    # Overall status is "degraded" if any service is down
    if not all(checks["services"].values()):
        checks["status"] = "degraded"
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
                f"http://{settings.chroma_host}:{settings.chroma_port}/api/v1/heartbeat"
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
