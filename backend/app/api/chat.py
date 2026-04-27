import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete

from app.database import async_session, get_db
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import ChatMessageResponse, ChatRequest, ChatSessionRenameRequest, ChatSessionResponse
from app.services.audit_service import log_event
from app.services.rag_pipeline import query_rag
from app.utils.constants import SSE_DONE, SSE_GUARDRAIL, SSE_TOKEN
from app.utils.request import get_client_ip
from app.utils.sse import parse_sse_event

logger = logging.getLogger(__name__)
router = APIRouter()


async def _stream_and_persist(
    query: str,
    llm: object,
    session_id: uuid.UUID,
    history: list[dict],
    ip_address: str | None = None,
) -> AsyncIterator[str]:
    """Wrap the RAG stream to collect the full response and persist it after streaming."""
    tokens: list[str] = []
    sources: list[dict] | None = None
    was_blocked = False

    try:
        async for event in query_rag(query, llm, history=history):
            yield event

            data = parse_sse_event(event)
            if data is not None:
                if data.get("type") == SSE_TOKEN:
                    tokens.append(data.get("content", ""))
                elif data.get("type") == SSE_GUARDRAIL:
                    tokens = [data.get("content", "")]
                    was_blocked = True
                elif data.get("type") == SSE_DONE:
                    sources = data.get("sources")
    except GeneratorExit:
        pass

    full_response = "".join(tokens)
    async with async_session() as db:
        if full_response:
            try:
                assistant_msg = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    sources=sources,
                )
                db.add(assistant_msg)
                await db.commit()
            except Exception:
                logger.exception("Failed to persist assistant message")

        if was_blocked:
            try:
                await log_event(
                    db,
                    event_type="guardrail_block",
                    detail={"query": query[:200], "session_id": str(session_id)},
                    ip_address=ip_address,
                )
            except Exception:
                logger.exception("Failed to log guardrail block event")


@router.post("")
async def chat(
    request: Request,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    llm = request.app.state.llm_provider
    ip_address = get_client_ip(request)

    # Create or retrieve session
    if body.session_id:
        session = await db.get(ChatSession, body.session_id)
        if not session:
            session = ChatSession(id=body.session_id)
            db.add(session)
    else:
        session = ChatSession(id=uuid.uuid4(), title=body.message[:50])
        db.add(session)
    await db.commit()

    # Save user message
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    await db.commit()

    await log_event(
        db,
        event_type="query",
        detail={"query": body.message[:200], "session_id": str(session.id)},
        ip_address=ip_address,
    )

    # Load recent conversation history (last 6 messages = 3 turns)
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(6)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(history_result.scalars().all())
    ]

    return StreamingResponse(
        _stream_and_persist(body.message, llm, session.id, history, ip_address),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Session-Id": str(session.id),
        },
    )


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatSession).order_by(ChatSession.created_at.desc()).limit(50)
    )
    sessions = result.scalars().all()
    return [ChatSessionResponse.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def get_session_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
async def rename_session(
    session_id: uuid.UUID,
    body: ChatSessionRenameRequest,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.title = body.title
    await db.commit()
    await db.refresh(session)
    return ChatSessionResponse.model_validate(session)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return {"message": "Session deleted"}
