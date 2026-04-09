import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)


def _run_migrations():
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully")
    except Exception as e:
        logger.warning("Could not run migrations: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run migrations and initialize LLM provider
    _run_migrations()
    app.state.llm_provider = get_llm_provider(settings)
    yield
    # Shutdown


app = FastAPI(
    title="SecuRAG",
    description="Enterprise Security Knowledge Base Chatbot",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
