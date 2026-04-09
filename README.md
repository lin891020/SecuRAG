# SecuRAG

**Enterprise Security Knowledge Base Chatbot** — A private-deployment RAG system with AI safety guardrails, built for organizations that need intelligent Q&A over their security documentation.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Vue](https://img.shields.io/badge/Vue-3-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Overview

SecuRAG enables security teams to upload internal documents (policies, SOPs, compliance guides) and query them through a conversational AI interface. All data stays on-premise — the LLM runs locally via Ollama, and documents are indexed in a self-hosted vector database.

### Key Features

- **RAG-Powered Q&A** — Retrieval-Augmented Generation ensures answers are grounded in your actual documents, with source citations
- **Real-time Streaming** — Server-Sent Events deliver token-by-token responses, similar to ChatGPT
- **AI Safety Layer** — NVIDIA NeMo Guardrails blocks prompt injection, off-topic queries, and unsafe outputs
- **Document Management** — Upload PDF/TXT/Markdown files with automatic chunking and vector embedding
- **Private Deployment** — Fully containerized with Docker Compose; no data leaves your infrastructure
- **Switchable LLM Backend** — Swap between local Ollama and GCP Vertex AI with a single env variable
- **Audit Trail** — All queries, uploads, and guardrail blocks are logged for compliance

## Architecture

```
┌──────────────┐     ┌──────────────────────────────────────────┐
│              │     │              FastAPI Backend              │
│   Vue 3 UI   │────▶│                                          │
│  (Naive UI)  │ SSE │  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│              │◀────│  │ NeMo    │  │   RAG   │  │  Audit  │ │
└──────────────┘     │  │Guardrail│  │Pipeline │  │  Logger │ │
                     │  └────┬────┘  └────┬────┘  └─────────┘ │
                     │       │            │                     │
                     └───────┼────────────┼─────────────────────┘
                             │            │
                  ┌──────────┼────────────┼──────────┐
                  │          ▼            ▼          │
                  │   ┌──────────┐  ┌──────────┐    │
                  │   │  Ollama  │  │ ChromaDB │    │
                  │   │ (LLM)   │  │ (Vectors)│    │
                  │   └──────────┘  └──────────┘    │
                  │        ┌──────────┐             │
                  │        │PostgreSQL│             │
                  │        │  (Data)  │             │
                  │        └──────────┘             │
                  │         Docker Compose           │
                  └──────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vue 3, Naive UI, Markdown-it |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Alembic |
| RAG | LangChain, Sentence-Transformers (`all-MiniLM-L6-v2`) |
| Vector Store | ChromaDB |
| LLM | Ollama (Llama 3.2) / GCP Vertex AI (Gemini 1.5 Flash) |
| Safety | NVIDIA NeMo Guardrails |
| Database | PostgreSQL 16 |
| Deployment | Docker Compose |

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (v4.0+)
- ~4 GB free disk space (for LLM model download)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/lin891020/SecuRAG.git
cd SecuRAG

# Copy environment config
cp .env.example .env

# Build and start all services
make build
make up

# Download the LLM model (first time only, ~2 GB)
make pull-model

# Verify everything is running
make ps
```

### Access the Application

| Service | URL |
|---------|-----|
| **Web UI** | http://localhost:3000 |
| **API Docs** | http://localhost:8000/docs |
| **Health Check** | http://localhost:8000/api/health |

### Usage

1. Navigate to **Documents** in the sidebar
2. Upload security documents (PDF, TXT, or Markdown)
3. Wait for status to change to `ready`
4. Switch to **Chat** and start asking questions
5. The AI will answer based on your uploaded documents, with source citations

## Project Structure

```
SecuRAG/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   ├── guardrails/       # NeMo Guardrails config & service
│   │   ├── llm/              # LLM provider abstraction (Ollama / Vertex AI)
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── rag/              # RAG pipeline (embeddings, splitter, retriever)
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic layer
│   │   └── utils/            # File parsers (PDF, TXT, MD)
│   ├── alembic/              # Database migrations
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── views/            # ChatView, DocumentsView, SettingsView
│   │   ├── router/           # Vue Router config
│   │   └── styles/           # Global CSS
│   ├── Dockerfile
│   └── package.json
├── docker/
│   ├── ollama/               # Model pull script
│   └── postgres/             # DB init script
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Configuration

All configuration is done through environment variables in `.env`. See [`.env.example`](.env.example) for all available options.

### Switch to Vertex AI

```bash
# In .env
SECURAG_LLM_PROVIDER=vertexai
SECURAG_GCP_PROJECT=your-gcp-project
SECURAG_GCP_REGION=us-central1
SECURAG_VERTEXAI_MODEL=gemini-1.5-flash
```

### Disable Guardrails

```bash
SECURAG_GUARDRAILS_ENABLED=false
```

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make up` | Start all services |
| `make down` | Stop all services |
| `make build` | Build Docker images |
| `make logs` | Tail service logs |
| `make pull-model` | Download Ollama LLM model |
| `make migrate` | Run database migrations |
| `make ps` | Show service status |
| `make shell-backend` | Open backend container shell |

## Security Features

### NeMo Guardrails

The AI safety layer protects against:

- **Prompt Injection** — Detects and blocks attempts to override system instructions ("ignore previous instructions", "act as DAN", etc.)
- **Topic Restriction** — Redirects off-topic queries back to security-related subjects
- **Output Filtering** — Screens LLM responses for harmful content before delivery

### Data Privacy

- All processing happens locally — no data sent to external APIs (when using Ollama)
- Documents stored on local volumes with Docker
- PostgreSQL stores chat history and audit logs on-premise

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Service health check |
| `POST` | `/api/chat` | Send message (SSE streaming response) |
| `GET` | `/api/chat/sessions` | List chat sessions |
| `GET` | `/api/documents` | List uploaded documents |
| `POST` | `/api/documents/upload` | Upload and index a document |
| `DELETE` | `/api/documents/{id}` | Delete a document |

## License

MIT
