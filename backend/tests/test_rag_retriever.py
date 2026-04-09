"""Tests for the retriever module."""

from unittest.mock import patch

import pytest

from app.rag.retriever import retrieve


class TestRetrieve:
    def test_returns_chunks_with_metadata(self):
        """Should return structured chunk dicts from ChromaDB results."""
        mock_results = {
            "documents": [["SQL injection is dangerous.", "Use parameterized queries."]],
            "metadatas": [[
                {"doc_id": "doc-1", "filename": "owasp.pdf", "chunk_index": 0, "page_number": 5},
                {"doc_id": "doc-1", "filename": "owasp.pdf", "chunk_index": 1, "page_number": 6},
            ]],
            "distances": [[0.15, 0.22]],
        }

        with patch("app.rag.retriever.embed_query", return_value=[0.1] * 384), \
             patch("app.rag.retriever.query_chunks", return_value=mock_results):

            chunks = retrieve("How to prevent SQL injection?")

        assert len(chunks) == 2
        assert chunks[0]["text"] == "SQL injection is dangerous."
        assert chunks[0]["doc_id"] == "doc-1"
        assert chunks[0]["filename"] == "owasp.pdf"
        assert chunks[0]["page_number"] == 5
        assert chunks[0]["distance"] == 0.15
        assert chunks[0]["chunk_index"] == 0

    def test_returns_empty_when_no_results(self):
        """Should return empty list when ChromaDB has no matches."""
        mock_results = {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        with patch("app.rag.retriever.embed_query", return_value=[0.1] * 384), \
             patch("app.rag.retriever.query_chunks", return_value=mock_results):

            chunks = retrieve("Something obscure")

        assert chunks == []

    def test_returns_empty_when_documents_none(self):
        """Should handle None documents gracefully."""
        mock_results = {"documents": None, "metadatas": None}

        with patch("app.rag.retriever.embed_query", return_value=[0.1] * 384), \
             patch("app.rag.retriever.query_chunks", return_value=mock_results):

            chunks = retrieve("anything")

        assert chunks == []

    def test_uses_configured_top_k(self):
        """Should pass top_k from settings to query_chunks."""
        mock_results = {"documents": [[]], "metadatas": [[]]}

        with patch("app.rag.retriever.embed_query", return_value=[0.1] * 384), \
             patch("app.rag.retriever.query_chunks", return_value=mock_results) as mock_query, \
             patch("app.rag.retriever.settings") as mock_settings:

            mock_settings.retrieval_top_k = 10
            retrieve("test")

        mock_query.assert_called_once_with([0.1] * 384, top_k=10)

    def test_custom_top_k_overrides_settings(self):
        """Explicit top_k should override the settings value."""
        mock_results = {"documents": [[]], "metadatas": [[]]}

        with patch("app.rag.retriever.embed_query", return_value=[0.1] * 384), \
             patch("app.rag.retriever.query_chunks", return_value=mock_results) as mock_query:

            retrieve("test", top_k=3)

        mock_query.assert_called_once_with([0.1] * 384, top_k=3)

    def test_handles_missing_distance(self):
        """Should handle results without distance field."""
        mock_results = {
            "documents": [["Some text"]],
            "metadatas": [[{"doc_id": "d1", "filename": "f.pdf", "chunk_index": 0, "page_number": 1}]],
        }

        with patch("app.rag.retriever.embed_query", return_value=[0.1] * 384), \
             patch("app.rag.retriever.query_chunks", return_value=mock_results):

            chunks = retrieve("test")

        assert len(chunks) == 1
        assert chunks[0]["distance"] is None
