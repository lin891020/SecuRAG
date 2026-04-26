from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.settings import router as settings_router
from app.api.rag import router as rag_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(rag_router, prefix="/rag", tags=["rag"])
