"""SecuRAG MCP Server

Exposes the SecuRAG knowledge base as MCP tools so Claude Desktop (or any
MCP-compatible client) can query your local security document knowledge base.

The server runs inside the backend Docker container, which already has Python 3.11
and all required dependencies. Claude Desktop communicates with it via docker exec.

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "securag": {
        "command": "docker",
        "args": ["exec", "-i", "securag-backend-1", "python", "/app/mcp_server.py"]
      }
    }
  }

Requirements: SecuRAG services must be running (`make up`) before starting Claude Desktop.
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

BACKEND_URL = os.getenv("SECURAG_BACKEND_URL", "http://localhost:8000/api")

mcp = FastMCP("SecuRAG")


async def _backend_request(
    method: str, path: str, *, timeout: float = 30, **kwargs
) -> httpx.Response | str:
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await getattr(client, method)(f"{BACKEND_URL}{path}", **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.ConnectError:
            return "Error: SecuRAG backend is not running. Start it with `make up`."
        except httpx.HTTPStatusError as e:
            return f"Error: Backend returned {e.response.status_code}"


@mcp.tool()
async def search_knowledge_base(query: str, top_k: int = 5) -> str:
    """Search the SecuRAG knowledge base and return relevant document chunks.

    Use this when you need to find specific information from the uploaded
    security documents without generating a full answer.

    Args:
        query: The search query or topic to look up.
        top_k: Number of chunks to return (default 5, max 20).
    """
    result = await _backend_request(
        "post", "/rag/search", json={"query": query, "top_k": min(top_k, 20)}
    )
    if isinstance(result, str):
        return result

    chunks = result.json().get("chunks", [])
    if not chunks:
        return "No relevant documents found for this query."

    lines = []
    for i, c in enumerate(chunks, 1):
        page = f"page {c['page_number']}" if c.get("page_number") else "no page"
        lines.append(f"[{i}] {c['filename']} ({page}):\n{c['text'][:600]}")

    return "\n\n---\n\n".join(lines)


@mcp.tool()
async def ask_securag(question: str) -> str:
    """Ask a question and get a full RAG-powered answer from the SecuRAG knowledge base.

    This runs the complete pipeline: retrieves relevant chunks, sends them to
    the local LLM, and returns a synthesized answer with source citations.
    Response may take 30-120 seconds depending on LLM speed.

    Args:
        question: The security question to answer.
    """
    result = await _backend_request(
        "post", "/rag/ask", json={"question": question}, timeout=180
    )
    if isinstance(result, str):
        return result

    data = result.json()
    answer = data.get("answer", "").strip()
    sources = data.get("sources", [])

    if not answer:
        return "No answer was generated. The knowledge base may be empty."

    if sources:
        seen = set()
        source_lines = []
        for s in sources:
            key = (s["filename"], s.get("page_number"))
            if key not in seen:
                seen.add(key)
                page = f", page {s['page_number']}" if s.get("page_number") else ""
                source_lines.append(f"- {s['filename']}{page}")
        answer += "\n\nSources:\n" + "\n".join(source_lines)

    return answer


@mcp.tool()
async def list_documents() -> str:
    """List all documents currently uploaded to the SecuRAG knowledge base.

    Use this first to see what documents are available before searching or asking questions.
    """
    result = await _backend_request("get", "/documents", timeout=15)
    if isinstance(result, str):
        return result

    docs = result.json().get("documents", [])
    if not docs:
        return "No documents in the knowledge base. Upload some via the SecuRAG web UI."

    lines = []
    total_chunks = 0
    for d in docs:
        size_kb = d.get("file_size", 0) / 1024
        chunks = d.get("chunk_count", 0)
        total_chunks += chunks
        lines.append(f"- {d['filename']}  ({chunks} chunks, {size_kb:.0f} KB)")

    return f"{len(docs)} documents, {total_chunks} total chunks:\n" + "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
