import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings as app_settings
from app.llm.ollama_provider import OllamaProvider
from app.llm.vertexai_provider import VertexAIProvider

router = APIRouter()


class ProviderUpdate(BaseModel):
    provider: str


class ModelUpdate(BaseModel):
    model: str


@router.get("/models")
async def list_models():
    """List models available in the local Ollama instance."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{app_settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {e}")


@router.patch("/model")
async def switch_model(body: ModelUpdate, request: Request):
    """Switch to a different Ollama model at runtime."""
    new_provider = OllamaProvider(
        base_url=app_settings.ollama_base_url,
        model=body.model,
    )
    request.app.state.llm_provider = new_provider
    return {"model": new_provider.model_name()}


@router.patch("/provider")
async def switch_provider(body: ProviderUpdate, request: Request):
    """Switch the active LLM provider at runtime without restarting the server."""
    if body.provider == "ollama":
        new_provider = OllamaProvider(
            base_url=app_settings.ollama_base_url,
            model=app_settings.ollama_model,
        )
    elif body.provider == "vertexai":
        new_provider = VertexAIProvider(
            project=app_settings.gcp_project,
            region=app_settings.gcp_region,
            model=app_settings.vertexai_model,
        )
    else:
        raise HTTPException(status_code=400, detail="provider must be 'ollama' or 'vertexai'")

    request.app.state.llm_provider = new_provider
    return {"provider": body.provider, "model": new_provider.model_name()}
