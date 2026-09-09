import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)


def _run_migrations(config=None) -> None:
    """Bring the database up to head. Blocking -- never call this on the loop.

    `alembic/env.py` runs its migrations through ``asyncio.run``, so this
    cannot be called from anywhere that already has a loop: it raises
    "asyncio.run() cannot be called from a running event loop". That is what
    used to happen. The call sat directly in the async lifespan inside a bare
    ``except Exception`` that logged a warning, so every start-up raised,
    swallowed it, and carried on with whatever schema the database happened to
    have -- which means start-up migrations never once ran.

    `config` exists so a test can point the same code at a throwaway database;
    production passes nothing and gets `alembic.ini`.
    """
    from alembic import command
    from alembic.config import Config

    command.upgrade(config or Config("alembic.ini"), "head")
    logger.info("Database migrations applied successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run migrations and initialize LLM provider.
    #
    # A failed migration is fatal on purpose. The previous version logged a
    # warning and carried on, so a backend whose schema was missing or stale
    # started successfully and then failed on the first query that touched a
    # table -- with the real cause several hundred log lines earlier, at
    # warning level, in a line nobody reads on a healthy boot.
    await asyncio.to_thread(_run_migrations)
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
