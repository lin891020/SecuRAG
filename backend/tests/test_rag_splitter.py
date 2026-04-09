"""Tests for the text splitter module."""

from unittest.mock import patch

import pytest

from app.rag.splitter import get_text_splitter, split_pages


class TestGetTextSplitter:
    def test_returns_splitter_with_configured_params(self):
        """Splitter should use settings for chunk_size and overlap."""
        with patch("app.rag.splitter.settings") as mock_settings:
            mock_settings.chunk_size = 500
            mock_settings.chunk_overlap = 100
            splitter = get_text_splitter()

        assert splitter._chunk_size == 500
        assert splitter._chunk_overlap == 100

    def test_separators_include_common_delimiters(self):
        splitter = get_text_splitter()
        assert "\n\n" in splitter._separators
        assert "\n" in splitter._separators


class TestSplitPages:
    def test_split_single_short_page(self):
        """Short text should produce a single chunk."""
        pages = [{"text": "Short security note.", "page": 1}]
        chunks = split_pages(pages)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Short security note."
        assert chunks[0]["page"] == 1

    def test_split_multiple_pages(self):
        """Each page should produce at least one chunk."""
        pages = [
            {"text": "Page one content.", "page": 1},
            {"text": "Page two content.", "page": 2},
        ]
        chunks = split_pages(pages)
        assert len(chunks) >= 2
        page_nums = {c["page"] for c in chunks}
        assert page_nums == {1, 2}

    def test_split_long_text_produces_multiple_chunks(self):
        """Long text should be split into multiple chunks."""
        long_text = "Security is important. " * 200  # ~4600 chars
        pages = [{"text": long_text, "page": 1}]

        with patch("app.rag.splitter.settings") as mock_settings:
            mock_settings.chunk_size = 500
            mock_settings.chunk_overlap = 50
            chunks = split_pages(pages)

        assert len(chunks) > 1
        assert all(c["page"] == 1 for c in chunks)

    def test_split_empty_page(self):
        """Empty page text should produce no chunks."""
        pages = [{"text": "", "page": 1}]
        chunks = split_pages(pages)
        assert len(chunks) == 0

    def test_split_preserves_page_metadata(self, sample_pages):
        """Chunk page numbers should match their source page."""
        chunks = split_pages(sample_pages)
        for chunk in chunks:
            assert chunk["page"] in [1, 2]
