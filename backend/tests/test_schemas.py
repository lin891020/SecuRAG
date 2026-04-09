"""Tests for Pydantic schemas."""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest, ChatMessageResponse, ChatSessionResponse, SourceReference
from app.schemas.document import DocumentListResponse, DocumentResponse


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(message="What is XSS?")
        assert req.message == "What is XSS?"
        assert req.session_id is None

    def test_with_session_id(self):
        sid = uuid.uuid4()
        req = ChatRequest(message="Follow up", session_id=sid)
        assert req.session_id == sid

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest()


class TestSourceReference:
    def test_valid_source(self):
        src = SourceReference(
            document_id="abc-123",
            filename="policy.pdf",
            chunk_index=0,
            page_number=5,
            content_preview="SQL injection is...",
        )
        assert src.filename == "policy.pdf"
        assert src.page_number == 5

    def test_optional_page_number(self):
        src = SourceReference(
            document_id="abc",
            filename="notes.txt",
            chunk_index=0,
            content_preview="text",
        )
        assert src.page_number is None


class TestChatMessageResponse:
    def test_from_attributes(self):
        """Should work with from_attributes for ORM model conversion."""
        resp = ChatMessageResponse(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            role="assistant",
            content="Firewall is...",
            created_at=datetime.now(),
        )
        assert resp.role == "assistant"
        assert resp.sources is None


class TestChatSessionResponse:
    def test_from_attributes(self):
        resp = ChatSessionResponse(
            id=uuid.uuid4(),
            title="Security Q&A",
            created_at=datetime.now(),
        )
        assert resp.title == "Security Q&A"

    def test_nullable_title(self):
        resp = ChatSessionResponse(
            id=uuid.uuid4(),
            title=None,
            created_at=datetime.now(),
        )
        assert resp.title is None


class TestDocumentResponse:
    def test_valid_document(self):
        resp = DocumentResponse(
            id=uuid.uuid4(),
            filename="policy.pdf",
            file_type="pdf",
            file_size=1024000,
            chunk_count=15,
            status="ready",
            created_at=datetime.now(),
        )
        assert resp.file_type == "pdf"
        assert resp.chunk_count == 15

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            DocumentResponse(
                id=uuid.uuid4(),
                filename="test.pdf",
                # missing file_type, file_size, etc.
            )


class TestDocumentListResponse:
    def test_empty_list(self):
        resp = DocumentListResponse(documents=[])
        assert resp.documents == []

    def test_with_documents(self):
        doc = DocumentResponse(
            id=uuid.uuid4(),
            filename="guide.md",
            file_type="md",
            file_size=2048,
            chunk_count=3,
            status="ready",
            created_at=datetime.now(),
        )
        resp = DocumentListResponse(documents=[doc])
        assert len(resp.documents) == 1
        assert resp.documents[0].filename == "guide.md"
