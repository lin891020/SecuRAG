import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.rag.retriever import retrieve
from app.services.rag_pipeline import query_rag
from app.utils.constants import SSE_DONE, SSE_GUARDRAIL, SSE_TOKEN
from app.utils.sse import parse_sse_event

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
    tokens: list[str] = []
    sources: list[dict] = []

    async for event in query_rag(body.question, llm):
        data = parse_sse_event(event)
        if data is None:
            continue
        if data.get("type") == SSE_TOKEN:
            tokens.append(data.get("content", ""))
        elif data.get("type") == SSE_GUARDRAIL:
            tokens = [data.get("content", "")]
        elif data.get("type") == SSE_DONE:
            sources = data.get("sources", [])

    return {"answer": "".join(tokens), "sources": sources}
