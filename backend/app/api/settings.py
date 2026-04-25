from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings as app_settings
from app.llm.ollama_provider import OllamaProvider
from app.llm.vertexai_provider import VertexAIProvider

router = APIRouter()


class ProviderUpdate(BaseModel):
    provider: str


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
