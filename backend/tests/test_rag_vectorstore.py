"""Tests for the vectorstore module."""

from unittest.mock import MagicMock, patch

import pytest

from app.rag.vectorstore import add_chunks, delete_document_chunks, get_collection, query_chunks


class TestGetCollection:
    def test_creates_collection_with_cosine_space(self):
        """Should create/get collection with cosine similarity."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch("app.rag.vectorstore.get_chroma_client", return_value=mock_client):
            result = get_collection()

        mock_client.get_or_create_collection.assert_called_once_with(
            name="securag_docs",
            metadata={"hnsw:space": "cosine"},
        )
        assert result is mock_collection


class TestAddChunks:
    def test_adds_chunks_with_correct_ids_and_metadata(self):
        """Should format IDs, embeddings, and metadata correctly."""
        mock_collection = MagicMock()
        chunks = [
            {"text": "Chunk one about firewalls.", "page": 1},
            {"text": "Chunk two about IDS.", "page": 2},
        ]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

        with patch("app.rag.vectorstore.get_collection", return_value=mock_collection):
            add_chunks(
                doc_id="doc-123",
                filename="guide.pdf",
                file_type="pdf",
                chunks=chunks,
                embeddings=embeddings,
            )

        mock_collection.add.assert_called_once()
        call_kwargs = mock_collection.add.call_args[1]

        assert call_kwargs["ids"] == ["doc-123_chunk_0", "doc-123_chunk_1"]
        assert call_kwargs["documents"] == ["Chunk one about firewalls.", "Chunk two about IDS."]
        assert call_kwargs["embeddings"] == embeddings
        assert call_kwargs["metadatas"][0]["doc_id"] == "doc-123"
        assert call_kwargs["metadatas"][0]["filename"] == "guide.pdf"
        assert call_kwargs["metadatas"][0]["chunk_index"] == 0
        assert call_kwargs["metadatas"][0]["page_number"] == 1
        assert call_kwargs["metadatas"][1]["chunk_index"] == 1

    def test_handles_none_page_number(self):
        """Should default page to 0 when None."""
        mock_collection = MagicMock()
        chunks = [{"text": "Text file content.", "page": None}]

        with patch("app.rag.vectorstore.get_collection", return_value=mock_collection):
            add_chunks("doc-1", "file.txt", "txt", chunks, [[0.1]])

        metadata = mock_collection.add.call_args[1]["metadatas"][0]
        assert metadata["page_number"] == 0


class TestQueryChunks:
    def test_queries_with_correct_params(self):
        """Should pass embedding, n_results, and include fields."""
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["result"]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        }

        with patch("app.rag.vectorstore.get_collection", return_value=mock_collection):
            result = query_chunks([0.1, 0.2, 0.3], top_k=3)

        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2, 0.3]],
            n_results=3,
            include=["documents", "metadatas", "distances"],
        )
        assert result["documents"][0] == ["result"]


class TestDeleteDocumentChunks:
    def test_deletes_by_doc_id(self):
        """Should delete all chunks with matching doc_id."""
        mock_collection = MagicMock()

        with patch("app.rag.vectorstore.get_collection", return_value=mock_collection):
            delete_document_chunks("doc-456")

        mock_collection.delete.assert_called_once_with(where={"doc_id": "doc-456"})
