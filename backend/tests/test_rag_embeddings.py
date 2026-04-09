"""Tests for the embeddings module."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.rag.embeddings import embed_query, embed_texts, get_embedding_model


class TestGetEmbeddingModel:
    def test_returns_singleton(self):
        """Model should be loaded once and reused."""
        with patch("app.rag.embeddings._model", None), \
             patch("app.rag.embeddings.SentenceTransformer") as MockST:
            mock_model = MagicMock()
            MockST.return_value = mock_model

            model1 = get_embedding_model()
            model2 = get_embedding_model()

        # SentenceTransformer called once, same instance returned
        MockST.assert_called_once()
        assert model1 is model2


class TestEmbedTexts:
    def test_returns_list_of_float_lists(self):
        """Should return list of embedding vectors."""
        fake_embeddings = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])

        with patch("app.rag.embeddings.get_embedding_model") as mock_get:
            mock_model = MagicMock()
            mock_model.encode.return_value = fake_embeddings
            mock_get.return_value = mock_model

            result = embed_texts(["text one", "text two"])

        assert len(result) == 2
        assert isinstance(result[0], list)
        assert isinstance(result[0][0], float)
        mock_model.encode.assert_called_once_with(["text one", "text two"], show_progress_bar=False)

    def test_empty_input_returns_empty(self):
        """Empty input should return empty list."""
        fake_embeddings = np.array([]).reshape(0, 384)

        with patch("app.rag.embeddings.get_embedding_model") as mock_get:
            mock_model = MagicMock()
            mock_model.encode.return_value = fake_embeddings
            mock_get.return_value = mock_model

            result = embed_texts([])

        assert result == []


class TestEmbedQuery:
    def test_returns_single_vector(self):
        """Should return a single embedding vector for a query."""
        fake_embedding = np.array([0.1, 0.2, 0.3])

        with patch("app.rag.embeddings.get_embedding_model") as mock_get:
            mock_model = MagicMock()
            mock_model.encode.return_value = fake_embedding
            mock_get.return_value = mock_model

            result = embed_query("what is a firewall?")

        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(v, float) for v in result)
