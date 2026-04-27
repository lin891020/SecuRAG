from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://securag:securag@localhost:5432/securag"

    # ChromaDB
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "securag_docs"

    # LLM Provider
    llm_provider: str = "ollama"  # "ollama" | "vertexai"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Vertex AI
    gcp_project: str = ""
    gcp_region: str = "us-central1"
    vertexai_model: str = "gemini-1.5-flash"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Guardrails
    guardrails_enabled: bool = True
    guardrails_config_path: str = "app/guardrails/config"

    # RAG
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retrieval_top_k: int = 5
    retrieval_distance_threshold: float = 0.7

    # Uploads
    upload_dir: str = "/app/uploads"

    # CORS
    cors_origins: str = "http://localhost:3000"  # comma-separated

    model_config = {"env_file": ".env", "env_prefix": "SECURAG_"}


settings = Settings()
