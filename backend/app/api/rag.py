"""The non-streaming RAG endpoints, which is how the MCP server asks.

`/chat` is the browser's route and audits itself. These two are the same
knowledge base reached from Claude Desktop, and until now they logged nothing --
so the audit trail the README describes covered one of the two front ends and
said nothing about the gap. Every event here carries `source: "rag_api"` so the
two routes are distinguishable after the fact -- the route, not the caller,
because nothing in the request says who is on the other end of it.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.rag.retriever import retrieve
from app.services.audit_service import log_event
from app.services.rag_pipeline import query_rag
from app.utils.constants import (
    GUARDRAIL_OUTPUT,
    SSE_DONE,
    SSE_GUARDRAIL,
    SSE_TOKEN,
)
from app.utils.request import get_client_ip
from app.utils.sse import parse_sse_event

logger = logging.getLogger(__name__)
router = APIRouter()


async def _audit(db: AsyncSession, event_type: str, detail: dict,
                 ip_address: str | None) -> None:
    """Record an event, but never fail the request because recording failed.

    An answer the user received and no log of it is bad; an answer the user
    could not receive because the log would not write is worse.
    """
    try:
        await log_event(db, event_type=event_type,
                        detail={**detail, "source": "rag_api"}, ip_address=ip_address)
    except Exception:
        logger.exception("Failed to write audit event %s", event_type)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class AskRequest(BaseModel):
    question: str


@router.post("/search")
async def search_knowledge_base(
    request: Request,
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    chunks = await asyncio.to_thread(retrieve, body.query, body.top_k)
    await _audit(db, "search", {"query": body.query[:200], "top_k": body.top_k},
                 get_client_ip(request))
    return {"query": body.query, "chunks": chunks}


@router.post("/ask")
async def ask_securag(
    request: Request,
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
):
    llm = request.app.state.llm_provider
    ip_address = get_client_ip(request)
    await _audit(db, "query", {"query": body.question[:200]}, ip_address)

    tokens: list[str] = []
    sources: list[dict] = []
    blocked = False
    flagged = False

    async for event in query_rag(body.question, llm):
        data = parse_sse_event(event)
        if data is None:
            continue
        if data.get("type") == SSE_TOKEN:
            tokens.append(data.get("content", ""))
        elif data.get("type") == SSE_GUARDRAIL:
            # An output flag annotates an answer that was already generated;
            # only an input block replaces it. See `app.utils.constants`.
            if data.get("stage") == GUARDRAIL_OUTPUT:
                flagged = True
            else:
                tokens = [data.get("content", "")]
                blocked = True
        elif data.get("type") == SSE_DONE:
            sources = data.get("sources", [])

    if blocked or flagged:
        await _audit(db, "guardrail_block" if blocked else "guardrail_flag",
                     {"query": body.question[:200]}, ip_address)

    return {"answer": "".join(tokens), "sources": sources}
