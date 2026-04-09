"""Shared test fixtures for SecuRAG backend tests."""

import uuid
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app

# ---------------------------------------------------------------------------
# Database fixtures — in-memory SQLite for fast, isolated tests
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # SQLite needs "PRAGMA foreign_keys=ON" per connection
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(db_engine) -> AsyncIterator[AsyncClient]:
    """FastAPI test client with DB overridden to use in-memory SQLite."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Provide a mock LLM provider on app.state
    app.state.llm_provider = make_mock_llm()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------


def make_mock_llm():
    """Create a mock LLM provider that streams a fixed response."""
    mock = MagicMock()
    mock.model_name.return_value = "mock/test-model"

    async def fake_generate(prompt: str, system_prompt: str = "") -> str:
        return "This is a test response about security."

    async def fake_generate_stream(prompt: str, system_prompt: str = ""):
        tokens = ["This ", "is ", "a ", "test ", "response."]
        for token in tokens:
            yield token

    mock.generate = fake_generate
    mock.generate_stream = fake_generate_stream
    return mock


@pytest.fixture
def mock_llm():
    return make_mock_llm()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_doc_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_pages() -> list[dict]:
    return [
        {"text": "This is page one about firewall configuration and network security.", "page": 1},
        {"text": "Page two covers access control policies and least privilege principle.", "page": 2},
    ]


@pytest.fixture
def sample_chunks() -> list[dict]:
    return [
        {"text": "Firewall configuration requires proper rule ordering.", "page": 1},
        {"text": "Network security depends on defense in depth.", "page": 1},
        {"text": "Access control follows the principle of least privilege.", "page": 2},
    ]


@pytest.fixture
def sample_contexts() -> list[dict]:
    return [
        {
            "text": "SQL injection is a code injection technique.",
            "doc_id": "abc-123",
            "filename": "owasp_guide.pdf",
            "chunk_index": 0,
            "page_number": 5,
            "distance": 0.15,
        },
        {
            "text": "Use parameterized queries to prevent SQL injection.",
            "doc_id": "abc-123",
            "filename": "owasp_guide.pdf",
            "chunk_index": 1,
            "page_number": 6,
            "distance": 0.22,
        },
    ]


@pytest.fixture
def tmp_text_file(tmp_path) -> Path:
    f = tmp_path / "test_policy.txt"
    f.write_text("This is a security policy document.\nIt covers access control.\n")
    return f


@pytest.fixture
def tmp_md_file(tmp_path) -> Path:
    f = tmp_path / "test_guide.md"
    f.write_text("# Security Guide\n\n## Firewall Rules\n\nAllow only necessary ports.\n")
    return f


@pytest.fixture
def tmp_pdf_file(tmp_path) -> Path:
    """Create a minimal valid PDF for testing."""
    f = tmp_path / "test_doc.pdf"
    # Minimal PDF structure
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Security Doc) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000360 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
441
%%EOF"""
    f.write_bytes(pdf_content)
    return f
