import asyncio
import json
import logging
import time
from typing import AsyncIterator

from app.guardrails.guard import guard_service
from app.llm.base import LLMProvider
from app.rag.retriever import retrieve

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are SecuRAG, an enterprise security knowledge base assistant.
Answer questions based ONLY on the provided context from the knowledge base.
If the context doesn't contain enough information to answer, say so honestly.
Always cite which document and page your answer comes from.
Respond in the same language as the user's question."""


def _build_prompt(query: str, contexts: list[dict], history: list[dict]) -> str:
    context_text = "\n\n".join(
        f"[Source: {c['filename']}, Page {c['page_number']}]\n{c['text']}"
        for c in contexts
    )
    history_text = ""
    if history:
        lines = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:500]}"
            for m in history
        )
        history_text = f"Previous conversation:\n{lines}\n---\n\n"

    return f"""{history_text}Context from knowledge base:
---
{context_text}
---

User question: {query}

Please answer based on the context above."""


async def query_rag(
    query: str,
    llm: LLMProvider,
    history: list[dict] | None = None,
) -> AsyncIterator[str]:
    """Execute the RAG pipeline and yield SSE events.

    Returns an async iterator of SSE events. The final_response list
    is populated as a side effect so the caller can persist the full response.
    """
    # --- Input guardrail check ---
    yield f"data: {json.dumps({'type': 'status', 'label': 'Checking input safety...', 'ts': time.time()})}\n\n"
    allowed, blocked_msg = await guard_service.check_input(query)
    if not allowed:
        logger.warning("Guardrails blocked input: %s", query[:100])
        yield f"data: {json.dumps({'type': 'guardrail', 'content': blocked_msg})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'sources': [], 'blocked': True})}\n\n"
        return

    # Retrieve relevant chunks (sync: embedding + ChromaDB query)
    yield f"data: {json.dumps({'type': 'status', 'label': 'Searching knowledge base...', 'ts': time.time()})}\n\n"
    contexts = await asyncio.to_thread(retrieve, query)

    if not contexts:
        yield f"data: {json.dumps({'type': 'token', 'content': 'No relevant documents found in the knowledge base. Please upload documents first.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
        return

    # Build prompt with context
    prompt = _build_prompt(query, contexts, history or [])

    # Stream LLM response
    yield f"data: {json.dumps({'type': 'status', 'label': 'Generating response...', 'ts': time.time()})}\n\n"
    full_response = ""
    async for token in llm.generate_stream(prompt, system_prompt=SYSTEM_PROMPT):
        full_response += token
        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    # --- Output guardrail check ---
    output_allowed, sanitized = await guard_service.check_output(full_response)
    if not output_allowed:
        logger.warning("Guardrails blocked output for query: %s", query[:100])
        yield f"data: {json.dumps({'type': 'guardrail', 'content': 'Response was filtered by security policy.'})}\n\n"

    # Build source references
    sources = [
        {
            "document_id": c["doc_id"],
            "filename": c["filename"],
            "chunk_index": c["chunk_index"],
            "page_number": c["page_number"],
            "content_preview": (c["text"][:100] + "...") if len(c["text"]) > 100 else c["text"],
        }
        for c in contexts
    ]

    yield f"data: {json.dumps({'type': 'done', 'sources': sources, 'ts': time.time(), 'model': llm.model_name()})}\n\n"
