from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.vertexai_provider import VertexAIProvider


def get_llm_provider(config: Settings) -> LLMProvider:
    if config.llm_provider == "ollama":
        return OllamaProvider(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
        )
    elif config.llm_provider == "vertexai":
        return VertexAIProvider(
            project=config.gcp_project,
            region=config.gcp_region,
            model=config.vertexai_model,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {config.llm_provider}")
