import asyncio
import json

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.rag.retriever import retrieve
from app.services.rag_pipeline import query_rag

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class AskRequest(BaseModel):
    question: str


@router.post("/search")
async def search_knowledge_base(body: SearchRequest):
    chunks = await asyncio.to_thread(retrieve, body.query, body.top_k)
    return {"query": body.query, "chunks": chunks}


@router.post("/ask")
async def ask_securag(request: Request, body: AskRequest):
    llm = request.app.state.llm_provider
    full_response = ""
    sources: list = []

    async for event in query_rag(body.question, llm):
        if not event.startswith("data: "):
            continue
        try:
            data = json.loads(event[6:].strip())
            if data.get("type") == "token":
                full_response += data.get("content", "")
            elif data.get("type") == "guardrail":
                full_response = data.get("content", "")
            elif data.get("type") == "done":
                sources = data.get("sources", [])
        except (json.JSONDecodeError, KeyError):
            pass

    return {"answer": full_response, "sources": sources}
