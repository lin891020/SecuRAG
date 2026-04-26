# SecuRAG

> **Enterprise Security Knowledge Base Chatbot** — Ask questions about your internal security policies, compliance guides, and SOPs through a conversational AI interface. All processing runs on your own infrastructure; no data leaves your network.

![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square)
![Vue](https://img.shields.io/badge/Vue-3-42b883?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square)
![Tests](https://img.shields.io/badge/Tests-104%20passing-brightgreen?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

---

## What is SecuRAG?

Security teams accumulate large volumes of documentation — access control policies, incident response playbooks, OWASP guidelines, compliance frameworks — and nobody reads them. SecuRAG turns that documentation into a queryable knowledge base: upload your documents once, then ask questions in plain language and get cited answers grounded in your actual content.

It is designed for **private deployment**. The LLM (Llama 3.2) runs locally via Ollama, documents are indexed in a self-hosted ChromaDB vector store, and chat history is persisted in a PostgreSQL database you control. Nothing touches an external API unless you explicitly switch to the Vertex AI backend.

---

## How It Works

Every chat message travels through a five-stage pipeline:

```
User query
    │
    ▼
① Input Guardrail (NeMo)
    │  Blocks prompt injection & off-topic requests (fail-closed)
    │
    ▼
② Retrieval (ChromaDB + Sentence-Transformers)
    │  Embeds query → top-K cosine similarity search → distance threshold filter
    │
    ▼
③ Prompt Assembly
    │  Injects conversation history + retrieved chunks into structured prompt
    │
    ▼
④ LLM Generation (Ollama / Vertex AI)
    │  Streams tokens via SSE as they are produced
    │
    ▼
⑤ Output Guardrail (pattern match)
       Scans for system-prompt leakage / jailbreak confirmations
```

The client receives a stream of JSON events (`status`, `token`, `guardrail`, `done`) and renders them progressively — each pipeline stage displays its own timer so users know exactly what the system is doing.

---

## Features

### RAG-Powered Q&A with Source Citations

Answers are generated exclusively from chunks retrieved from your uploaded documents. The LLM is instructed to cite the source file and page number for every claim. If the knowledge base does not contain relevant information the system says so, rather than hallucinating.

Retrieval uses `all-MiniLM-L6-v2` (Sentence-Transformers) for embedding and ChromaDB for vector search. A configurable cosine distance threshold (`SECURAG_RETRIEVAL_DISTANCE_THRESHOLD`, default `0.7`) discards chunks that are too loosely related before they reach the LLM, preventing low-confidence context from degrading answer quality.

### Multi-Turn Conversation Memory

Each chat session maintains a persistent history in PostgreSQL. Before every query the backend loads the last 6 messages (3 user/assistant turns) and prepends them to the prompt:

```
Previous conversation:
User: What is OWASP?
Assistant: OWASP is the Open Web Application Security Project...
---
Context from knowledge base:
[Source: owasp-top10.pdf, Page 4]
...
User question: How many categories does it define?
```

This allows natural follow-up questions — the LLM understands pronouns and references to earlier answers without the user repeating context.

### Real-Time Streaming with Per-Stage Timers

Responses stream token-by-token using Server-Sent Events. The UI displays three pipeline stages as the request progresses:

```
✓  Checking input safety...      0.0s
✓  Searching knowledge base...   0.1s
✓  Generating response...       35.1s
```

Timers use server-side Unix timestamps (`ts`) embedded in each `status` SSE event to measure actual stage durations, avoiding the client-side batching problem where all events in a single TCP packet appear to arrive simultaneously.

### Stream Cancellation

A **Stop** button appears while generation is in progress. Clicking it aborts the fetch via `AbortController` on the frontend. The backend detects the client disconnect via `GeneratorExit` and persists whatever partial response was accumulated before the abort — so the conversation history remains coherent even for interrupted messages.

### AI Safety — Three-Layer Model

The system applies safety checks at three points, each scoped to what it can reliably do:

| Layer | What it checks | Mechanism |
|-------|---------------|-----------|
| **Input Guardrail** | User query — blocks prompt injection and off-topic requests | NeMo Guardrails (Colang flows + LLM self-check) |
| **Retrieval Filter** | Retrieved chunks — drops low-relevance context | Cosine distance threshold |
| **Output Guardrail** | LLM response — catches system-prompt leakage and jailbreak confirmations | Pattern matching on high-signal phrases |

The input guardrail is **fail-closed**: if NeMo throws an exception the request is blocked rather than silently allowed through. The output guardrail uses pattern matching rather than a second LLM call because NeMo's `generate_async` is a response-generation API, not an auditing API — routing an already-generated response through it triggers NeMo's own input rails on the trigger phrase, producing false positives on legitimate answers.

### Document Management

Upload PDF, TXT, or Markdown files through the Documents view. Each document is processed asynchronously:

1. **Parsing** — PDF text is extracted page-by-page; Markdown and plain text are read directly
2. **Chunking** — Split into overlapping chunks (LangChain `RecursiveCharacterTextSplitter`)
3. **Embedding** — Each chunk is embedded with `all-MiniLM-L6-v2`
4. **Indexing** — Embeddings stored in ChromaDB with metadata (filename, page number, chunk index)

Document status transitions: `processing` → `ready` (or `error`). The UI polls for status changes. Documents can be deleted, which removes both the database record and all associated vectors from ChromaDB.

### Switchable LLM Backend

The `LLMProvider` abstraction allows swapping between backends with a single environment variable:

| Provider | Model | Use case |
|----------|-------|----------|
| `ollama` (default) | Llama 3.2 (local) | Air-gapped / fully private deployment |
| `vertexai` | Gemini 1.5 Flash | Cloud deployment, higher quality |

Both providers implement the same `generate_stream` interface so the rest of the pipeline is unaffected by the choice.

### Airflow Auto-Ingest Pipeline

SecuRAG ships with an Apache Airflow DAG (`securag_auto_ingest`) that automates document ingestion from a watched folder. Drop any PDF, TXT, or Markdown file into `watched_docs/` and it will be indexed into the knowledge base automatically — no UI interaction required.

The DAG runs on a 6-hour schedule and executes two tasks in sequence:

| Task | What it does |
|------|-------------|
| `scan_watch_folder` | Queries `/api/documents` for already-ingested filenames, scans `watched_docs/`, computes the diff |
| `ingest_new_files` | Uploads each new file to `/api/documents/upload`; fails the task if any upload errors, triggering Airflow's retry logic |

Task outputs are passed between stages via **XCom** (Airflow's inter-task communication mechanism). Failed ingestions retry once after 5 minutes.

The Airflow web UI is available at **http://localhost:8080** (admin / admin). DAGs can also be triggered manually from the UI without waiting for the next scheduled run.

### MCP Server — Claude Desktop Integration

SecuRAG exposes its knowledge base as **Model Context Protocol (MCP)** tools, allowing Claude Desktop to query your documents directly during a conversation without copy-pasting content.

Three tools are registered:

| Tool | Description |
|------|-------------|
| `list_documents` | Lists all documents currently in the knowledge base |
| `search_knowledge_base` | Semantic search — returns the most relevant raw chunks for a query |
| `ask_securag` | Full RAG pipeline — retrieves context and generates a cited answer via the local LLM |

The MCP server runs inside the existing backend Docker container (Python 3.11 + all dependencies already present). Claude Desktop communicates with it via `docker exec`.

**Setup:** add the following to `~/Library/Application Support/Claude/claude_desktop_config.json`, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "securag": {
      "command": "docker",
      "args": ["exec", "-i", "securag-backend-1", "python", "/app/mcp_server.py"]
    }
  }
}
```

SecuRAG services must be running (`make up`) before starting Claude Desktop.

### Audit Trail

Every significant event is written to the `audit_logs` table with timestamp, event type, detail payload, and client IP:

- `query` — user sent a message
- `upload` — document uploaded and indexed
- `delete_document` — document removed
- `guardrail_block` — input was blocked by guardrails

Indexed on `event_type` and `created_at` for efficient compliance reporting queries.

---

## Architecture

<img width="1672" height="941" alt="SecuRAG" src="https://github.com/user-attachments/assets/8849e19f-2ef2-4d15-9f16-869c42171acf" />

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | Vue 3, Naive UI | Composition API, `<script setup>` |
| Backend | FastAPI, SQLAlchemy 2.0 async | Async throughout; Alembic for migrations |
| Embeddings | Sentence-Transformers `all-MiniLM-L6-v2` | Runs in-process, no GPU required |
| Vector Store | ChromaDB | Persistent local volume |
| LLM | Ollama (Llama 3.2) / GCP Vertex AI | Swappable via env var |
| Safety | NVIDIA NeMo Guardrails | Colang flows + LLM self-check |
| Database | PostgreSQL 16 | Chat history, documents, audit logs |
| Pipeline Orchestration | Apache Airflow 2.9 | Scheduled auto-ingest from watched folder |
| AI Integration | MCP (Model Context Protocol) | Exposes knowledge base as Claude Desktop tools |
| Deployment | Docker Compose | Single `make up` to start everything |

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 4.0+
- ~4 GB free disk space (Llama 3.2 model)

### Quick Start

```bash
git clone https://github.com/lin891020/SecuRAG.git
cd SecuRAG

cp .env.example .env   # review defaults, no edits required for local use

make build             # build Docker images (~5 min first time)
make up                # start all services
make pull-model        # download Llama 3.2 (~2 GB, first time only)
make ps                # verify all containers are running
```

Open **http://localhost:3000** in your browser.

### First Steps

1. Go to **Documents** → upload one or more PDF/TXT/Markdown files
2. Wait for status to show `ready` (embedding runs in the background)
3. Go to **Chat** → ask a question about the uploaded content
4. The AI responds with cited sources; ask follow-up questions naturally

---

## Configuration

All settings are environment variables in `.env`. The full list is in [`.env.example`](.env.example).

### Core Settings

```bash
# LLM backend: "ollama" (default, fully local) or "vertexai"
SECURAG_LLM_PROVIDER=ollama

# Cosine distance cutoff for retrieval (0 = perfect match, 1 = unrelated)
# Raise this to be more permissive; lower it to require tighter relevance
SECURAG_RETRIEVAL_DISTANCE_THRESHOLD=0.7

# NeMo Guardrails on/off
SECURAG_GUARDRAILS_ENABLED=true
```

### Switching to Vertex AI

```bash
SECURAG_LLM_PROVIDER=vertexai
SECURAG_GCP_PROJECT=your-project-id
SECURAG_GCP_REGION=us-central1
SECURAG_VERTEXAI_MODEL=gemini-1.5-flash
```

Ensure `GOOGLE_APPLICATION_CREDENTIALS` or Application Default Credentials are configured in the backend container.

---

## Development

### Running Tests

```bash
make test
# or directly:
docker compose exec backend python -m pytest tests/ -v
```

The test suite covers API endpoints, RAG pipeline, guardrails service, LLM providers, and utilities — **104 tests, 0 failures**.

### Project Structure

```
SecuRAG/
├── backend/
│   ├── app/
│   │   ├── api/              # Route handlers: chat.py, documents.py, health.py, rag.py
│   │   ├── guardrails/       # NeMo guard wrapper + Colang config
│   │   │   └── config/       # config.yml, rails.co, prompts.yml
│   │   ├── llm/              # LLMProvider base class, Ollama + VertexAI impls
│   │   ├── models/           # SQLAlchemy ORM: ChatSession, ChatMessage, Document, AuditLog
│   │   ├── rag/              # Embedder, splitter, ChromaDB retriever
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── services/         # rag_pipeline.py (SSE orchestration), audit_service.py
│   │   └── utils/            # File parsers: PDF, TXT, Markdown
│   ├── mcp_server.py         # MCP server — exposes RAG tools to Claude Desktop
│   ├── alembic/              # DB migrations (001 initial schema, 002 indexes)
│   ├── tests/                # pytest — one file per module
│   └── pyproject.toml
├── dags/
│   └── securag_auto_ingest.py  # Airflow DAG: scan watched_docs/ every 6h and ingest
├── watched_docs/             # Drop files here for automatic ingestion
├── frontend/
│   ├── src/
│   │   ├── views/            # ChatView.vue, DocumentsView.vue, SettingsView.vue
│   │   ├── router/           # Vue Router
│   │   └── styles/           # Global CSS
│   └── package.json
├── docker/
│   ├── airflow/              # init.sh: db migrate + create admin user
│   ├── ollama/               # Entrypoint script: pulls model on first start
│   └── postgres/             # init.sql
├── docker-compose.yml
├── Makefile
└── .env.example
```

### Makefile Reference

| Command | Description |
|---------|-------------|
| `make up` | Start all services (detached) |
| `make down` | Stop and remove containers |
| `make build` | Rebuild Docker images |
| `make logs` | Tail logs from all services |
| `make pull-model` | Pull Llama 3.2 into the Ollama container |
| `make migrate` | Run pending Alembic migrations |
| `make airflow-setup` | Create Airflow metadata DB and run initial migrations (run once) |
| `make test` | Run the backend test suite |
| `make ps` | Show container status |
| `make shell-backend` | Open a shell in the backend container |

---

## API Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Liveness check — returns service status for all components |
| `POST` | `/api/chat` | Send a message; returns an SSE stream |
| `GET` | `/api/chat/sessions` | List the 50 most recent chat sessions |
| `GET` | `/api/chat/sessions/{id}/messages` | All messages in a session (chronological) |
| `PATCH` | `/api/chat/sessions/{id}` | Rename a session |
| `DELETE` | `/api/chat/sessions/{id}` | Delete session and all its messages |
| `GET` | `/api/documents` | List all documents with status |
| `POST` | `/api/documents/upload` | Upload and index a document (multipart/form-data) |
| `DELETE` | `/api/documents/{id}` | Delete document and remove its vectors |
| `POST` | `/api/rag/search` | Semantic search — returns raw chunks without LLM generation |
| `POST` | `/api/rag/ask` | Full RAG query — non-streaming, returns complete answer (used by MCP) |

Interactive docs available at **http://localhost:8000/docs**.

### SSE Event Stream (`POST /api/chat`)

Each `data:` line in the stream is a JSON object. The sequence for a normal response:

```
data: {"type": "status",   "label": "Checking input safety...",   "ts": 1714000000.1}
data: {"type": "status",   "label": "Searching knowledge base...", "ts": 1714000000.2}
data: {"type": "status",   "label": "Generating response...",      "ts": 1714000000.3}
data: {"type": "token",    "content": "Incident"}
data: {"type": "token",    "content": " response"}
...
data: {"type": "done",     "sources": [...], "ts": 1714000035.4}
```

If the input guardrail blocks the request:

```
data: {"type": "status",   "label": "Checking input safety...", "ts": ...}
data: {"type": "guardrail","content": "Request blocked by policy."}
data: {"type": "done",     "sources": [], "blocked": true}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `status` \| `token` \| `guardrail` \| `done` |
| `content` | string | Token text or block reason |
| `label` | string | Human-readable stage name (status events) |
| `ts` | float | Unix timestamp (status and done events) |
| `sources` | array | Source citations — `filename`, `page_number`, `content_preview` |
| `blocked` | bool | Present and `true` on done event when guardrail triggered |

---

## Troubleshooting

**Documents not found after restarting containers**  
ChromaDB persists data to `/data` inside its container. Ensure your `docker-compose.yml` mounts the volume at that exact path: `chroma_data:/data`. A mismatch causes data to be written to a non-persistent path and lost on restart.

**"Response was filtered by security policy" on normal questions**  
The output guardrail uses pattern matching for high-signal phrases only (system prompt leakage, jailbreak confirmations). If you see false positives, check that `SECURAG_GUARDRAILS_ENABLED` is `true` and that NeMo initialized successfully — inspect logs with `make logs`.

**LLM responses are very slow**  
Llama 3.2 on CPU can take 30–60 seconds per response. This is expected without a GPU. Switch to `SECURAG_LLM_PROVIDER=vertexai` for faster cloud inference, or run the stack on a machine with an Nvidia GPU and configure Ollama to use it.

**Guardrails blocking legitimate security questions**  
Adjust the Colang flows in `backend/app/guardrails/config/rails.co`. Add canonical examples to `define user ask about security` to help NeMo classify similar queries as allowed.

---

## License

MIT
