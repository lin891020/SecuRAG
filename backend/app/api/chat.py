import json
import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import ChatMessageResponse, ChatRequest, ChatSessionResponse
from app.services.rag_pipeline import query_rag

logger = logging.getLogger(__name__)
router = APIRouter()


async def _stream_and_persist(
    query: str,
    llm: object,
    session_id: uuid.UUID,
) -> AsyncIterator[str]:
    """Wrap the RAG stream to collect the full response and persist it after streaming."""
    full_response = ""
    sources: list | None = None

    async for event in query_rag(query, llm):
        yield event

        # Parse SSE events to collect the full response
        if event.startswith("data: "):
            try:
                data = json.loads(event[6:].strip())
                if data.get("type") == "token":
                    full_response += data.get("content", "")
                elif data.get("type") == "guardrail":
                    full_response = data.get("content", "")
                elif data.get("type") == "done":
                    sources = data.get("sources")
            except (json.JSONDecodeError, KeyError):
                pass

    # Persist assistant response after stream finishes
    if full_response:
        try:
            async with async_session() as db:
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


@router.post("")
async def chat(
    request: Request,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    llm = request.app.state.llm_provider

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

    # Stream RAG response and persist assistant message
    return StreamingResponse(
        _stream_and_persist(body.message, llm, session.id),
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
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return [ChatMessageResponse.model_validate(m) for m in messages]
