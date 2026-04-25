"""Tests for the documents API endpoints."""

import io
from unittest.mock import AsyncMock, patch

import pytest


class TestDocumentsList:
    async def test_list_documents_empty(self, client):
        """Should return empty list initially."""
        resp = await client.get("/api/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents"] == []


class TestDocumentUpload:
    async def test_upload_txt_file(self, client):
        """Should accept and ingest a .txt file."""
        file_content = b"Security policy: all access must be authenticated."

        with patch("app.services.document_service.parse_file") as mock_parse, \
             patch("app.services.document_service.split_pages") as mock_split, \
             patch("app.services.document_service.embed_texts") as mock_embed, \
             patch("app.services.document_service.add_chunks") as mock_add:

            mock_parse.return_value = [{"text": file_content.decode(), "page": None}]
            mock_split.return_value = [{"text": file_content.decode(), "page": None}]
            mock_embed.return_value = [[0.1] * 384]
            mock_add.return_value = None

            resp = await client.post(
                "/api/documents/upload",
                files={"file": ("policy.txt", io.BytesIO(file_content), "text/plain")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "policy.txt"
        assert data["file_type"] == "txt"
        assert data["status"] == "ready"
        assert data["chunk_count"] == 1

    async def test_upload_md_file(self, client):
        """Should accept .md files."""
        file_content = b"# Security Guide\n\nThis is a guide."

        with patch("app.services.document_service.parse_file") as mock_parse, \
             patch("app.services.document_service.split_pages") as mock_split, \
             patch("app.services.document_service.embed_texts") as mock_embed, \
             patch("app.services.document_service.add_chunks"):

            mock_parse.return_value = [{"text": file_content.decode(), "page": None}]
            mock_split.return_value = [{"text": file_content.decode(), "page": None}]
            mock_embed.return_value = [[0.1] * 384]

            resp = await client.post(
                "/api/documents/upload",
                files={"file": ("guide.md", io.BytesIO(file_content), "text/markdown")},
            )

        assert resp.status_code == 200
        assert resp.json()["file_type"] == "md"

    async def test_upload_unsupported_type_rejected(self, client):
        """Should reject files with unsupported extensions."""
        resp = await client.post(
            "/api/documents/upload",
            files={"file": ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    async def test_upload_no_filename_rejected(self, client):
        """Should reject upload with no filename (400 from our code or 422 from FastAPI multipart parsing)."""
        resp = await client.post(
            "/api/documents/upload",
            files={"file": ("", io.BytesIO(b"content"), "text/plain")},
        )
        assert resp.status_code in (400, 422)

    async def test_upload_appears_in_list(self, client):
        """Uploaded document should appear in the documents list."""
        file_content = b"Test document content."

        with patch("app.services.document_service.parse_file") as mock_parse, \
             patch("app.services.document_service.split_pages") as mock_split, \
             patch("app.services.document_service.embed_texts") as mock_embed, \
             patch("app.services.document_service.add_chunks"):

            mock_parse.return_value = [{"text": file_content.decode(), "page": None}]
            mock_split.return_value = [{"text": file_content.decode(), "page": None}]
            mock_embed.return_value = [[0.1] * 384]

            await client.post(
                "/api/documents/upload",
                files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
            )

        resp = await client.get("/api/documents")
        docs = resp.json()["documents"]
        assert len(docs) == 1
        assert docs[0]["filename"] == "test.txt"


class TestDocumentDelete:
    async def test_delete_nonexistent_returns_404(self, client):
        """Should return 404 for unknown document ID."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.delete(f"/api/documents/{fake_id}")
        assert resp.status_code == 404

    async def test_delete_existing_document(self, client):
        """Should delete document and return success."""
        file_content = b"To be deleted."

        with patch("app.services.document_service.parse_file") as mock_parse, \
             patch("app.services.document_service.split_pages") as mock_split, \
             patch("app.services.document_service.embed_texts") as mock_embed, \
             patch("app.services.document_service.add_chunks"), \
             patch("app.services.document_service.delete_document_chunks"):

            mock_parse.return_value = [{"text": file_content.decode(), "page": None}]
            mock_split.return_value = [{"text": file_content.decode(), "page": None}]
            mock_embed.return_value = [[0.1] * 384]

            upload_resp = await client.post(
                "/api/documents/upload",
                files={"file": ("delete_me.txt", io.BytesIO(file_content), "text/plain")},
            )
            doc_id = upload_resp.json()["id"]

            resp = await client.delete(f"/api/documents/{doc_id}")

        assert resp.status_code == 200
        assert resp.json()["message"] == "Document deleted"

        # Verify it's gone
        list_resp = await client.get("/api/documents")
        assert len(list_resp.json()["documents"]) == 0

    async def test_delete_invalid_uuid_returns_422(self, client):
        """Should return 422 for malformed UUID."""
        resp = await client.delete("/api/documents/not-a-uuid")
        assert resp.status_code == 422
