"""Tests for LLM providers and factory."""

import json
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.factory import get_llm_provider
from app.llm.ollama_provider import OllamaProvider


class TestLLMFactory:
    def test_creates_ollama_provider(self):
        """Should create OllamaProvider when provider is 'ollama'."""
        mock_config = MagicMock()
        mock_config.llm_provider = "ollama"
        mock_config.ollama_base_url = "http://localhost:11434"
        mock_config.ollama_model = "llama3.2"

        provider = get_llm_provider(mock_config)
        assert isinstance(provider, OllamaProvider)

    def test_creates_vertexai_provider(self):
        """Should create VertexAIProvider when provider is 'vertexai'."""
        from app.llm.vertexai_provider import VertexAIProvider

        mock_config = MagicMock()
        mock_config.llm_provider = "vertexai"
        mock_config.gcp_project = "my-project"
        mock_config.gcp_region = "us-central1"
        mock_config.vertexai_model = "gemini-1.5-flash"

        provider = get_llm_provider(mock_config)
        assert isinstance(provider, VertexAIProvider)

    def test_raises_on_unknown_provider(self):
        """Should raise ValueError for unknown provider."""
        mock_config = MagicMock()
        mock_config.llm_provider = "gpt-4"

        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_provider(mock_config)


class TestOllamaProvider:
    def test_model_name(self):
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")
        assert provider.model_name() == "ollama/llama3.2"

    def test_strips_trailing_slash(self):
        provider = OllamaProvider(base_url="http://localhost:11434/", model="llama3.2")
        assert provider._base_url == "http://localhost:11434"

    async def test_generate_calls_ollama_api(self):
        """Should POST to /api/generate with stream=False."""
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "A firewall is a network security device."}
        mock_response.raise_for_status = MagicMock()

        with patch("app.llm.ollama_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await provider.generate("What is a firewall?", system_prompt="You are helpful.")

        assert result == "A firewall is a network security device."
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        body = call_kwargs[1]["json"]
        assert body["model"] == "llama3.2"
        assert body["stream"] is False
        assert body["system"] == "You are helpful."

    async def test_generate_stream_yields_tokens(self):
        """Should stream tokens from Ollama's streaming API."""
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

        # Simulate streaming response lines
        lines = [
            json.dumps({"response": "Hello", "done": False}),
            json.dumps({"response": " world", "done": False}),
            json.dumps({"response": "", "done": True}),
        ]

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = lambda: _async_iter(lines)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            tokens = []
            async for token in provider.generate_stream("test prompt"):
                tokens.append(token)

        assert tokens == ["Hello", " world"]

    async def test_generate_stream_stops_on_done(self):
        """Should stop yielding when done=True."""
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

        lines = [
            json.dumps({"response": "Only this", "done": True}),
            json.dumps({"response": "Should not appear", "done": False}),
        ]

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = lambda: _async_iter(lines)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            tokens = []
            async for token in provider.generate_stream("test"):
                tokens.append(token)

        assert tokens == ["Only this"]


class TestVertexAIProvider:
    def test_model_name(self):
        from app.llm.vertexai_provider import VertexAIProvider

        provider = VertexAIProvider(project="proj", region="us-central1", model="gemini-1.5-flash")
        assert provider.model_name() == "vertexai/gemini-1.5-flash"

    async def test_stream_yields_chunks(self):
        with _stubbed_vertex() as (provider, model):
            model.generate_content.return_value = [
                MagicMock(text="Incident"), MagicMock(text=" response"),
            ]
            got = [t async for t in provider.generate_stream("q")]

        assert got == ["Incident", " response"]

    async def test_stream_raises_what_the_producer_thread_hit(self):
        """A failure mid-stream must reach the caller, not end the stream.

        The producer runs in an executor thread; an exception there used to die
        with the thread while the end-of-stream sentinel went out as usual, so a
        revoked credential or a quota refusal arrived as a short answer and a
        200 with nothing in the log.
        """
        def _boom(*_args, **_kwargs):
            yield MagicMock(text="Incident")
            raise RuntimeError("403 quota exceeded")

        seen = []
        with _stubbed_vertex() as (provider, model):
            model.generate_content.side_effect = _boom
            with pytest.raises(RuntimeError, match="quota exceeded"):
                async for token in provider.generate_stream("q"):
                    seen.append(token)

        # what did arrive before the failure is still delivered
        assert seen == ["Incident"]


@contextmanager
def _stubbed_vertex():
    """A VertexAIProvider with the google SDK replaced by mocks.

    The provider imports `vertexai` inside each method, so the stub has to stay
    in `sys.modules` for the duration of the call, not just construction.
    """
    from app.llm.vertexai_provider import VertexAIProvider

    model = MagicMock()
    generative_models = MagicMock()
    generative_models.GenerativeModel.return_value = model
    with patch.dict(sys.modules, {"vertexai": MagicMock(),
                                  "vertexai.generative_models": generative_models}):
        yield VertexAIProvider(project="p", region="r", model="m"), model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _async_iter(items):
    for item in items:
        yield item
